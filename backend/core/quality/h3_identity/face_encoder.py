"""H3 Identity QC：ArcFace 人脸编码（纯 ONNX，无需 insightface 包）

- RetinaFace det_10g（人脸检测 + 5 关键点）
- w600k_r50（ArcFace 512-d embedding）
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

DET_PATH = Path("D:/ComfyUI/models/insightface/det_10g.onnx")
ARC_PATH = Path("D:/ComfyUI/models/insightface/w600k_r50.onnx")

# ArcFace 对齐模板（112x112）
ARCFACE_DST = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

STRIDES = (8, 16, 32)
VARIANCE = (0.1, 0.2)


def _generate_anchors(feat_map, stride, base=4.0):
    """RetinaFace 每位置 2 anchors（scale 1.0 / 2.0）"""
    fh, fw = feat_map
    anchors = []
    for i in range(fh):
        for j in range(fw):
            cx = (j + 0.5) * stride
            cy = (i + 0.5) * stride
            for s in (1.0, 2.0):
                w = base * stride * s
                h = base * stride * s
                anchors.append([cx, cy, w, h])
    return np.array(anchors, dtype=np.float32)


def _nms(boxes, scores, iou_thresh=0.45):
    if len(boxes) == 0:
        return []
    x1 = boxes[:, 0]; y1 = boxes[:, 1]; x2 = boxes[:, 2]; y2 = boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-12)
        order = order[1:][iou <= iou_thresh]
    return keep


class FaceEncoder:

    def __init__(self, det_path=DET_PATH, arc_path=ARC_PATH, input_size=640):
        self.det = ort.InferenceSession(str(det_path), providers=["CPUExecutionProvider"])
        self.arc = ort.InferenceSession(str(arc_path), providers=["CPUExecutionProvider"])
        self.input_size = input_size

    # ---------- 检测 ----------
    def detect(self, img_bgr):
        """返回 list[dict(bbox, kps, score)]（640 输入坐标）"""
        img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        h, w = img.shape[:2]
        scale = self.input_size / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(img, (new_w, new_h))
        canvas = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized
        blob = ((canvas.astype(np.float32) - 127.5) / 128.0).transpose(2, 0, 1)[None]

        out = self.det.run(None, {"input.1": blob})
        scores_all, bboxes_all, kps_all = [], [], []
        for i, stride in enumerate(STRIDES):
            s = out[i].reshape(-1)
            b = out[3 + i].reshape(-1, 4)
            k = out[6 + i].reshape(-1, 10)
            fm = self.input_size // stride
            anchors = _generate_anchors((fm, fm), stride)
            s = s[: len(anchors)]
            b = b[: len(anchors)]
            k = k[: len(anchors)]
            # decode（中心形式）
            cx = anchors[:, 0] - b[:, 0] * anchors[:, 2]
            cy = anchors[:, 1] - b[:, 1] * anchors[:, 3]
            w_ = anchors[:, 2] * np.exp(b[:, 2])
            h_ = anchors[:, 3] * np.exp(b[:, 3])
            box = np.stack([cx, cy, cx + w_, cy + h_], axis=1)
            kp = np.stack([
                anchors[:, 0] + k[:, 0] * anchors[:, 2],
                anchors[:, 1] + k[:, 1] * anchors[:, 3],
                anchors[:, 0] + k[:, 2] * anchors[:, 2],
                anchors[:, 1] + k[:, 3] * anchors[:, 3],
                anchors[:, 0] + k[:, 4] * anchors[:, 2],
                anchors[:, 1] + k[:, 5] * anchors[:, 3],
                anchors[:, 0] + k[:, 6] * anchors[:, 2],
                anchors[:, 1] + k[:, 7] * anchors[:, 3],
                anchors[:, 0] + k[:, 8] * anchors[:, 2],
                anchors[:, 1] + k[:, 9] * anchors[:, 3],
            ], axis=1)
            scores_all.append(s); bboxes_all.append(box); kps_all.append(kp)

        scores = np.concatenate(scores_all)
        boxes = np.concatenate(bboxes_all)
        kps = np.concatenate(kps_all)
        # 阈值 + NMS
        keep = np.where(scores > 0.5)[0]
        boxes, kps, scores = boxes[keep], kps[keep], scores[keep]
        keep = _nms(boxes, scores)
        faces = []
        for i in keep:
            bx = boxes[i] / scale
            kp = kps[i].reshape(5, 2) / scale
            faces.append({"bbox": bx, "kps": kp, "score": float(scores[i])})
        return faces

    # ---------- 对齐 + 编码 ----------
    def _align(self, img_bgr, kps):
        src = kps.astype(np.float32)
        M = cv2.estimateAffinePartial2D(src, ARCFACE_DST, method=cv2.LMEDS)[0]
        if M is None:
            M = cv2.getAffineTransform(src[:3], ARCFACE_DST[:3])
        aligned = cv2.warpAffine(img_bgr, M, (112, 112), borderValue=0.0)
        return aligned

    def embed_face(self, img_bgr, kps):
        aligned = self._align(img_bgr, kps)
        rgb = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB)
        blob = ((rgb.astype(np.float32) - 127.5) / 128.0).transpose(2, 0, 1)[None]
        out = self.arc.run(None, {"input.1": blob})[0][0]
        norm = out / (np.linalg.norm(out) + 1e-12)
        return norm

    def embed_image(self, img_bgr):
        """图片中最大人脸的 embedding；无人脸返回 None"""
        faces = self.detect(img_bgr)
        if not faces:
            return None, faces
        faces.sort(key=lambda f: f["score"], reverse=True)
        best = faces[0]
        return self.embed_face(img_bgr, best["kps"]), faces

    def cosine(self, a, b):
        return float(np.dot(a, b))

    def embed_video_faces(self, video_path, max_frames=8):
        """视频抽样人脸 embedding 列表"""
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 124
        embs = []
        for frac in np.linspace(0.15, 0.85, max_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * frac))
            ok, frame = cap.read()
            if not ok:
                continue
            e, _ = self.embed_image(frame)
            if e is not None:
                embs.append(e)
        cap.release()
        return embs


face_encoder = FaceEncoder()
