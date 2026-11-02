"""Download official model bytes and check their published Git LFS SHA-256."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "models/manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["models"]:
        destination = ROOT / "models" / entry["file"]
        if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == entry["sha256"]:
            print("Verified:", destination.name, flush=True)
            continue
        temporary = destination.with_suffix(".download")
        print("Downloading:", entry["file"], flush=True)
        request = urllib.request.Request(entry["url"], headers={"User-Agent": "PhotoJoy-model-setup/0.1"})
        with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as stream:
            while chunk := response.read(1024*1024):
                stream.write(chunk)
        if temporary.stat().st_size != entry["bytes"] or hashlib.sha256(temporary.read_bytes()).hexdigest() != entry["sha256"]:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Model validation failed: {entry['file']}")
        temporary.replace(destination)
        print("Verified:", destination.name, flush=True)
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    for directory, name in [("face_detection_yunet", "YuNet-MIT.txt"), ("face_recognition_sface", "SFace-Apache-2.0.txt")]:
        url = f"https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/{directory}/LICENSE"
        (licenses / name).write_bytes(urllib.request.urlopen(url, timeout=30).read())


if __name__ == "__main__":
    main()
