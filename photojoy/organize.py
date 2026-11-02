from pathlib import Path
import json
import os
import shutil

from .media import period
from .paths import available_path, digest, inside, safe_name, uid
from .service import checkpoint, Cancelled
from .store import now


class Organizer:
    def __init__(self, store):
        self.store = store

    def plan(self, media_ids, unit="day"):
        children = {c["id"]: c for c in self.store.children()}
        operations, skipped = [], 0
        for media_id in dict.fromkeys(media_ids):
            media = self.store.one_media(media_id)
            if not media["reviewed"] or media["status"] != "confirmed":
                continue
            source = Path(media["path"])
            for child_id in json.loads(media["assignments"]):
                if child_id not in children:
                    continue
                previous = self.store.rows("SELECT * FROM file_operations WHERE media_id=? AND child_id=? AND state='done'", (media_id, child_id))
                if previous:
                    # Do not duplicate an already organized photo after a child rename.
                    valid = any(Path(row["destination"]).is_file() and digest(Path(row["destination"])) == media["sha256"] for row in previous)
                    if valid:
                        skipped += 1
                        continue
                    raise ValueError(f"기존 정리 결과가 없거나 변경되었습니다: {source.name}. 작업 이력을 확인하세요.")
                folder = f"{safe_name(children[child_id]['name'])}_{child_id[:6]}"
                filename = f"{media['captured']}_{safe_name(source.stem, 60)}_{media['sha256'][:10]}{source.suffix.lower()}"
                target = inside(self.store.root, self.store.root / "정리" / folder / period(media["captured"], unit) / filename)
                target = available_path(target)
                operations.append(dict(id=uid(), media_id=media_id, child_id=child_id, source=str(source), destination=str(target), sha256=media["sha256"]))
        return {"unit": unit, "operations": operations, "skipped": skipped}

    def create_batch(self, plan):
        if not plan["operations"]:
            raise ValueError("새로 정리할 확인 완료 자료가 없습니다.")
        batch = uid()
        with self.store.connect() as con:
            con.execute("INSERT INTO batches VALUES (?,?,?)", (batch, now(), plan["unit"]))
            for op in plan["operations"]:
                con.execute("INSERT INTO file_operations VALUES (?,?,?,?,?,?,?,?,?)", (op["id"], batch, op["media_id"], op["child_id"], op["source"], op["destination"], op["sha256"], "planned", ""))
        return batch

    def _state(self, operation, state, error=""):
        self.store.execute("UPDATE file_operations SET state=?,error=? WHERE id=?", (state, error, operation))

    def run(self, batch, progress=lambda *_: None, cancel=None):
        operations = self.store.rows("SELECT * FROM file_operations WHERE batch_id=? ORDER BY rowid", (batch,))
        result = {"done": 0, "errors": [], "batch": batch}
        for index, op in enumerate(operations, 1):
            checkpoint(cancel)
            if op["state"] in ("done", "undone", "undoing"):
                continue
            progress(index-1, len(operations), f"정리: {Path(op['source']).name}")
            temporary = None
            try:
                target = inside(self.store.root, Path(op["destination"]))
                temporary = inside(self.store.root, target.with_name(f".photojoy-{op['id']}.part"))
                source = Path(op["source"])
                # A prepared operation may have completed its atomic rename before interruption.
                if op["state"] == "prepared" and target.is_file() and not temporary.exists() and digest(target) == op["sha256"]:
                    self._state(op["id"], "done")
                    result["done"] += 1
                    continue
                media = self.store.one_media(op["media_id"])
                if not media["reviewed"] or media["status"] != "confirmed" or op["child_id"] not in json.loads(media["assignments"]):
                    raise ValueError("검토 내용이 변경되었습니다. 새 정리 계획을 만드세요.")
                if not any(c["id"] == op["child_id"] for c in self.store.children()):
                    raise ValueError("졸업 처리된 아이입니다. 새 정리 계획을 만드세요.")
                if not source.is_file() or digest(source) != op["sha256"]:
                    raise ValueError("원본이 없거나 분석 후 내용이 바뀌었습니다.")
                if target.exists():
                    raise FileExistsError("대상 파일이 이미 있습니다. 덮어쓰지 않았습니다.")
                target.parent.mkdir(parents=True, exist_ok=True)
                inside(self.store.root, target)
                if shutil.disk_usage(target.parent).free < source.stat().st_size + 1024*1024:
                    raise OSError("저장 공간이 부족합니다.")
                self._state(op["id"], "copying")
                temporary.unlink(missing_ok=True)
                with source.open("rb") as inp, temporary.open("xb") as out:
                    while block := inp.read(1024*1024):
                        checkpoint(cancel)
                        out.write(block)
                    out.flush()
                    os.fsync(out.fileno())
                if digest(temporary) != op["sha256"]:
                    raise ValueError("복사 결과 해시가 일치하지 않습니다.")
                shutil.copystat(source, temporary)
                checkpoint(cancel)
                self._state(op["id"], "prepared")
                if target.exists():
                    raise FileExistsError("정리 중 같은 이름의 파일이 생겼습니다.")
                # Windows rename refuses to overwrite an existing destination.
                temporary.rename(target)
                self._state(op["id"], "done")
                result["done"] += 1
            except Cancelled:
                if temporary:
                    temporary.unlink(missing_ok=True)
                self._state(op["id"], "cancelled", "사용자 취소")
                raise
            except Exception as exc:
                if temporary:
                    temporary.unlink(missing_ok=True)
                self._state(op["id"], "error", str(exc))
                result["errors"].append(f"{Path(op['source']).name}: {exc}")
            progress(index, len(operations), f"정리 {index}/{len(operations)}")
        return result

    def undo(self, batch, progress=lambda *_: None, cancel=None):
        operations = self.store.rows("SELECT * FROM file_operations WHERE batch_id=? AND state IN ('done','undoing')", (batch,))
        result = {"undone": 0, "errors": []}
        for index, op in enumerate(operations, 1):
            checkpoint(cancel)
            try:
                target = inside(self.store.root, Path(op["destination"]))
                source = Path(op["source"])
                if not source.is_file() or digest(source) != op["sha256"]:
                    raise ValueError("원본이 없거나 달라져 정리본을 보존했습니다.")
                if target.exists() and digest(target) != op["sha256"]:
                    raise ValueError("정리 후 수정된 파일이므로 보존했습니다.")
                self._state(op["id"], "undoing")
                target.unlink(missing_ok=True)
                self._state(op["id"], "undone")
                result["undone"] += 1
            except Exception as exc:
                result["errors"].append(f"{Path(op['destination']).name}: {exc}")
            progress(index, len(operations), "정리 되돌리는 중")
        return result

