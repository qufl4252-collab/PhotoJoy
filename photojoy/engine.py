from dataclasses import dataclass
from pathlib import Path
import hashlib
import json

import cv2
import numpy as np

from .paths import digest, resource_root


@dataclass
class Face:
    bbox: list[float]
    landmarks: list[float]
    detection_score: float
    embedding: np.ndarray
    crop: np.ndarray


def normalize(value) -> np.ndarray:
    value = np.asarray(value, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(value))
    if not value.size or not np.all(np.isfinite(value)) or not np.isfinite(norm) or norm < 1e-8:
        raise ValueError("유효하지 않은 얼굴 특징입니다.")
    return value / norm


class SFaceEngine:
    name = "OpenCV YuNet + SFace"

    def __init__(self, model_dir: Path | None = None):
        self.model_dir = Path(model_dir) if model_dir else resource_root() / "models"
        self.detector = self.recognizer = None
        self.fingerprint = ""

    def load(self):
        if self.detector is not None:
            return
        manifest_path = resource_root() / "models" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        hashes = []
        for entry in manifest["models"]:
            path = self.model_dir / entry["file"]
            if not path.is_file():
                raise FileNotFoundError(f"얼굴 모델이 없습니다: {path}\n모델 준비 스크립트를 먼저 실행하세요.")
            value = digest(path)
            if value != entry["sha256"]:
                raise ValueError(f"모델 파일 검증에 실패했습니다: {path.name}")
            hashes.append(value)
        # OpenCV's native filename loader cannot reliably open Korean Windows paths.
        detection = np.frombuffer((self.model_dir / manifest["models"][0]["file"]).read_bytes(), dtype=np.uint8)
        recognition = np.frombuffer((self.model_dir / manifest["models"][1]["file"]).read_bytes(), dtype=np.uint8)
        empty = np.empty(0, dtype=np.uint8)
        detector = cv2.FaceDetectorYN.create("onnx", detection, empty, (320, 320), 0.85, 0.3, 5000)
        recognizer = cv2.FaceRecognizerSF.create("onnx", recognition, empty)
        self.detector, self.recognizer = detector, recognizer
        self.fingerprint = "sface-v1:" + hashlib.sha256(("|".join(hashes) + ":bgr-l2-resize1600").encode()).hexdigest()[:20]
        cv2.setNumThreads(2)

    def detect_and_embed(self, image_bgr) -> list[Face]:
        self.load()
        height, width = image_bgr.shape[:2]
        scale = min(1.0, 1600 / max(height, width))
        small = cv2.resize(image_bgr, (max(1, round(width * scale)), max(1, round(height * scale)))) if scale < 1 else image_bgr
        self.detector.setInputSize((small.shape[1], small.shape[0]))
        _, detected = self.detector.detect(small)
        if detected is None:
            return []
        result = []
        for row in detected:
            aligned = self.recognizer.alignCrop(small, row)
            embedding = normalize(self.recognizer.feature(aligned).copy())
            x, y, w, h = (row[:4] / scale).tolist()
            result.append(Face([max(0, x), max(0, y), min(width, x+w), min(height, y+h)], (row[4:14]/scale).tolist(), float(row[14]), embedding, aligned))
        return sorted(result, key=lambda f: -(f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))


class InsightFaceEngine:
    """Optional user-provided model adapter. Never downloads a model implicitly."""
    name = "InsightFace (사용자 모델)"

    def __init__(self, model_root: Path):
        self.root, self.app, self.fingerprint = Path(model_root), None, ""

    def load(self):
        if self.app is not None:
            return
        required = [self.root / "models" / "buffalo_l" / name for name in ("det_10g.onnx", "w600k_r50.onnx")]
        if not all(p.is_file() for p in required):
            raise FileNotFoundError("사용자 모델 폴더에 buffalo_l 검출·인식 모델 두 개가 필요합니다.")
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name="buffalo_l", root=str(self.root), allowed_modules=["detection", "recognition"], providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        self.app = app
        self.fingerprint = "insightface-v1:" + hashlib.sha256("|".join(digest(p) for p in required).encode()).hexdigest()[:20]

    def detect_and_embed(self, image_bgr):
        self.load()
        result = []
        from insightface.utils.face_align import norm_crop
        for face in self.app.get(image_bgr):
            result.append(Face(face.bbox.tolist(), face.kps.reshape(-1).tolist(), float(face.det_score), normalize(face.normed_embedding), norm_crop(image_bgr, face.kps)))
        return result


def compare(embedding, gallery: dict[str, list[np.ndarray]], threshold=.50, margin=.08):
    query = normalize(embedding)
    scores = []
    for child, refs in gallery.items():
        values = [float(query @ normalize(ref)) for ref in refs if np.asarray(ref).size == query.size]
        if values:
            scores.append((child, float(np.mean(sorted(values, reverse=True)[:3]))))
    scores.sort(key=lambda row: (-row[1], row[0]))
    if not scores:
        return {"child": None, "score": None, "runner_up": None, "accepted": False, "reason": "등록된 얼굴 특징 없음"}
    child, score = scores[0]
    runner = scores[1][1] if len(scores) > 1 else None
    accepted = score >= threshold + (0.08 if runner is None else 0) and (runner is None or score-runner >= margin)
    return {"child": child, "score": score, "runner_up": runner, "accepted": bool(accepted), "reason": "확인 필요 (실험 기준)" if accepted else "유사도 부족 또는 후보가 비슷함"}

