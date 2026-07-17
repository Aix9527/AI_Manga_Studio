"""
AI Manga Studio Pro V3 鈥?Face Consistency Engine

鏍规嵁 CharacterDNA 鐨?seed + appearance_prompt锛屽湪鍥剧墖鐢熸垚鍚?鎵ц闈㈤儴涓€鑷存€т慨澶嶏紙PuLID / IPAdapter / ControlNet Union锛夈€?
ComfyUI 鐜妫€娴嬶細
  - PuLID_ComfyUI 鑷畾涔夎妭鐐瑰凡瀹夎
  - ComfyUI_IPAdapter_plus 宸插畨瑁?  - FLUX.1-dev-Controlnet-Union.safetensors 宸插氨缁?  - 鈿?PuLID/IPAdapter 妯″瀷鐩綍褰撳墠涓虹┖ 鈥?闇€瑕佺敤鎴锋墜鍔ㄤ笅杞芥ā鍨?"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


# ============================================================
# Data Classes
# ============================================================

@dataclass
class FaceConsistencyResult:
    """Result of face consistency application."""

    input_image: str = ""
    output_image: str = ""
    method: str = ""             # "pulid" / "ipadapter" / "none"
    success: bool = False
    error: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Availability Detection
# ============================================================

def _check_pulid_available(comfyui_path: str = "D:\\ComfyUI_new") -> bool:
    """Check if PuLID models are available in ComfyUI."""
    pulid_dir = os.path.join(comfyui_path, "models", "pulid")
    if os.path.isdir(pulid_dir):
        files = os.listdir(pulid_dir)
        model_files = [f for f in files if not f.startswith("put_") and not f.startswith(".")]
        if model_files:
            return True
    return False


def _check_ipadapter_available(comfyui_path: str = "D:\\ComfyUI_new") -> bool:
    """Check if IPAdapter models are available."""
    ipa_dir = os.path.join(comfyui_path, "models", "ipadapter")
    if os.path.isdir(ipa_dir):
        files = os.listdir(ipa_dir)
        model_files = [f for f in files if not f.startswith("put_") and not f.startswith(".")]
        if model_files:
            return True
    return False


def _get_available_method(comfyui_path: str = "D:\\ComfyUI_new") -> str:
    """Determine the best available face consistency method.

    Returns: "pulid" | "ipadapter" | "none"
    """
    if _check_pulid_available(comfyui_path):
        return "pulid"
    if _check_ipadapter_available(comfyui_path):
        return "ipadapter"
    return "none"


# ============================================================
# Face Consistency Engine
# ============================================================

class FaceConsistencyEngine:
    """鏍规嵁 CharacterDNA 鎵ц闈㈤儴涓€鑷存€т慨澶嶃€?
    鏀寔涓夌鏂规硶锛堟寜浼樺厛绾э級锛?      1. PuLID 鈥?鏈€寮轰竴鑷存€э紝闇€瑕?PuLID 妯″瀷
      2. IPAdapter 鈥?杞婚噺闈㈤儴閿佸畾
      3. None   鈥?璺宠繃锛堟ā鍨嬩笉鍙敤鏃讹級

    浣跨敤鏂瑰紡锛?        engine = FaceConsistencyEngine(comfyui_client)
        result = engine.apply(image_path, character_dna)
    """

    def __init__(
        self,
        comfyui_client: Any = None,
        workflow_template: str = "flux_pulid.json",
        comfyui_path: str = "D:\\ComfyUI_new",
    ):
        self.comfyui = comfyui_client
        self.workflow_template = workflow_template
        self.comfyui_path = comfyui_path

        # Detect available method
        self.method = _get_available_method(comfyui_path)
        if self.method == "none":
            logger.warning(
                "FaceConsistencyEngine: No PuLID or IPAdapter models found. "
                "Face consistency will be skipped. "
                "To enable: download models to D:\\ComfyUI_new\\models\\pulid\\ "
                "or D:\\ComfyUI_new\\models\\ipadapter\\"
            )
        else:
            logger.info(f"FaceConsistencyEngine: Using method={self.method}")

    # 鈹€鈹€ Public API 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def apply(
        self,
        image_path: str,
        character_dna: Any,
        reference_image: Optional[str] = None,
    ) -> FaceConsistencyResult:
        """瀵瑰崟寮犲浘鐗囧簲鐢ㄩ潰閮ㄤ竴鑷存€э紝杩斿洖淇鍚庣殑鍥剧墖璺緞銆?
        Args:
            image_path: 婧愬浘鐗囩粷瀵硅矾寰勩€?            character_dna: CharacterDNA 瀵硅薄锛堝惈 appearance_prompt / seed锛夈€?            reference_image: 鍙€夊弬鑰冨浘锛堢敤浜?IPAdapter 鍙傝€冩ā寮忥級銆?
        Returns:
            FaceConsistencyResult with output_image path.
        """
        if self.method == "none":
            return FaceConsistencyResult(
                input_image=image_path,
                output_image=image_path,
                method="none",
                success=True,
                error="PuLID/IPAdapter models not available 鈥?skipped",
            )

        if self.comfyui is None:
            return FaceConsistencyResult(
                input_image=image_path,
                output_image=image_path,
                method=self.method,
                success=False,
                error="No ComfyUI client provided",
            )

        try:
            # Build workflow with face consistency nodes injected
            workflow = self.build_workflow(
                base_workflow=None,  # Will load from template
                character_dna=character_dna,
                reference_image=reference_image,
            )

            # Submit to ComfyUI
            # TODO: Integrate with actual ComfyUI client submit API
            # result = self.comfyui.submit_workflow(workflow, input_image=image_path)
            # output_path = result.output_images[0]

            logger.info(
                f"FaceConsistency: method={self.method}, "
                f"character={getattr(character_dna, 'name', '?')}, "
                f"image={Path(image_path).name}"
            )

            return FaceConsistencyResult(
                input_image=image_path,
                output_image=image_path,  # Placeholder 鈥?needs actual ComfyUI integration
                method=self.method,
                success=True,
            )

        except Exception as e:
            logger.error(f"FaceConsistencyEngine.apply failed: {e}")
            return FaceConsistencyResult(
                input_image=image_path,
                output_image=image_path,
                method=self.method,
                success=False,
                error=str(e),
            )

    def build_workflow(
        self,
        base_workflow: Optional[dict] = None,
        character_dna: Any = None,
        reference_image: Optional[str] = None,
    ) -> dict:
        """娉ㄥ叆 PuLID/IPAdapter 鑺傜偣鍒?Flux workflow銆?
        Args:
            base_workflow: 鍩虹 Flux workflow dict锛堝彲閫夛級銆?            character_dna: CharacterDNA 瀵硅薄銆?            reference_image: 鍙傝€冨浘璺緞銆?
        Returns:
            Modified workflow dict with face consistency nodes.
        """
        if base_workflow is None:
            # Load default template
            base_workflow = self._load_template()

        if self.method == "pulid":
            return self._inject_pulid(base_workflow, character_dna, reference_image)
        elif self.method == "ipadapter":
            return self._inject_ipadapter(base_workflow, character_dna, reference_image)
        return base_workflow

    # 鈹€鈹€ Internal 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _load_template(self) -> dict:
        """Load workflow template JSON."""
        import json

        template_dir = Path(__file__).parent.parent / "workflow" / "templates"
        template_path = template_dir / self.workflow_template
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                return json.load(f)
        logger.warning(f"Workflow template not found: {template_path}")
        return {}

    def _inject_pulid(
        self,
        workflow: dict,
        character_dna: Any,
        reference_image: Optional[str] = None,
    ) -> dict:
        """Inject PuLID Apply node after VAE Decode.

        PuLID node chain:
          LoadImage 鈫?PuLIDModelLoader 鈫?PuLIDApply (between VAE Decode and SaveImage)
        """
        # PuLID requires custom node: PuLID_ComfyUI
        # Node types: ApplyPuLIDFlux, PuLIDModelLoader
        # For now, return workflow as-is with metadata annotation
        workflow["_face_consistency"] = {
            "method": "pulid",
            "character": getattr(character_dna, "name", ""),
            "status": "PLACEHOLDER 鈥?PuLID models need to be downloaded",
            "install_guide": (
                "Download PuLID models from HuggingFace to D:\\ComfyUI_new\\models\\pulid\\"
            ),
        }
        return workflow

    def _inject_ipadapter(
        self,
        workflow: dict,
        character_dna: Any,
        reference_image: Optional[str] = None,
    ) -> dict:
        """Inject IPAdapter FaceID node.

        IPAdapter chain:
          LoadImage 鈫?IPAdapterModelLoader 鈫?IPAdapterApply 鈫?KSampler
        """
        workflow["_face_consistency"] = {
            "method": "ipadapter",
            "character": getattr(character_dna, "name", ""),
            "status": "PLACEHOLDER 鈥?IPAdapter models need to be downloaded",
            "install_guide": (
                "Download IPAdapter-FaceID models to D:\\ComfyUI_new\\models\\ipadapter\\"
            ),
        }
        return workflow

    # 鈹€鈹€ Static helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    @staticmethod
    def get_install_guide() -> str:
        """Return installation guide for face consistency models."""
        return (
            "Face Consistency 妯″瀷瀹夎鎸囧崡锛歕n"
            "鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€\n"
            "1. PuLID Flux (鎺ㄨ崘):\n"
            "   - 涓嬭浇 pulid_flux_v0.9.0.safetensors 鈫?D:\\ComfyUI_new\\models\\pulid\\\n"
            "   - 涓嬭浇 Eva-Clip 妯″瀷 鈫?D:\\ComfyUI_new\\models\\clip\\\n"
            "   鍙傝€? https://github.com/balazik/PuLID_ComfyUI\n\n"
            "2. IPAdapter FaceID (澶囬€?:\n"
            "   - 涓嬭浇 ip-adapter-faceid-plusv2_sd15.bin 鈫?D:\\ComfyUI_new\\models\\ipadapter\\\n"
            "   鍙傝€? https://github.com/cubiq/ComfyUI_IPAdapter_plus\n\n"
            "3. ControlNet Union (宸叉湁):\n"
            "   - FLUX.1-dev-Controlnet-Union.safetensors 宸插湪 models/controlnet/\n"
        )

    @staticmethod
    def is_available(comfyui_path: str = "D:\\ComfyUI_new") -> bool:
        """Check if any face consistency method is available."""
        return _get_available_method(comfyui_path) != "none"
