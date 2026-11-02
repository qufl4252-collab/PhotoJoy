"""Start the loopback server without a console, then open Chrome."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765"


def ready():
    try:
        with urlopen(URL + "/healthz", timeout=1) as response:
            return json.load(response).get("version") == "0.3.0"
    except Exception:
        return False


if not ready():
    logs = ROOT / "web-data"
    logs.mkdir(exist_ok=True)
    with (logs / "server.log").open("ab") as log:
        subprocess.Popen([sys.executable, str(ROOT / "run_web.py")], cwd=ROOT,
                         stdout=log, stderr=log,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(30):
        if ready():
            break
        time.sleep(.5)
if not ready():
    raise RuntimeError("PhotoJoy web server did not start; see web-data/server.log")
chrome = next((Path(os.environ[key]) / "Google/Chrome/Application/chrome.exe"
               for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
               if key in os.environ and (Path(os.environ[key]) / "Google/Chrome/Application/chrome.exe").is_file()), None)
if chrome:
    subprocess.Popen([str(chrome), URL])
else:
    webbrowser.open(URL)
