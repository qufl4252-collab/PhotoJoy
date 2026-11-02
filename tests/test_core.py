from pathlib import Path
import json
import threading
import zipfile

import numpy as np
import pytest
from PIL import Image

from photojoy.engine import compare, normalize
from photojoy.media import period, capture_date
from photojoy.organize import Organizer
from photojoy.exporting import make_zips, backup, export_csv
from photojoy.paths import digest, inside, safe_name, uid
from photojoy.service import Cancelled
from photojoy.store import Store, now


@pytest.fixture
def library(tmp_path):
    store = Store(tmp_path / "한글 작업 폴더")
    child = store.add_child("테스트 아이")
    source = tmp_path / "원본 20261102.jpg"
    Image.new("RGB", (80, 60), "orange").save(source)
    media_id = uid()
    store.execute("INSERT INTO media(id,path,sha256,kind,captured,date_source,created) VALUES (?,?,?,?,?,?,?)", (media_id, str(source), digest(source), "photo", "2026-11-02", "파일명", now()))
    store.review([media_id], [child])
    return store, child, source, media_id


def test_match_ambiguity_unknown_and_single():
    gallery = {"a": [np.array([1., 0.])], "b": [np.array([0., 1.])]}
    assert compare([1, 0], gallery)["child"] == "a"
    assert compare([1, 0], gallery)["accepted"]
    assert not compare([1, 1], gallery)["accepted"]
    assert not compare([-1, -1], gallery)["accepted"]
    assert not compare([0, 1], {"a": gallery["a"]})["accepted"]
    assert not compare([1, 0], {})["accepted"]
    with pytest.raises(ValueError):
        normalize([np.nan, 1])
    with pytest.raises(ValueError):
        normalize([0, 0])


def test_calendar_names_and_containment(tmp_path):
    assert period("2026-11-01", "week") == "2026-11월1주차"
    assert period("2026-11-02", "week") == "2026-11월2주차"
    assert period("2026-12-31", "day") == "2026-12-31"
    assert safe_name("CON.txt") == "_CON.txt"
    assert "/" not in safe_name("../한글/아이")
    with pytest.raises(ValueError):
        inside(tmp_path, tmp_path / ".." / "escape")


def test_date_exif_precedence(tmp_path):
    path = tmp_path / "20261102.jpg"
    image = Image.new("RGB", (20, 30))
    exif = Image.Exif()
    exif[36867] = "2025:08:03 10:12:00"
    image.save(path, exif=exif)
    assert capture_date(path) == ("2025-08-03", "EXIF 촬영일")


def test_review_undo_and_archived(library):
    store, child, source, media_id = library
    store.review([media_id], [], excluded=True)
    assert store.one_media(media_id)["status"] == "excluded"
    store.undo_review(media_id)
    assert json.loads(store.one_media(media_id)["assignments"]) == [child]
    store.update_child(child, "동명이인", "형제", False)
    with pytest.raises(ValueError):
        store.review([media_id], [child])


def test_reference_engine_separation(library):
    store, child, source, media_id = library
    store.add_reference(child, [1., 0.], "engine-a", source, digest(source), 0, "")
    assert child in store.gallery("engine-a")
    assert store.gallery("engine-b") == {}
    store.execute("UPDATE reference_faces SET active=0")
    assert store.gallery("engine-a") == {}


def test_safe_copy_idempotence_undo(library):
    store, child, source, media_id = library
    before = digest(source)
    organizer = Organizer(store)
    plan = organizer.plan([media_id], "week")
    batch = organizer.create_batch(plan)
    assert organizer.run(batch)["done"] == 1
    target = Path(plan["operations"][0]["destination"])
    assert digest(target) == before == digest(source)
    assert organizer.plan([media_id])["skipped"] == 1
    assert organizer.run(batch)["done"] == 0
    assert organizer.undo(batch)["undone"] == 1
    assert not target.exists() and digest(source) == before


