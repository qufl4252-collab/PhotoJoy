from pathlib import Path
import json
import threading

import numpy as np

from .engine import SFaceEngine, compare
from .media import read_frames, capture_date, save_preview, kind, MEDIA_EXT
from .paths import digest, uid, inside
from .store import Store, now


class Cancelled(Exception):
    pass


def checkpoint(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled("작업이 취소되었습니다. 완료된 항목은 보존됩니다.")


class Service:
    def __init__(self, store: Store, engine=None):
        self.store = store
        self.engine = engine or SFaceEngine()

    def registration_candidates(self, path: Path):
        self.engine.load()
        frame = next(read_frames(path))
        faces = self.engine.detect_and_embed(frame.image)
        return faces, digest(path)

    def register(self, child, path, face, index, source_hash):
        crop = inside(self.store.root, self.store.data / "references" / f"{uid()}.jpg")
        save_preview(face.crop, crop, 240)
        self.store.add_reference(child, face.embedding, self.engine.fingerprint, path, source_hash, index, crop)

    def expand(self, paths):
        results = []
        seen = set()
        for item in paths:
            path = Path(item).resolve()
            candidates = path.rglob("*") if path.is_dir() else [path]
            for candidate in candidates:
                if not candidate.is_file() or candidate.is_symlink() or candidate.suffix.lower() not in MEDIA_EXT:
                    continue
                resolved = candidate.resolve()
                if any(resolved.is_relative_to(self.store.root / folder) for folder in (".photojoy", "정리", "전송묶음", "백업")):
                    continue
                if str(resolved) not in seen:
                    seen.add(str(resolved))
                    results.append(resolved)
        return results

    def analyze(self, paths, progress=lambda *_: None, cancel=None):
        self.engine.load()
        gallery = self.store.gallery(self.engine.fingerprint)
        threshold = self.store.get_setting("threshold", .50)
        margin = self.store.get_setting("margin", .08)
        paths = self.expand(paths)
        result = {"analyzed": 0, "cached": 0, "errors": [], "total": len(paths)}
        for number, path in enumerate(paths, 1):
            checkpoint(cancel)
            progress(number-1, len(paths), f"분석: {path.name}")
            media_id = None
            try:
                sha = digest(path)
                existing = self.store.rows("SELECT * FROM media WHERE sha256=?", (sha,))
                if existing:
                    old = existing[0]
                    media_id = old["id"]
                    if not Path(old["path"]).exists():
                        self.store.execute("UPDATE media SET path=? WHERE id=?", (str(path), media_id))
                    if old["reviewed"] or (old["engine"] == self.engine.fingerprint and old["status"] != "error"):
                        if not old["reviewed"]:
                            self.rematch(media_id, gallery, threshold, margin)
                        result["cached"] += 1
                        continue
                else:
                    media_id = uid()
                    captured, source = capture_date(path)
                    self.store.execute("INSERT INTO media(id,path,sha256,kind,captured,date_source,created) VALUES (?,?,?,?,?,?,?)", (media_id, str(path), sha, kind(path), captured, source, now()))
                rows = []
                thumbnail = ""
                for frame_no, frame in enumerate(read_frames(path)):
                    checkpoint(cancel)
                    preview = inside(self.store.root, self.store.data / "previews" / f"{media_id}_{frame_no}.jpg")
                    save_preview(frame.image, preview)
                    thumbnail = thumbnail or str(preview)
                    height, width = frame.image.shape[:2]
                    for face in self.engine.detect_and_embed(frame.image):
                        face_id = uid()
                        crop = inside(self.store.root, self.store.data / "previews" / f"{face_id}_face.jpg")
                        save_preview(face.crop, crop, 160)
                        candidate = compare(face.embedding, gallery, threshold, margin)
                        if min(face.bbox[2]-face.bbox[0], face.bbox[3]-face.bbox[1]) < 45:
                            candidate.update(accepted=False, reason="작은 얼굴 — 직접 확인")
                        # Normalize box coordinates to keep overlays aligned with resized previews.
                        bbox = [face.bbox[0]/width, face.bbox[1]/height, face.bbox[2]/width, face.bbox[3]/height]
                        rows.append((face_id, media_id, json.dumps(bbox), face.embedding.astype(np.float32).tobytes(), face.embedding.size, self.engine.fingerprint, frame.time, str(preview), str(crop), json.dumps(candidate)))
                with self.store.connect() as con:
                    con.execute("DELETE FROM faces WHERE media_id=?", (media_id,))
                    con.executemany("INSERT INTO faces VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
                    con.execute("UPDATE media SET thumbnail=?,engine=?,status=?,error='' WHERE id=?", (thumbnail, self.engine.fingerprint, "review" if rows else "no_face", media_id))
                result["analyzed"] += 1
            except Cancelled:
                if media_id:
                    self.store.execute("UPDATE media SET status='error',error='분석 취소 — 다시 추가하여 재시도' WHERE id=? AND reviewed=0", (media_id,))
                raise
            except Exception as exc:
                result["errors"].append(f"{path.name}: {exc}")
                if media_id:
                    self.store.execute("UPDATE media SET status='error',error=? WHERE id=? AND reviewed=0", (str(exc), media_id))
            finally:
                progress(number, len(paths), f"분석 {number}/{len(paths)}")
        return result

    def rematch(self, media_id, gallery=None, threshold=None, margin=None):
        self.engine.load()
        gallery = self.store.gallery(self.engine.fingerprint) if gallery is None else gallery
        threshold = self.store.get_setting("threshold", .50) if threshold is None else threshold
        margin = self.store.get_setting("margin", .08) if margin is None else margin
        for face in self.store.faces(media_id):
            if face["engine"] != self.engine.fingerprint:
                continue
            vector = np.frombuffer(face["embedding"], dtype=np.float32)
            candidate = compare(vector, gallery, threshold, margin)
            previous = json.loads(face["candidate"])
            if previous["reason"].startswith("작은 얼굴"):
                candidate.update(accepted=False, reason=previous["reason"])
            self.store.execute("UPDATE faces SET candidate=? WHERE id=?", (json.dumps(candidate), face["id"]))

    def confirm_candidates(self, media_ids):
        valid = {c["id"] for c in self.store.children()}
        confirmed = []
        for media_id in media_ids:
            faces = self.store.faces(media_id)
            candidates = [json.loads(f["candidate"]) for f in faces]
            if not candidates or any(not c["accepted"] or c["child"] not in valid for c in candidates):
                raise ValueError("미확정 얼굴이 있습니다. 얼굴 후보를 확인하고 '직접 배정'을 사용하세요.")
            confirmed.append((media_id, list(dict.fromkeys(c["child"] for c in candidates))))
        for media_id, ids in confirmed:
            self.store.review([media_id], ids)

    def learn_face(self, face_id, child):
        row = self.store.rows("SELECT f.*,m.sha256,m.path FROM faces f JOIN media m ON m.id=f.media_id WHERE f.id=?", (face_id,))[0]
        # A stable face ID-derived index avoids conflating video frames or multiple people.
        index = int(face_id[:8], 16)
        self.store.add_reference(child, np.frombuffer(row["embedding"], dtype=np.float32), row["engine"], row["path"], row["sha256"], index, row["crop"])
