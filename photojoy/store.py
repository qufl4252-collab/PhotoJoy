from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import json
import sqlite3

import numpy as np

from .paths import inside, uid


def now():
    return datetime.now().isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS children (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, group_name TEXT NOT NULL DEFAULT '',
 active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reference_faces (
 id TEXT PRIMARY KEY, child_id TEXT NOT NULL REFERENCES children(id), engine TEXT NOT NULL,
 embedding BLOB NOT NULL, dimension INTEGER NOT NULL, source TEXT NOT NULL, source_hash TEXT NOT NULL,
 face_index INTEGER NOT NULL, crop TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL,
 UNIQUE(child_id, engine, source_hash, face_index));
CREATE TABLE IF NOT EXISTS media (
 id TEXT PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
 captured TEXT NOT NULL, date_source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'review',
 error TEXT NOT NULL DEFAULT '', thumbnail TEXT NOT NULL DEFAULT '', engine TEXT NOT NULL DEFAULT '',
 assignments TEXT NOT NULL DEFAULT '[]', reviewed INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS faces (
 id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
 bbox TEXT NOT NULL, embedding BLOB NOT NULL, dimension INTEGER NOT NULL,
 engine TEXT NOT NULL, frame REAL, preview TEXT NOT NULL, crop TEXT NOT NULL, candidate TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS corrections (
 id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id), before_json TEXT NOT NULL,
 after_json TEXT NOT NULL, created TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS batches (
 id TEXT PRIMARY KEY, created TEXT NOT NULL, unit TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS file_operations (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id), media_id TEXT NOT NULL REFERENCES media(id),
 child_id TEXT NOT NULL REFERENCES children(id), source TEXT NOT NULL, destination TEXT NOT NULL,
 sha256 TEXT NOT NULL, state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS exports (
 id TEXT PRIMARY KEY, child_id TEXT NOT NULL REFERENCES children(id), start TEXT NOT NULL, end TEXT NOT NULL,
 path TEXT NOT NULL, file_count INTEGER NOT NULL, created TEXT NOT NULL, sent_at TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS faces_media ON faces(media_id);
CREATE INDEX IF NOT EXISTS operation_media ON file_operations(media_id,child_id,state);
"""


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.data = inside(self.root, self.root / ".photojoy")
        self.data.mkdir(exist_ok=True)
        self.db = self.data / "photojoy.sqlite3"
        for name in ("previews", "references"):
            inside(self.root, self.data / name).mkdir(exist_ok=True)
        with self.connect() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("이 데이터는 더 최신 PhotoJoy에서 생성되었습니다.")
            con.executescript(SCHEMA)
            con.execute("PRAGMA user_version=1")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def rows(self, sql, params=()):
        with self.connect() as con:
            return [dict(row) for row in con.execute(sql, params)]

    def execute(self, sql, params=()):
        with self.connect() as con:
            con.execute(sql, params)

    def get_setting(self, key, default):
        found = self.rows("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(found[0]["value"]) if found else default

    def set_setting(self, key, value):
        self.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def children(self, include_archived=False):
        return self.rows("SELECT c.*, (SELECT COUNT(*) FROM reference_faces r WHERE r.child_id=c.id AND r.active=1) AS refs FROM children c " + ("" if include_archived else "WHERE active=1 ") + "ORDER BY name,id")

    def add_child(self, name, group=""):
        if not name.strip():
            raise ValueError("이름을 입력하세요.")
        child = uid()
        self.execute("INSERT INTO children(id,name,group_name,created) VALUES (?,?,?,?)", (child, name.strip(), group.strip(), now()))
        return child

    def update_child(self, child, name, group, active):
        if not name.strip():
            raise ValueError("이름을 입력하세요.")
        self.execute("UPDATE children SET name=?,group_name=?,active=? WHERE id=?", (name.strip(), group.strip(), int(active), child))

    def add_reference(self, child, embedding, engine, source, source_hash, index, crop):
        values = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if not np.all(np.isfinite(values)) or not values.size:
            raise ValueError("얼굴 특징이 유효하지 않습니다.")
        self.execute("INSERT INTO reference_faces VALUES (?,?,?,?,?,?,?,?,?,1,?) ON CONFLICT(child_id,engine,source_hash,face_index) DO UPDATE SET active=1, crop=excluded.crop",
                     (uid(), child, engine, values.tobytes(), len(values), str(source), source_hash, index, str(crop), now()))

    def gallery(self, engine):
        result = {}
        for row in self.rows("SELECT r.* FROM reference_faces r JOIN children c ON c.id=r.child_id WHERE r.active=1 AND c.active=1 AND r.engine=?", (engine,)):
            vector = np.frombuffer(row["embedding"], dtype=np.float32).copy()
            if vector.size == row["dimension"] and np.all(np.isfinite(vector)):
                result.setdefault(row["child_id"], []).append(vector)
        return result

    def media(self):
        return self.rows("SELECT * FROM media ORDER BY created DESC,path")

    def one_media(self, media_id):
        found = self.rows("SELECT * FROM media WHERE id=?", (media_id,))
        if not found:
            raise ValueError("미디어를 찾을 수 없습니다.")
        return found[0]

    def faces(self, media_id):
        return self.rows("SELECT * FROM faces WHERE media_id=? ORDER BY frame,id", (media_id,))

    def review(self, media_ids, child_ids, excluded=False):
        ids = list(dict.fromkeys(child_ids))
        valid = {c["id"] for c in self.children()}
        if any(child not in valid for child in ids):
            raise ValueError("졸업 처리되었거나 없는 아이가 포함되었습니다.")
        if not ids and not excluded:
            raise ValueError("배정할 아이를 선택하세요.")
        with self.connect() as con:
            for media_id in media_ids:
                row = dict(con.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone())
                before = {k: row[k] for k in ("assignments", "reviewed", "status")}
                after = {"assignments": json.dumps(ids), "reviewed": 1, "status": "excluded" if excluded else "confirmed"}
                con.execute("INSERT INTO corrections VALUES (?,?,?,?,?,0)", (uid(), media_id, json.dumps(before), json.dumps(after), now()))
                con.execute("UPDATE media SET assignments=?,reviewed=?,status=? WHERE id=?", (after["assignments"], 1, after["status"], media_id))

    def undo_review(self, media_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM corrections WHERE media_id=? AND undone=0 ORDER BY rowid DESC LIMIT 1", (media_id,)).fetchone()
            if not row:
                raise ValueError("되돌릴 교정 기록이 없습니다.")
            before = json.loads(row["before_json"])
            con.execute("UPDATE media SET assignments=?,reviewed=?,status=? WHERE id=?", (before["assignments"], before["reviewed"], before["status"], media_id))
            con.execute("UPDATE corrections SET undone=1 WHERE id=?", (row["id"],))

    def confirmed(self, start="0001-01-01", end="9999-12-31"):
        return self.rows("SELECT * FROM media WHERE reviewed=1 AND status='confirmed' AND captured BETWEEN ? AND ? ORDER BY captured,path", (start, end))

    def statistics(self, start="0001-01-01", end="9999-12-31"):
        counts = {c["id"]: dict(c, photos=0, videos=0) for c in self.children()}
        for media in self.confirmed(start, end):
            for child in json.loads(media["assignments"]):
                if child in counts:
                    counts[child]["photos" if media["kind"] == "photo" else "videos"] += 1
        return list(counts.values())

