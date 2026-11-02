# PyInstaller onedir: models and notices travel with the executable.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'run_photojoy.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'models'), 'models'), (str(root / 'licenses'), 'licenses'), (str(root / 'README.md'), '.')],
    hiddenimports=['pi_heif'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'torch', 'insightface'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PhotoJoy', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PhotoJoy')
