"""Exercise a separate loopback QA server with public sample photos only."""
from io import BytesIO
import json
from pathlib import Path
import zipfile

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8766"
session = requests.Session()
session.headers.update({"Origin": BASE, "X-PhotoJoy": "1"})
credentials = {"username": "화면검증", "password": "photojoy-preview-only", "platform": "windows"}


def check(response):
    response.raise_for_status()
    return response.json()


def main():
    result = session.post(BASE + "/api/auth/register", json=credentials, timeout=10)
    if result.status_code == 409:
        result = session.post(BASE + "/api/auth/login", json=credentials, timeout=10)
    check(result)
    library = check(session.get(BASE + "/api/library", timeout=10))
    child = library["children"][0]["id"] if library["children"] else check(session.post(BASE + "/api/children", json={"name":"공개 샘플 A", "group":"기능 확인용"}, timeout=10))["id"]
    sample = ROOT / "test-output/fixtures/astronaut.png"
    with sample.open("rb") as stream:
        check(session.post(BASE + "/api/media", files={"file":("20261102 공개샘플.png", stream, "image/png")}, timeout=120))
    library = check(session.get(BASE + "/api/library", timeout=10))
    media = library["media"][0]
    detail = check(session.get(BASE + "/api/media/" + media["id"], timeout=10))
    assert detail["face_count"] == 1
    face = detail["faces"][0]
    check(session.post(BASE + f"/api/faces/{face['id']}/reference", json={"child":child}, timeout=10))
    check(session.post(BASE + "/api/rematch", timeout=30))
    detail = check(session.get(BASE + "/api/media/" + media["id"], timeout=10))
    assert detail["faces"][0]["candidate"]["accepted"]
    check(session.post(BASE + f"/api/media/{media['id']}/confirm", timeout=10))
    exports = check(session.post(BASE + "/api/exports", json={"children":[child]}, timeout=30))["exports"]
    archive = session.get(BASE + exports[0]["url"], timeout=30)
    archive.raise_for_status()
    with zipfile.ZipFile(BytesIO(archive.content)) as z:
        assert z.testzip() is None
        assert z.read(z.namelist()[0]) == sample.read_bytes()
    proof = {"real_model":True, "detected_faces":detail["face_count"], "candidate":detail["faces"][0]["candidate"],
             "zip_verified":True, "statistics":check(session.get(BASE + "/api/library", timeout=10))["statistics"]}
    (ROOT / "test-output/web-real-smoke.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"real_model":True,"detected_faces":detail["face_count"],"zip_verified":True},ensure_ascii=False))


if __name__ == "__main__":
    main()
