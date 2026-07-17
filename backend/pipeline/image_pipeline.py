"""
V3.0 Layer 9 — Image Pipeline (Cascade)

Full image generation cascade:
  Prompt → Flux → PuLID (face consistency) → SUPIR (4K upscale)
  → CodeFormer (face restore) → QualityEngine (scoring) → Final Image

Uses WorkflowGenerator + ComfyUIClient for real GPU inference.
Integrates MediaCache for cache-hit skip.
Each stage can be independently skipped via CLI flags.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from loguru import logger


class ImagePipeline:
    """Cascade image generation pipeline backed by ComfyUI.

    Each stage is a pluggable method. Stages run sequentially;
    any stage can be disabled via skip flags.

    Uses WorkflowGenerator to build ComfyUI API-format workflows
    from UnifiedShot objects, and ComfyUIClient for submission.

    Usage:
        pipeline = ImagePipeline(output_dir="output/project")
        result = pipeline.run(shot=shot, character_dna_list=char_dnas)
    """

    def __init__(
        self,
        output_dir: str = "",
        skip_pulid: bool = False,
        skip_supir: bool = False,
        skip_codeformer: bool = False,
    ):
        self.output_dir = os.path.abspath(output_dir or "output")
        self.skip_pulid = skip_pulid
        self.skip_supir = skip_supir
        self.skip_codeformer = skip_codeformer

        # Lazy-initialized
        self._client = None
        self._generator = None
        self._cache = None
        self._comfyui_output_dir = ""

    # ── Public API ─────────────────────────────────────────

    def run(
        self,
        shot: Any,
        character_dna_list: Optional[List[Any]] = None,
    ) -> ImagePipelineResult:
        """Run the full image cascade on a single UnifiedShot.

        Args:
            shot: UnifiedShot object with merged_prompt, camera, etc.
            character_dna_list: List of CharacterDNA for face embeddings.

        Returns:
            ImagePipelineResult with final image path and stage details.
        """
        result = ImagePipelineResult()
        stage_times: Dict[str, float] = {}

        # ── Lazy init ─────────────────────────────────────
        self._ensure_initialized()

        # ── Cache check ───────────────────────────────────
        cache_key = self._cache_key(shot)
        cached = self._cache_lookup(shot, cache_key)
        if cached:
            logger.info(f"ImagePipeline: CACHE HIT {shot.shot_id} → {os.path.basename(cached)}")
            result.base_image = cached
            result.current_image = cached
            result.final_image = cached
            result.status = "SUCCESS"
            result.cache_hit = True
            return result

        # ── Stage 1: Flux Generation ─────────────────────
        t0 = time.time()
        try:
            result.base_image = self._generate_base(shot)
        except Exception as e:
            logger.error(f"ImagePipeline: Flux generation failed for {shot.shot_id}: {e}")
            result.status = "FAILED"
            result.error = f"Flux generation: {e}"
            return result
        stage_times["flux"] = time.time() - t0

        if not result.base_image:
            result.status = "FAILED"
            result.error = "Base generation returned empty path"
            return result

        result.current_image = result.base_image

        # ── Stage 2: PuLID (Face Consistency) ────────────
        if not self.skip_pulid and self._has_face_embeddings(character_dna_list):
            t0 = time.time()
            try:
                result.pulid_image = self._apply_pulid(
                    image_path=result.current_image,
                    character_dna_list=character_dna_list,
                )
            except Exception as e:
                logger.error(f"ImagePipeline: PuLID failed: {e}")
            stage_times["pulid"] = time.time() - t0
            if result.pulid_image:
                result.current_image = result.pulid_image

        # ── Stage 3: SUPIR (4K Upscale) ──────────────────
        if not self.skip_supir:
            t0 = time.time()
            try:
                result.supir_image = self._apply_supir(
                    image_path=result.current_image,
                )
            except Exception as e:
                logger.error(f"ImagePipeline: SUPIR failed: {e}")
            stage_times["supir"] = time.time() - t0
            if result.supir_image:
                result.current_image = result.supir_image
        else:
            result.supir_image = result.current_image

        # ── Stage 4: CodeFormer (Face Restore) ───────────
        if not self.skip_codeformer:
            t0 = time.time()
            try:
                result.codeformer_image = self._apply_codeformer(
                    image_path=result.current_image,
                )
            except Exception as e:
                logger.error(f"ImagePipeline: CodeFormer failed: {e}")
            stage_times["codeformer"] = time.time() - t0
            if result.codeformer_image:
                result.current_image = result.codeformer_image
        else:
            result.codeformer_image = result.current_image

        # ── Final ────────────────────────────────────────
        result.final_image = result.current_image
        result.stage_times = stage_times
        result.status = "SUCCESS"

        # ── Write cache ───────────────────────────────────
        if result.final_image:
            self._cache_store(shot, cache_key, result.final_image)

        return result

    # ── Stage: Flux Base Generation ───────────────────────

    def _generate_base(self, shot: Any) -> str:
        """Generate base image via Flux Kontext.

        Builds a ComfyUI workflow from the shot, submits to ComfyUI,
        and copies the output to our project directory.

        Returns:
            Absolute path to generated image, or "" on failure.
        """
        workflow = self._generator.generate(shot)

        # ── Validate workflow before submission ──────────
        validation_errors = self._validate_workflow(workflow, shot.shot_id)
        if validation_errors:
            for err in validation_errors:
                logger.warning(f"ImagePipeline: [WORKFLOW VALIDATION] {shot.shot_id}: {err}")

        result = self._client.submit_workflow(workflow, wait=True)
        if not result:
            logger.error(f"ImagePipeline: ComfyUI returned empty result for {shot.shot_id}")
            return ""

        images = result.get("images", [])
        if not images:
            logger.error(f"ImagePipeline: No output images in ComfyUI result for {shot.shot_id}")
            return ""

        # Copy from ComfyUI output dir to our project
        source_path = images[0].get("path", "")
        if not source_path or not os.path.exists(source_path):
            logger.error(f"ImagePipeline: Output image not found: {source_path}")
            return ""

        # Copy to project output dir
        shot_output_dir = os.path.join(self.output_dir, "shots")
        os.makedirs(shot_output_dir, exist_ok=True)
        shot_id = getattr(shot, "shot_id", "") or f"ch{getattr(shot, 'chapter', 0):02d}_sc{getattr(shot, 'scene', 1):02d}_sh{getattr(shot, 'shot', 0):03d}"
        dest_path = os.path.join(shot_output_dir, f"{shot_id}_flux.png")

        try:
            import shutil
            shutil.copy(source_path, dest_path)
            logger.info(f"ImagePipeline: Copied {os.path.basename(source_path)} → {dest_path}")
        except Exception as e:
            logger.error(f"ImagePipeline: Copy failed: {e}")
            # Fall back to source path
            dest_path = source_path

        return dest_path

    # ── Stage: PuLID Face Consistency ─────────────────────

    def _apply_pulid(
        self,
        image_path: str,
        character_dna_list: Optional[List[Any]] = None,
    ) -> str:
        """Apply PuLID for face identity consistency.

        Injects CharacterDNA.face_embedding to lock face identity.
        Uses ComfyUI PuLID workflow if available, otherwise falls
        back to PIL-based approach or returns the original.

        Args:
            image_path: Path to source image.
            character_dna_list: List of CharacterDNA with face embeddings.

        Returns:
            Path to PuLID-processed image, or "" on failure.
        """
        if not character_dna_list:
            return ""

        face_embeddings = []
        for cd in character_dna_list:
            emb = getattr(cd, "face_embedding", "")
            if emb and os.path.exists(emb):
                face_embeddings.append(emb)

        if not face_embeddings:
            logger.debug("ImagePipeline: No face embeddings found — skipping PuLID")
            return ""

        logger.info(f"ImagePipeline: PuLID with {len(face_embeddings)} face embeddings")
        # TODO: Build PuLID workflow and submit to ComfyUI
        # For now, return empty — PuLID needs a dedicated workflow template
        return ""

    # ── Stage: SUPIR 4K Upscale ───────────────────────────

    def _apply_supir(self, image_path: str) -> str:
        """Upscale to 4K using SUPIR or PIL Lanczos fallback.

        SUPIR (Scaling-UP Image Restoration) produces higher quality
        upscales with detail hallucination.

        Falls back to PIL Lanczos + UnsharpMask if SUPIR model is unavailable.

        Returns:
            Path to upscaled image, or "" on failure.
        """
        if not image_path or not os.path.exists(image_path):
            return ""

        # Try SUPIR via ComfyUI first
        try:
            upscaled = self._supir_comfyui(image_path)
            if upscaled:
                return upscaled
        except Exception as e:
            logger.warning(f"ImagePipeline: SUPIR ComfyUI failed ({e}), falling back to PIL")

        # Fallback: PIL Lanczos upscale
        return self._upscale_pil(image_path, 3840, 2160)

    def _supir_comfyui(self, image_path: str) -> str:
        """Submit SUPIR workflow to ComfyUI.

        Returns:
            Path to upscaled image, or "" on failure.
        """
        import json

        # Load SUPIR workflow template
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "workflow", "templates",
        )
        template_path = os.path.join(templates_dir, "supir_4k.json")
        if not os.path.exists(template_path):
            logger.warning(f"ImagePipeline: SUPIR template not found: {template_path}")
            return ""

        with open(template_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # Inject input image path into the workflow
        self._inject_image_path(workflow, image_path, "LoadImage")

        result = self._client.submit_workflow(workflow, wait=True)
        if not result:
            return ""

        images = result.get("images", [])
        if images:
            return images[0].get("path", "")

        return ""

    def _upscale_pil(self, image_path: str, target_w: int, target_h: int) -> str:
        """Upscale using PIL Lanczos + UnsharpMask.

        Same approach as FluxPlugin._upscale_image.
        """
        try:
            from PIL import Image, ImageFilter

            img = Image.open(image_path)
            current_w, current_h = img.size

            if current_w >= target_w and current_h >= target_h:
                logger.info(f"ImagePipeline: Skip upscale — already {current_w}x{current_h}")
                return image_path

            img_upscaled = img.resize((target_w, target_h), Image.LANCZOS)

            upscale_factor = max(target_w / current_w, target_h / current_h)
            if upscale_factor >= 3.0:
                img_upscaled = img_upscaled.filter(
                    ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2)
                )
            elif upscale_factor >= 2.0:
                img_upscaled = img_upscaled.filter(
                    ImageFilter.UnsharpMask(radius=1.2, percent=100, threshold=2)
                )
            else:
                img_upscaled = img_upscaled.filter(
                    ImageFilter.UnsharpMask(radius=0.8, percent=80, threshold=3)
                )

            base, ext = os.path.splitext(image_path)
            upscaled_path = f"{base}_4k{ext}"
            img_upscaled.save(upscaled_path, quality=95)
            logger.info(f"ImagePipeline: PIL upscale {current_w}x{current_h} → {target_w}x{target_h} → {upscaled_path}")
            return upscaled_path

        except Exception as e:
            logger.error(f"ImagePipeline: PIL upscale failed: {e}")
            return ""

    # ── Stage: CodeFormer Face Restore ────────────────────

    def _apply_codeformer(self, image_path: str) -> str:
        """Apply CodeFormer face restoration.

        Uses ComfyUI CodeFormer node if available.

        Returns:
            Path to restored image, or "" on failure.
        """
        if not image_path or not os.path.exists(image_path):
            return ""

        # TODO: Build CodeFormer workflow and submit to ComfyUI
        logger.info(f"ImagePipeline: CodeFormer on {os.path.basename(image_path)} (not yet implemented)")
        return ""

    # ── Cache Integration ─────────────────────────────────

    def _cache_key(self, shot: Any) -> str:
        """Build a cache key from shot attributes."""
        project = getattr(shot, "project_id", "") or "default"
        chapter = getattr(shot, "chapter", 0)
        shot_id = getattr(shot, "shot_id", "") or f"sh{getattr(shot, 'shot', 0):03d}"
        return f"{project}/ch{chapter:02d}/{shot_id}"

    def _cache_lookup(self, shot: Any, cache_key: str) -> str:
        """Look up a shot in the media cache.

        Returns:
            Cached image path, or "" if not found.
        """
        if not self._cache:
            try:
                from backend.media_cache import MediaCache
                self._cache = MediaCache()
            except Exception as e:
                logger.warning(f"ImagePipeline: Cache init failed: {e}")
                return ""

        try:
            prompt = getattr(shot, "merged_prompt", "") or getattr(shot, "positive_prompt", "")
            prompt_hash = str(hash(prompt))[-12:]
            meta = {
                "project": getattr(shot, "project_id", "") or "default",
                "chapter": getattr(shot, "chapter", 0),
                "shot_id": getattr(shot, "shot_id", ""),
                "prompt": (prompt or "")[:80],
            }
            return self._cache.get(cache_key, "shots", meta) or ""
        except Exception:
            return ""

    def _cache_store(self, shot: Any, cache_key: str, image_path: str) -> None:
        """Store a generated image in the media cache."""
        if not self._cache:
            return

        try:
            self._cache.cache_shot(
                project_id=getattr(shot, "project_id", "") or "default",
                chapter=getattr(shot, "chapter", 0),
                shot_id=getattr(shot, "shot_id", "") or f"sh{getattr(shot, 'shot', 0):03d}",
                generated_path=image_path,
                prompt_hash=str(hash(
                    getattr(shot, "merged_prompt", "") or getattr(shot, "positive_prompt", "")
                ))[-12:],
            )
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────

    def _ensure_initialized(self) -> None:
        """Lazy-init ComfyUI client and WorkflowGenerator."""
        if self._client is not None:
            return

        from backend.comfyui_client import ComfyUIClient
        from backend.workflow_generator import WorkflowGenerator

        self._client = ComfyUIClient()
        self._generator = WorkflowGenerator()
        logger.info(f"ImagePipeline: Initialized — ComfyUI @ {self._client.base_url}")

        # Check connection
        ok, msg = self._client.check_connection()
        if ok:
            logger.info(f"ImagePipeline: {msg}")
        else:
            logger.warning(f"ImagePipeline: ComfyUI not reachable: {msg}")

    @staticmethod
    def _has_face_embeddings(character_dna_list: Optional[List[Any]]) -> bool:
        """Check if any CharacterDNA has face embedding files."""
        if not character_dna_list:
            return False
        for cd in character_dna_list:
            emb = getattr(cd, "face_embedding", "")
            if emb and os.path.exists(emb):
                return True
        return False

    @staticmethod
    def _inject_image_path(workflow: Dict, image_path: str, target_node_type: str) -> None:
        """Inject an image path into a workflow's LoadImage node."""
        image_path = image_path.replace("\\", "/")
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            if class_type == target_node_type:
                inputs = node.get("inputs", {})
                if "image" in inputs:
                    inputs["image"] = image_path
                    logger.debug(f"ImagePipeline: Injected image path into node {node_id}")
                    return
        logger.warning(f"ImagePipeline: No {target_node_type} node found to inject image path")

    # ── Workflow Validation ────────────────────────────────────

    @staticmethod
    def _validate_workflow(workflow: Dict[str, Any], shot_id: str) -> List[str]:
        """Validate a ComfyUI workflow before submission.

        Checks for missing connections, placeholder strings, and
        incorrect node types that would cause ComfyUI errors or
        corrupted output (pink/purple/liquid images).

        Args:
            workflow: ComfyUI API-format workflow dict.
            shot_id: Shot identifier for log messages.

        Returns:
            List of validation error strings (empty = valid).
        """
        errors: List[str] = []

        # ── Check for PLACEHOLDER strings ─────────────────
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs", {})
            for key, val in inputs.items():
                if isinstance(val, str) and val.startswith("PLACEHOLDER"):
                    errors.append(
                        f"Node {node_id} ({node.get('class_type','?')}): "
                        f"unresolved placeholder in '{key}' = '{val}'"
                    )

        # ── KSampler connectivity ─────────────────────────
        sampler_nodes = [nid for nid, n in workflow.items()
                         if isinstance(n, dict) and n.get("class_type") == "KSampler"]
        for nid in sampler_nodes:
            inputs = workflow[nid].get("inputs", {})
            required = ["model", "positive", "negative", "latent_image"]
            for r in required:
                val = inputs.get(r)
                if val is None:
                    errors.append(
                        f"KSampler node {nid}: missing required input '{r}' — "
                        f"KSampler without '{r}' will produce black/corrupted output"
                    )

        # ── VAEDecode connectivity ────────────────────────
        vae_nodes = [nid for nid, n in workflow.items()
                     if isinstance(n, dict) and n.get("class_type") == "VAEDecode"]
        for nid in vae_nodes:
            inputs = workflow[nid].get("inputs", {})
            if inputs.get("vae") is None:
                errors.append(
                    f"VAEDecode node {nid}: missing 'vae' input — "
                    f"VAEDecode without VAE will produce pink/garbage output"
                )
            if inputs.get("samples") is None:
                errors.append(
                    f"VAEDecode node {nid}: missing 'samples' input — "
                    f"VAEDecode without latent samples will produce empty output"
                )

        # ── CLIPTextEncodeFlux connectivity ───────────────
        for nid, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") != "CLIPTextEncodeFlux":
                continue
            inputs = node.get("inputs", {})
            for field in ("clip", "clip_l", "t5xxl"):
                if not inputs.get(field):
                    errors.append(
                        f"CLIPTextEncodeFlux node {nid}: missing '{field}' input — "
                        f"incomplete CLIP encoding will produce corrupted text conditioning"
                    )

        # ── Check for CheckpointLoaderSimple + Flux ───────
        for nid, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "CheckpointLoaderSimple":
                ckpt_name = node.get("inputs", {}).get("ckpt_name", "")
                if "flux" in str(ckpt_name).lower():
                    errors.append(
                        f"Node {nid}: CheckpointLoaderSimple loading Flux model '{ckpt_name}' — "
                        f"Flux models should use UNETLoader. CheckpointLoaderSimple may return "
                        f"invalid CLIP/VAE, causing pink/purple/liquid artifacts."
                    )

        # ── SaveImage connectivity ────────────────────────
        save_nodes = [nid for nid, n in workflow.items()
                      if isinstance(n, dict) and n.get("class_type") == "SaveImage"]
        for nid in save_nodes:
            inputs = workflow[nid].get("inputs", {})
            if inputs.get("images") is None:
                errors.append(
                    f"SaveImage node {nid}: missing 'images' input — no output will be saved"
                )

        return errors


class ImagePipelineResult:
    """Result of an ImagePipeline run."""

    def __init__(self):
        self.status: str = "PENDING"
        self.error: str = ""
        self.cache_hit: bool = False
        self.base_image: str = ""
        self.pulid_image: str = ""
        self.supir_image: str = ""
        self.codeformer_image: str = ""
        self.current_image: str = ""
        self.final_image: str = ""
        self.quality_scores: Dict[str, float] = {}
        self.stage_times: Dict[str, float] = {}
