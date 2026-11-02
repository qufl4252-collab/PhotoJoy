from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
import re

import cv2
import numpy as np
from PIL import Image, ImageOps

try:
    from pi_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts"}
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT


@dataclass
class Frame:
    image: np.ndarray
    time: float | None = None


def kind(path: Path) -> str:
    if path.suffix.lower() in IMAGE_EXT:
        return "photo"
    if path.suffix.lower() in VIDEO_EXT:
        return "video"
    raise ValueError("지원하지 않는 형식입니다.")


def read_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def read_frames(path: Path, samples: int = 8):
    if kind(path) == "photo":
        yield Frame(read_image(path))
        return
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("동영상을 열 수 없습니다. 경로 또는 코덱을 확인하세요.")
    try:
        total, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
        if not np.isfinite(total) or total < 1:
            total = 1
        if not np.isfinite(fps) or fps <= 0:
            fps = 30.0
        positions = sorted(set(np.linspace(0, max(0, int(total) - 1), min(samples, int(total)), dtype=int)))
        found = False
        for position in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(position))
            ok, frame = cap.read()
            if ok:
                found = True
                yield Frame(frame, float(position / fps))
        if not found:
            raise ValueError("동영상 프레임을 읽을 수 없습니다.")
    finally:
        cap.release()


def capture_date(path: Path) -> tuple[str, str]:
    if path.suffix.lower() in IMAGE_EXT:
        try:
            with Image.open(path) as image:
                exif = image.getexif()
                try:
                    details = exif.get_ifd(34665)
                except (KeyError, TypeError):
                    details = {}
                for tag in (36867, 36868, 306):
                    raw = details.get(tag) or exif.get(tag)
                    if raw:
                        parsed = datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S")
                        return parsed.date().isoformat(), "EXIF 촬영일"
        except Exception:
            pass
    for match in re.finditer(r"(?<!\d)((?:19|20)\d{2})[-_.]?([01]\d)[-_.]?([0-3]\d)(?!\d)", path.stem):
        try:
            parsed = date(*map(int, match.groups()))
            if parsed.year <= date.today().year + 1:
                return parsed.isoformat(), "파일명"
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat(), "파일 수정 시각"


def period(value: str, unit: str) -> str:
    d = date.fromisoformat(value)
    if unit == "week":
        week = (d.day - 1 + d.replace(day=1).weekday()) // 7 + 1
        return f"{d.year}-{d.month:02d}월{week}주차"
    return d.isoformat()


def save_preview(image_bgr, path: Path, edge: int = 1200):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    image.save(path, "JPEG", quality=88)

