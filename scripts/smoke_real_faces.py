"""Real CPU inference and full workflow using two public reference sample photos.

This verifies plumbing, not accuracy on independent photos or children.
"""
from pathlib import Path
import json
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
from PIL import Image, ImageEnhance
from photojoy.engine import SFaceEngine, compare
from photojoy.media import read_image
from photojoy.service import Service
from photojoy.store import Store
from photojoy.paths import digest, uid
from photojoy.organize import Organizer
from photojoy.exporting import make_zips, backup


def main():
    started = time.perf_counter()
    fixture = ROOT / "test-output/fixtures"
    run = ROOT / "test-output" / ("실제얼굴_" + uid()[:8])
    run.mkdir(parents=True)
    inputs = run / "입력 사진"
    inputs.mkdir()
    store = Store(run / "사진 보관함")
    engine = SFaceEngine()
    service = Service(store, engine)
    children, faces = [], []
    for name, filename in [("샘플 A", "astronaut.png"), ("샘플 B", "grace_hopper.jpg")]:
        child = store.add_child(name)
        source = fixture / filename
        candidates, sha = service.registration_candidates(source)
        assert candidates, f"No face: {filename}"
        service.register(child, source, candidates[0], 0, sha)
        children.append(child)
        faces.append(candidates[0])
    same = float(faces[0].embedding @ faces[0].embedding)
    different = float(faces[0].embedding @ faces[1].embedding)
    gallery = store.gallery(engine.fingerprint)
    assert compare(faces[0].embedding, gallery)["child"] == children[0]
    assert compare(faces[1].embedding, gallery)["child"] == children[1]
    assert not compare(faces[1].embedding, {children[0]: gallery[children[0]]})["accepted"]
    for index, filename in enumerate(("astronaut.png", "grace_hopper.jpg")):
        with Image.open(fixture / filename) as source:
            adjusted = ImageEnhance.Brightness(source.convert("RGB")).enhance(.92)
            adjusted.save(inputs / f"20261102_검증{index}.jpg", quality=90)
    group = Image.new("RGB", (1024, 600), "white")
    for index, filename in enumerate(("astronaut.png", "grace_hopper.jpg")):
        with Image.open(fixture / filename) as source:
            source = source.convert("RGB")
            source.thumbnail((512, 600))
            group.paste(source, (index*512, 0))
    group.save(inputs / "20261102_단체.jpg", quality=95)
    Image.new("RGB", (640, 480), "gray").save(inputs / "얼굴없음.jpg")
    # Generated test clip from a public sample; not a real-world video accuracy test.
    video = inputs / "테스트 영상.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (512, 512))
    assert writer.isOpened()
    image = read_image(fixture / "astronaut.png")
    for _ in range(20):
        writer.write(image)
    writer.release()
    original_hashes = {str(p): digest(p) for p in inputs.iterdir()}
    result = service.analyze([inputs])
    assert not result["errors"], result
    media = store.media()
    confirmed = []
    for row in media:
        if row["status"] == "no_face":
            continue
        candidates = [json.loads(f["candidate"]) for f in store.faces(row["id"])]
        assert all(c["accepted"] for c in candidates), (row["path"], candidates)
        service.confirm_candidates([row["id"]])
        confirmed.append(row["id"])
        if "단체" in row["path"]:
            assert set(json.loads(store.one_media(row["id"])["assignments"])) == set(children)
    assert len(confirmed) == 4
    organizer = Organizer(store)
    plan = organizer.plan(confirmed, "week")
    batch = organizer.create_batch(plan)
    copied = organizer.run(batch)
    assert not copied["errors"] and copied["done"] == 5, copied
    assert organizer.plan(confirmed)["skipped"] == 5
    zips = make_zips(store, children, "2000-01-01", "2100-01-01")
    assert len(zips["paths"]) == 2
    zip_counts = []
    for path in zips["paths"]:
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            zip_counts.append(len(archive.namelist()))
    assert sorted(zip_counts) == [2, 3]
    backup_path = backup(store)
    for path, sha in original_hashes.items():
        assert digest(Path(path)) == sha
    cached = service.analyze([inputs])
    assert cached["cached"] == 5
    summary = dict(engine=engine.fingerprint, same_image_score=same, different_sample_score=different,
        analyzed=result, copied=copied, zip_counts=zip_counts, stats=store.statistics(),
        backup=backup_path, originals_unchanged=True, seconds=round(time.perf_counter()-started,2),
        limitations="Two public adult sample photos and derived images/video. Not an independent identity/child accuracy benchmark.", library=str(store.root))
    (run / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "test-output/latest-smoke.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
