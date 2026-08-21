"""QC Report — 逐镜头验收指标（GPT Round-1 验收格式）。

对每个生成视频输出：
  duration / resolution / fps / file size / motion score /
  visual quality / face score / anatomy proxy / PASS|FAIL

PASS 判定（GPT Round-1）：
  - 通过 Video Contract（时长/分辨率/帧率/文件大小）
  - visual quality >= 0.70（"像素 0.7 以上"的量化指标）
  - mosaic 帧占比 <= 10%、identity/face 不低于阈值（可用时）
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _probe(video_path: Path) -> dict:
    from backend.production.video_contract import probe_video, validate_video
    probe = probe_video(video_path)
    errors = validate_video(probe)
    return {
        "duration": round(probe.duration, 2),
        "resolution": f"{probe.width}x{probe.height}" if probe.width else "0x0",
        "width": probe.width,
        "height": probe.height,
        "fps": probe.fps,
        "frame_count": probe.frame_count,
        "file_size_kb": round(probe.size_bytes / 1024),
        "contract_errors": errors,
    }


def _quality(video_path: Path) -> dict:
    """Visual quality in 0-1 (from quality_gate's 0-100 score)."""
    try:
        from backend.video.quality_gate import check_video_quality
        report = check_video_quality(video_path)
        q = {
            "visual_quality": round(report.overall_score / 100.0, 3),
            "mosaic": round(getattr(report, "mosaic_ratio", getattr(report, "mosaic_score", 0.0)) or 0.0, 3),
            "issues": list(getattr(report, "issues", []) or []),
        }
        # quality_gate 某些版本把 score 存为 0-100 的 overall_score
        return q
    except Exception as exc:
        logger.warning("Quality gate unavailable: %s", exc)
        return {"visual_quality": 0.0, "mosaic": 0.0, "issues": ["quality_gate_error"]}


def _motion(video_path: Path) -> dict:
    try:
        from backend.video.quality_gate import compute_motion_metrics
        base = compute_motion_metrics(video_path)
    except Exception:
        base = {}

    # GPT Round-2A: 拆分为 motion_energy / motion_smoothness / flicker_score
    # 不要混淆"运动量"和"运动稳定性"。
    motion_score = base.get("motion_score", 0.0)
    motion_cv = base.get("motion_cv", 1.0)

    report = dict(base)
    report["motion_energy"] = round(motion_score, 3)
    # flicker_score: 帧间运动变化系数归一化（越高越闪）
    report["flicker_score"] = round(min(1.0, max(0.0, motion_cv / 2.0)), 3)
    # motion_smoothness: 平滑度 = 1 - flicker
    report["motion_smoothness"] = round(max(0.0, 1.0 - report["flicker_score"]), 3)

    # flow_variance: 相邻帧差的标准差（局部运动跳变信号）
    try:
        import numpy as np
        from backend.video.quality_gate import _read_sample_frames
        frames = _read_sample_frames(video_path)
        if len(frames) >= 3:
            diffs = [float(np.abs(frames[i + 1] - frames[i]).mean()) for i in range(len(frames) - 1)]
            report["flow_variance"] = round(float(np.std(diffs)), 3)
        else:
            report["flow_variance"] = 0.0
    except Exception:
        report["flow_variance"] = 0.0
    return report


def _face_and_anatomy(video_path: Path) -> dict:
    """Face/anatomy via real face detection (GPT Round-3B).

    用 YuNet 真实人脸检测替换 Round-1/2 的"中心区域纹理"启发式：
      face_score = 0.3*detection_rate + 0.25*sharpness + 0.25*identity_consistency + 0.2*avg_face_size
    分级：FAIL<0.45 / MARGINAL<0.55 / PASS<0.70 / GOOD<0.85 / EXCELLENT
    """
    try:
        from backend.video.face_report import compute_face_report
        r = compute_face_report(video_path, sample_count=6)
        return {
            "face_score": r.face_score,
            "face_grade": r.grade,
            "face_detection_rate": r.detection_rate,
            "face_avg_size": r.avg_face_size,
            "face_sharpness": r.sharpness,
            "face_identity_consistency": r.identity_consistency,
            "num_faces_seen": r.num_faces_seen,
            "anatomy": 0.0,  # 保留字段；真实解剖需接入人体关键点模型（后续）
        }
    except Exception:
        return {"face_score": 0.0, "face_grade": "FAIL", "anatomy": 0.0}


def _face_requirement(shot_class: str) -> dict:
    """GPT Round-4: face_score 阈值按镜头类型分级，不做固定 >=0.85 一刀切。

    - 特写/对白（dialogue/closeup）: 脸是主体，要求高
    - 动作（action）: 高速运动中脸可模糊，要求中低
    - 远景/战斗（wide/combat）: 脸可选，不设门槛
    """
    sc = (shot_class or "normal").lower()
    if sc in ("dialogue", "closeup", "emotional", "特写", "对白"):
        return {"requirement": "high", "pass": 0.70, "good": 0.85}
    if sc in ("action", "combat", "extreme_action", "动作", "战斗"):
        return {"requirement": "medium", "pass": 0.40, "good": 0.65}
    return {"requirement": "optional", "pass": 0.0, "good": 0.0}


def generate_qc_report(video_path: Path, shot_class: str = "normal") -> dict:
    """Produce the GPT Round-1 acceptance-format QC report for one video.

    shot_class（GPT Round-3 分级门槛）:
      normal 普通镜头: visual>=0.80 flicker<=0.35
      action 动作镜头: visual>=0.75 motion_energy>=5 flicker<=0.55 continuity>=0.65
      climax 高潮镜头: visual>=0.70 motion_energy>=10（允许爆点牺牲清晰度）
    """
    video_path = Path(video_path)
    report: dict = {"video": str(video_path)}
    if not video_path.exists():
        report.update({"status": "FAIL", "reason": "missing_file"})
        return report

    probe = _probe(video_path)
    quality = _quality(video_path)
    motion = _motion(video_path)
    face = _face_and_anatomy(video_path)

    report.update(probe)
    report.update(quality)
    report.update(motion)
    report.update(face)

    contract_errors = probe.get("contract_errors", [])
    mosaic_ok = quality.get("mosaic", 0.0) <= 0.10
    motion_energy = motion.get("motion_energy", 0.0)
    flicker = motion.get("flicker_score", 1.0)
    visual = quality.get("visual_quality", 0.0)

    # GPT Round-3 分级门槛
    if shot_class == "climax":
        visual_ok = visual >= 0.70
        motion_ok = motion_energy >= 10.0
        flicker_ok = flicker <= 0.60
    elif shot_class == "action":
        visual_ok = visual >= 0.75
        motion_ok = motion_energy >= 5.0
        flicker_ok = flicker <= 0.55
    else:
        visual_ok = visual >= 0.80
        motion_ok = motion_energy >= 0.10
        flicker_ok = flicker <= 0.35

    # GPT Round-4: face_score 按镜头类型分级（仅 high/medium 设门槛，optional 不拦）
    face_req = _face_requirement(shot_class)
    face_score = face.get("face_score", 0.0)
    face_ok = face_score >= face_req["pass"] or face_req["requirement"] == "optional"

    failures = []
    if contract_errors:
        failures.extend(contract_errors)
    if not visual_ok:
        failures.append(f"visual_quality<{0.80 if shot_class == 'normal' else (0.75 if shot_class == 'action' else 0.70)}")
    if not mosaic_ok:
        failures.append("mosaic>0.10")
    if not motion_ok:
        failures.append(f"motion_energy<{10.0 if shot_class == 'climax' else (5.0 if shot_class == 'action' else 0.10)}")
    if not flicker_ok:
        failures.append(f"flicker>{flicker:.2f}")
    if not face_ok:
        failures.append(f"face_score<{face_req['pass']:.2f} ({face_req['requirement']})")

    report["shot_class"] = shot_class
    report["face_requirement"] = face_req
    report["status"] = "PASS" if not failures else "FAIL"
    report["failures"] = failures
    return report


def generate_episode_qc_report(videos: list[Path]) -> dict:
    """Produce per-shot QC reports for a sequence of videos (3 shots = 1 episode)."""
    shots = [generate_qc_report(v) for v in videos]
    return {
        "shots": shots,
        "summary": {
            "total": len(shots),
            "passed": sum(1 for s in shots if s.get("status") == "PASS"),
            "failed": sum(1 for s in shots if s.get("status") != "PASS"),
        },
    }
