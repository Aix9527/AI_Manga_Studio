# -*- coding: utf-8 -*-
"""FaceReport — 真实人脸检测的 QC 人脸评分（GPT Round-3B）。

背景：
  Round-1/2 的 face_score 用"中心区域纹理"启发式，无法区分背影/侧脸/正脸，
  已被 GPT 判定失效。Round-3 必须接入真实人脸检测。

实现：
  onnxruntime + YuNet（OpenCV Zoo）人脸检测模型（backend/video/models/yunet_face.onnx）。
  抽帧 -> 检测人脸 bbox -> 计算 detection_rate / avg_face_size / sharpness /
  identity_consistency，加权合成 face_score。

face_score = 0.3*detection_rate + 0.25*sharpness + 0.25*identity_consistency + 0.2*avg_face_size

分级（GPT Round-3）：FAIL <0.45 / PASS >=0.55 / GOOD >=0.70 / EXCELLENT >=0.85
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "models" / "yunet_face.onnx"


@dataclass
class FaceReport:
    detection_rate: float = 0.0       # 检出人脸帧占比 0-1
    avg_face_size: float = 0.0        # 人脸 bbox 面积占帧面积比（有脸帧均值）0-1
    sharpness: float = 0.0            # 人脸区域 Laplacian 方差归一化 0-1
    identity_consistency: float = 0.0 # 跨帧身份一致性（颜色直方图近似）0-1
    num_faces_seen: int = 0           # 抽帧中检出的人脸总数
    face_score: float = 0.0           # 合成分 0-1
    grade: str = "FAIL"               # FAIL/MARGINAL/PASS/GOOD/EXCELLENT
    detail: list[dict] = field(default_factory=list)  # 逐帧 bbox

    @property
    def score(self) -> float:
        return self.face_score


def _load_session():
    """Lazy-load the YuNet ONNX session. Returns None if model missing."""
    if not MODEL_PATH.exists():
        logger.warning("YuNet model missing: %s", MODEL_PATH)
        return None
    try:
        import onnxruntime as ort
        return ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    except Exception as exc:
        logger.warning("Failed to load YuNet ONNX session: %s", exc)
        return None


def _sample_color_frames(video_path: Path, count: int = 6) -> list:
    """Uniformly sample `count` color frames (BGR ndarray, full resolution)."""
    import numpy as np
    try:
        import imageio.v2 as imageio
        reader = imageio.get_reader(str(video_path))
        raw: list[np.ndarray] = []
        for frame in reader:
            arr = np.asarray(frame)
            if arr.ndim == 3 and arr.shape[2] >= 3:
                raw.append(arr[..., :3])  # keep color
            else:
                raw.append(arr)
        reader.close()
    except Exception as exc:
        logger.warning("color frame read failed for %s: %s", video_path, exc)
        return []

    if not raw:
        return []
    if len(raw) == 1:
        return [raw[0]]

    idxs = sorted({round(i * (len(raw) - 1) / (count - 1)) for i in range(count)})
    return [raw[i] for i in idxs]


def _laplacian_variance(img, x, y, w, h) -> float:
    """Laplacian variance of a bbox region, normalized to 0-1."""
    import numpy as np
    import cv2
    hh, ww = img.shape[:2]
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2, y2 = min(ww, int(x + w)), min(hh, int(y + h))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return 0.0
    gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(np.clip(lap.var() / 3000.0, 0.0, 1.0))


def _hist_similarity(f0, f1, x0, y0, x1, y1, w0, h0, w1, h1) -> float:
    """HSV 直方图相关性（无 ArcFace 时的身份一致性降级近似）。"""
    import numpy as np
    import cv2
    try:
        a = f0[int(y0):int(y0 + h0), int(x0):int(x0 + w0)]
        b = f1[int(y1):int(y1 + h1), int(x1):int(x1 + w1)]
        if a.size == 0 or b.size == 0:
            return 0.5
        ha = cv2.calcHist([cv2.cvtColor(a, cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 16], [0, 180, 0, 256])
        hb = cv2.calcHist([cv2.cvtColor(b, cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(ha, ha, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(hb, hb, 0, 1, cv2.NORM_MINMAX)
        return float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))
    except Exception:
        return 0.5


def _get_detector():
    """Lazy-create a cv2.FaceDetectorYN instance (handles decode + NMS)."""
    import cv2
    if not MODEL_PATH.exists():
        return None
    det = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (320, 320), score_threshold=0.5)
    return det


def _detect_faces(detector, frame_bgr):
    """Run YuNet (via cv2.FaceDetectorYN) on one BGR frame -> list of (conf, x, y, w, h)."""
    import cv2
    h, w = frame_bgr.shape[:2]
    detector.setInputSize((w, h))
    ret, faces = detector.detect(frame_bgr)
    results = []
    if not ret or faces is None or len(faces) == 0:
        return results
    for row in faces:
        # OpenCV FaceDetectorYN 输出列: [x, y, w, h, lm0x, lm0y, lm1x, lm1y, lm2x, lm2y, lm3x, lm3y, lm4x, lm4y, score]
        conf = float(row[14])
        if conf < 0.5:
            continue
        results.append((conf, float(row[0]), float(row[1]), float(row[2]), float(row[3])))
    return results


def compute_face_report(video_path: Path, sample_count: int = 6) -> FaceReport:
    """Run real face detection on a video and produce a FaceReport."""
    video_path = Path(video_path)
    report = FaceReport()
    detector = _get_detector()
    if detector is None:
        report.face_score = 0.0
        report.grade = "FAIL"
        report.detail = [{"error": "yunet_model_missing"}]
        return report

    import numpy as np

    frames = _sample_color_frames(video_path, count=sample_count)
    if not frames:
        report.face_score = 0.0
        report.grade = "FAIL"
        report.detail = [{"error": "no_frames_extracted"}]
        return report

    faces = []  # (frame_idx, conf, x, y, w, h, sharpness)
    for fi, frame in enumerate(frames):
        dets = _detect_faces(detector, frame)
        if not dets:
            continue
        conf, x, y, bw, bh = max(dets, key=lambda d: d[0])
        sharp = _laplacian_variance(frame, x, y, bw, bh)
        faces.append((fi, conf, x, y, bw, bh, sharp))
        report.detail.append({
            "frame": fi,
            "conf": round(conf, 3),
            "bbox": [round(v, 1) for v in (x, y, bw, bh)],
            "sharpness": round(sharp, 3),
        })

    report.num_faces_seen = len(faces)
    if not faces:
        report.face_score = 0.0
        report.grade = "FAIL"
        report.detail.append({"error": "no_faces_detected"})
        return report

    report.detection_rate = round(len(faces) / len(frames), 3)
    frame_areas = [frames[fi].shape[0] * frames[fi].shape[1] for fi, *_ in faces]
    report.avg_face_size = round(float(np.mean([(w * h) / a for (_, _, _, w, h, *_), a in zip(faces, frame_areas)])), 3)
    report.sharpness = round(float(np.mean([d[6] for d in faces])), 3)

    if len(faces) >= 2:
        fi0, _, x0, y0, w0, h0, _ = faces[0]
        fi1, _, x1, y1, w1, h1, _ = faces[-1]
        report.identity_consistency = round(
            _hist_similarity(frames[fi0], frames[fi1], x0, y0, x1, y1, w0, h0, w1, h1), 3
        )
    else:
        report.identity_consistency = 0.0

    report.face_score = round(
        0.3 * report.detection_rate
        + 0.25 * report.sharpness
        + 0.25 * report.identity_consistency
        + 0.2 * report.avg_face_size,
        3,
    )
    report.grade = _grade(report.face_score)
    return report


def _grade(score: float) -> str:
    if score < 0.45:
        return "FAIL"
    if score < 0.55:
        return "MARGINAL"
    if score < 0.70:
        return "PASS"
    if score < 0.85:
        return "GOOD"
    return "EXCELLENT"
