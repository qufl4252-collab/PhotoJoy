from datetime import datetime
from contextlib import closing
from pathlib import Path
import csv
import io
import json
import os
import sqlite3
import zipfile

from PIL import Image, ImageOps

from .paths import available_path, digest, inside, safe_name, uid
from .service import checkpoint
from .store import now


def csv_cell(value):
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def export_csv(store, path, start, end):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["아이 ID", "이름", "사진 수", "영상 수", "합계", "시작", "끝"])
        for child in store.statistics(start, end):
            writer.writerow([child["id"], csv_cell(child["name"]), child["photos"], child["videos"], child["photos"]+child["videos"], start, end])


def media_source(store, row):
    original = Path(row["path"])
    if original.is_file() and digest(original) == row["sha256"]:
        return original
    for operation in store.rows("SELECT * FROM file_operations WHERE media_id=? AND state='done'", (row["id"],)):
        candidate = inside(store.root, Path(operation["destination"]))
        if candidate.is_file() and digest(candidate) == row["sha256"]:
            return candidate
    raise ValueError(f"원본 또는 검증된 정리본이 없습니다: {original.name}")


def watermarked(source, logo_path):
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    with Image.open(logo_path) as opened:
        logo = opened.convert("RGBA")
    logo.thumbnail((max(1, image.width//5), max(1, image.height//5)), Image.Resampling.LANCZOS)
    pad = max(4, min(image.size)//40)
    image.alpha_composite(logo, (image.width-logo.width-pad, image.height-logo.height-pad))
    output = io.BytesIO()
    image.convert("RGB").save(output, "JPEG", quality=95)
    return output.getvalue()


def make_zips(store, child_ids, start, end, logo=None, progress=lambda *_: None, cancel=None):
    rows = store.confirmed(start, end)
    children = [c for c in store.children() if c["id"] in child_ids]
    output = inside(store.root, store.root / "전송묶음")
    output.mkdir(exist_ok=True)
    result = {"paths": [], "errors": []}
    for index, child in enumerate(children, 1):
        checkpoint(cancel)
        selected = [m for m in rows if child["id"] in json.loads(m["assignments"])]
        if not selected:
            continue
        target = available_path(inside(store.root, output / f"{safe_name(child['name'])}_{child['id'][:6]}_{start}_{end}.zip"))
        temporary = target.with_name(f".{uid()}.part")
        try:
            with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                for n, media in enumerate(selected, 1):
                    checkpoint(cancel)
                    progress(n, len(selected), f"{child['name']} ZIP {n}/{len(selected)}")
                    source = media_source(store, media)
                    extension = ".jpg" if logo and media["kind"] == "photo" else source.suffix.lower()
                    name = f"{media['captured']}/{safe_name(source.stem,60)}_{media['sha256'][:10]}{extension}"
                    if logo and media["kind"] == "photo":
                        archive.writestr(name, watermarked(source, logo))
                    else:
                        archive.write(source, name)
            with zipfile.ZipFile(temporary) as archive:
                if archive.testzip() is not None:
                    raise ValueError("ZIP 검증에 실패했습니다.")
            temporary.rename(target)
            store.execute("INSERT INTO exports VALUES (?,?,?,?,?,?,?,NULL)", (uid(), child["id"], start, end, str(target), len(selected), now()))
            result["paths"].append(str(target))
        finally:
            temporary.unlink(missing_ok=True)
    return result


def backup(store):
    folder = inside(store.root, store.root / "백업")
    folder.mkdir(exist_ok=True)
    target = available_path(folder / f"PhotoJoy_{datetime.now():%Y%m%d_%H%M%S}.zip")
    snapshot = inside(store.root, store.data / f"backup-{uid()}.sqlite3")
    temporary = target.with_suffix(".part")
    try:
        with store.connect() as source, closing(sqlite3.connect(snapshot)) as dest:
            source.backup(dest)
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "photojoy.sqlite3")
            archive.writestr("backup.json", json.dumps({"format": 1, "created": now(), "root": str(store.root), "includes_originals": False}))
            for folder_name in ("references", "previews"):
                for file in (store.data / folder_name).glob("*.jpg"):
                    inside(store.root, file)
                    archive.write(file, str(file.relative_to(store.data)))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip():
                raise ValueError("백업 검증 실패")
        temporary.rename(target)
        return str(target)
    finally:
        snapshot.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
