from pathlib import Path
from importlib import metadata
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / "licenses" / "dependencies"
target.mkdir(parents=True, exist_ok=True)
names = ["numpy", "opencv-python-headless", "Pillow", "PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "pi-heif", "pyinstaller"]
index = []
for name in names:
    dist = metadata.distribution(name)
    output = target / name
    output.mkdir(exist_ok=True)
    index.append(f"{name}=={dist.version} | {dist.metadata.get('Home-page', '')}")
    (output / "METADATA.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
    for relative in dist.files or []:
        text = str(relative).replace("\\", "/")
        if any(marker in text.lower() for marker in ("license", "copying", "copyright", "notice")):
            source = Path(dist.locate_file(relative))
            if source.is_file() and source.stat().st_size < 5_000_000:
                destination = output / text.replace("/", "__").replace("..", "_")
                shutil.copyfile(source, destination)
(target / "INDEX.txt").write_text("\n".join(index), encoding="utf-8")
for path in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
    if path.is_file():
        shutil.copyfile(path, target / "Python-LICENSE.txt")
print(f"Collected notices in {target}")