def test_changed_source_is_not_copied(library):
    store, child, source, media_id = library
    organizer = Organizer(store)
    plan = organizer.plan([media_id])
    batch = organizer.create_batch(plan)
    source.write_bytes(b"changed")
    assert organizer.run(batch)["errors"]
    assert not Path(plan["operations"][0]["destination"]).exists()
    assert source.read_bytes() == b"changed"


def test_target_conflict_is_not_owned(library):
    store, child, source, media_id = library
    organizer = Organizer(store)
    plan = organizer.plan([media_id])
    batch = organizer.create_batch(plan)
    target = Path(plan["operations"][0]["destination"])
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    assert organizer.run(batch)["errors"]
    assert organizer.undo(batch)["undone"] == 0
    assert target.exists()


def test_modified_output_is_preserved(library):
    store, child, source, media_id = library
    organizer = Organizer(store)
    plan = organizer.plan([media_id])
    batch = organizer.create_batch(plan)
    organizer.run(batch)
    target = Path(plan["operations"][0]["destination"])
    target.write_bytes(b"user edit")
    assert organizer.undo(batch)["errors"]
    assert target.read_bytes() == b"user edit"


def test_missing_original_prevents_deleting_only_copy(library):
    store, child, source, media_id = library
    organizer = Organizer(store)
    plan = organizer.plan([media_id])
    batch = organizer.create_batch(plan)
    organizer.run(batch)
    source.unlink()
    assert organizer.undo(batch)["errors"]
    assert Path(plan["operations"][0]["destination"]).exists()


def test_interrupted_copy_retry(library, monkeypatch):
    store, child, source, media_id = library
    organizer = Organizer(store)
    plan = organizer.plan([media_id])
    batch = organizer.create_batch(plan)
    import photojoy.organize as module
    real = module.os.fsync
    monkeypatch.setattr(module.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("simulated disk failure")))
    assert organizer.run(batch)["errors"]
    assert source.exists()
    assert not Path(plan["operations"][0]["destination"]).exists()
    monkeypatch.setattr(module.os, "fsync", real)
    assert organizer.run(batch)["done"] == 1


def test_recover_after_rename_before_commit(library):
    store, child, source, media_id = library
    organizer = Organizer(store)
    plan = organizer.plan([media_id])
    batch = organizer.create_batch(plan)
    op = plan["operations"][0]
    target = Path(op["destination"])
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    store.execute("UPDATE file_operations SET state='prepared' WHERE id=?", (op["id"],))
    assert organizer.run(batch)["done"] == 1


def test_cancel_preserves_source(library):
    store, child, source, media_id = library
    organizer = Organizer(store)
    batch = organizer.create_batch(organizer.plan([media_id]))
    event = threading.Event()
    event.set()
    with pytest.raises(Cancelled):
        organizer.run(batch, cancel=event)
    assert source.exists()


def test_exports_watermark_stats_backup(library, tmp_path):
    store, child, source, media_id = library
    before = digest(source)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (10, 10), (255, 0, 0, 180)).save(logo)
    result = make_zips(store, [child], "2026-01-01", "2026-12-31", logo)
    with zipfile.ZipFile(result["paths"][0]) as archive:
        assert len(archive.namelist()) == 1
        assert archive.testzip() is None
    assert digest(source) == before
    assert store.statistics()[0]["photos"] == 1
    assert store.rows("SELECT sent_at FROM exports")[0]["sent_at"] is None
    with zipfile.ZipFile(backup(store)) as archive:
        assert "photojoy.sqlite3" in archive.namelist()
        assert not json.loads(archive.read("backup.json"))["includes_originals"]
    csv = tmp_path / "stats.csv"
    store.update_child(child, "=HYPERLINK()", "", True)
    export_csv(store, csv, "2026-01-01", "2026-12-31")
    assert "'=HYPERLINK()" in csv.read_text(encoding="utf-8-sig")
