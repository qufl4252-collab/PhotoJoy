"""Download two public reference images for the optional real-inference smoke test."""
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = {
    "astronaut.png": (
        "https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/astronaut.png",
        "88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5",
    ),
    "grace_hopper.jpg": (
        "https://raw.githubusercontent.com/matplotlib/matplotlib/v3.10.7/lib/matplotlib/mpl-data/sample_data/grace_hopper.jpg",
        "a8ca6d734765703b09728ab47fe59f473d93ae3967fc24c7c0288c3c7adb7130",
    ),
}


def main():
    folder = ROOT / "test-output/fixtures"
    folder.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in SAMPLES.items():
        target = folder / name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            print(f"Ready: {name}")
            continue
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Sample hash mismatch: {name}")
        part = target.with_suffix(target.suffix + ".part")
        part.write_bytes(data)
        part.replace(target)
        print(f"Downloaded: {name}")


if __name__ == "__main__":
    main()
