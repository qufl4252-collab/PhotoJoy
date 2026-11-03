from io import BytesIO
import json
from pathlib import Path
import time
import zipfile

import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from photojoy.engine import Face
from photojoy_web.app import create_app
from photojoy_web.auth import token_hash

URL = "http://localhost"
HEADERS = {"Origin": URL, "X-PhotoJoy": "1"}
PASSWORD = "test-only-password-7315"


class TestEngine:
    fingerprint = "test-engine"

    def load(self):
        pass

    def detect_and_embed(self, image):
        h, w = image.shape[:2]
        return [Face([0, 0, w, h], [], .99, np.array([1., 0.], dtype=np.float32), image)]


@pytest.fixture
def web(tmp_path):
    app = create_app(data_dir=tmp_path, public_url=URL, google_client_id="", engine=TestEngine())
    with TestClient(app, base_url=URL, headers=HEADERS) as client:
        yield app, client


def register(client, username="테스트계정", platform="windows"):
    response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD, "platform": platform})
    assert response.status_code == 200, response.text
    return response


def photo(color="orange"):
    output = BytesIO()
    Image.new("RGB", (120, 100), color).save(output, format="PNG")
    return output.getvalue()


def upload(client, name="20261102 사진.png"):
    response = client.post("/api/media", files={"file": (name, photo(), "image/png")})
    assert response.status_code == 200, response.text
    return response.json()["media"]


def test_login_page_and_api_gate(web):
    app, client = web
    page = client.get("/")
    assert page.status_code == 200
    assert all(text in page.text for text in ["아이디", "비밀번호", "윈도우", "안드로이드", "아이폰", "Google로 로그인"])
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/library").status_code == 401
    assert client.post("/api/media", files={"file": ("x.png", photo())}).status_code == 401
    assert client.get("/web-data/accounts.sqlite3").status_code == 404
    assert client.get("/api/config").json()["google_client_id"] == ""


@pytest.mark.parametrize("platform", ["windows", "android", "iphone"])
def test_accounts_platforms_logout_and_password_storage(web, platform):
    app, client = web
    response = register(client, platform=platform)
    user_id = response.json()["user"]["id"]
    assert response.json()["user"]["platform"] == platform
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
    token = client.cookies.get("pj_session")
    with app.state.accounts.connect() as db:
        row = db.execute("SELECT password FROM users WHERE id=?", (user_id,)).fetchone()
        assert row[0].startswith("scrypt$") and PASSWORD not in row[0]
        assert db.execute("SELECT token FROM sessions").fetchone()[0] == token_hash(token)
    assert client.post("/api/auth/logout").status_code == 200
    assert app.state.accounts.resolve(token) is None
    assert client.get("/api/library").status_code == 401
    assert client.post("/api/auth/login", json={"username":"테스트계정","password":PASSWORD,"platform":platform}).status_code == 200
    assert client.get("/api/auth/me").json()["user"]["id"] == user_id


def test_bad_credentials_and_same_origin_enforcement(web):
    app, client = web
    register(client)
    assert client.post("/api/auth/login", json={"username":"테스트계정","password":"wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username":"not-present","password":"wrong"}).status_code == 401
    assert client.post("/api/auth/register", json={"username":"new","password":"short"}).status_code == 400
    assert client.post("/api/auth/register", json={"username":"new","password":PASSWORD,"platform":"linux"}).status_code == 422
    assert client.post("/api/children", json={"name":"김민준"}, headers={"Origin":"https://attacker.example"}).status_code == 403
    assert client.post("/api/children", json={"name":"김민준"}, headers={"X-PhotoJoy":""}).status_code == 403
    assert client.get("/", headers={"Host":"attacker.example"}).status_code == 400


def test_case_normalization_duplicate_and_registration_closed(web, monkeypatch):
    app, client = web
    register(client, "PhotoJoy_TEST")
    assert client.post("/api/auth/register", json={"username":"photojoy_test","password":PASSWORD}).status_code == 409
    monkeypatch.setenv("PHOTOJOY_REGISTRATION", "false")
    assert client.post("/api/auth/register", json={"username":"another","password":PASSWORD}).status_code == 403
    assert client.get("/api/config").json()["registration"] is False
    assert client.post("/api/auth/login", json={"username":"PHOTOJOY_test","password":PASSWORD}).status_code == 200


def test_upload_reference_review_export_and_undo(web):
    app, client = web
    register(client)
    child = client.post("/api/children", json={"name":"김민준","group":"햇살반"}).json()["id"]
    m = upload(client)
    assert m["status"] == "review" and m["face_count"] == 1
    detail = client.get(f"/api/media/{m['id']}").json()
    face_id = detail["faces"][0]["id"]
    assert client.get(m["preview"]).headers["cache-control"] == "no-store"
    assert client.post(f"/api/faces/{face_id}/reference", json={"child":child}).status_code == 200
    assert client.post("/api/rematch").status_code == 200
    assert client.get("/api/library").json()["media"][0]["status"] == "candidate"
    assert client.post(f"/api/media/{m['id']}/confirm").status_code == 200
    stats = client.get("/api/library").json()["statistics"][0]
    assert stats["photos"] == 1
    exports = client.post("/api/exports", json={"children":[child]}).json()["exports"]
    assert len(exports) == 1 and exports[0]["count"] == 1
    data = client.get(exports[0]["url"])
    with zipfile.ZipFile(BytesIO(data.content)) as archive:
        assert archive.testzip() is None
        assert archive.read(archive.namelist()[0]) == photo()
    csv = client.get("/api/statistics.csv")
    assert "김민준" in csv.content.decode("utf-8-sig")
    assert client.post(f"/api/media/{m['id']}/undo").status_code == 200
    assert client.get("/api/library").json()["statistics"][0]["photos"] == 0
    assert client.post(f"/api/media/{m['id']}/review", json={"children":[child]}).status_code == 200
    assert client.put(f"/api/children/{child}", json={"name":"박서연","group":"하늘반"}).status_code == 200
    assert client.get("/api/library").json()["children"][0]["name"] == "박서연"


def test_tenant_isolation_for_every_private_resource(web):
    app, first = web
    register(first, "account-one")
    child = first.post("/api/children", json={"name":"우리 아이"}).json()["id"]
    media = upload(first)
    face = first.get(f"/api/media/{media['id']}").json()["faces"][0]["id"]
    first.post(f"/api/media/{media['id']}/review", json={"children":[child]})
    export = first.post("/api/exports", json={"children":[child]}).json()["exports"][0]
    with TestClient(app, base_url=URL, headers=HEADERS) as second:
        register(second, "account-two")
        assert second.get("/api/library").json()["media"] == []
        for path in [media["preview"], f"/api/media/{media['id']}", f"/api/faces/{face}/crop", export["url"]]:
            assert second.get(path).status_code == 404
        assert second.post(f"/api/media/{media['id']}/review", json={"children":[child]}).status_code == 404
        assert second.post(f"/api/faces/{face}/reference", json={"child":child}).status_code == 404
        assert second.put(f"/api/children/{child}", json={"name":"변조"}).status_code == 404
        assert second.post("/api/exports", json={"children":[child]}).status_code == 404


def test_upload_names_duplicates_and_rejection_cleanup(web, monkeypatch):
    app, client = web
    register(client)
    media = upload(client, "../../"+"한"*180+".png")
    assert media["name"].endswith(".png") and "/" not in media["name"]
    assert len(media["name"].encode("utf-8")) <= 200
    duplicate = client.post("/api/media", files={"file":("duplicate.png",photo())})
    assert duplicate.json()["duplicate"] is True
    assert len(list(app.state.data_root.glob("users/*/uploads/*/*"))) == 1
    assert client.post("/api/media", files={"file":("bad.exe",b"data")}).status_code == 400
    assert client.post("/api/media", files={"file":("broken.jpg",b"not an image")}).status_code == 422
    assert client.post("/api/media", files={"file":("empty.jpg",b"")}).status_code == 400
    assert len(client.get("/api/library").json()["media"]) == 1
    monkeypatch.setenv("PHOTOJOY_USER_QUOTA_MB", "0")
    assert client.post("/api/media", files={"file":("over.png",photo("blue"))}).status_code == 413
    assert len(list(app.state.data_root.glob("users/*/uploads/*/*"))) == 1


def test_sessions_expire_and_rate_limit(web):
    app, client = web
    register(client)
    with app.state.accounts.connect() as db:
        db.execute("UPDATE sessions SET expires=?", (time.time()-1,))
    assert client.get("/api/auth/me").status_code == 401
    for _ in range(3):
        app.state.accounts.limit("limited-test", maximum=3)
    with pytest.raises(Exception) as error:
        app.state.accounts.limit("limited-test", maximum=3)
    assert error.value.status_code == 429


def test_google_disabled_invalid_token_nonce_and_replay(web, tmp_path):
    app, client = web
    assert client.post("/api/auth/google", json={"credential":"not-a-token"}).status_code == 503
    configured = create_app(tmp_path / "google", URL, "test-client.apps.googleusercontent.com", engine=TestEngine())
    with TestClient(configured, base_url=URL, headers=HEADERS) as google:
        nonce = google.get("/api/config").json()["google_nonce"]
        def invalid(*args):
            raise ValueError("signature rejected")
        configured.state.verify_google = invalid
        assert google.post("/api/auth/google", json={"credential":"forged"}).status_code == 401
        claims = {"sub":"google-subject-1","name":"구글 사용자","email_verified":True,"nonce":"wrong"}
        configured.state.verify_google = lambda token, audience: claims
        assert google.post("/api/auth/google", json={"credential":"fixture"}).status_code == 401
        claims["nonce"] = nonce
        success = google.post("/api/auth/google", json={"credential":"fixture","platform":"iphone"})
        assert success.status_code == 200 and success.json()["user"]["platform"] == "iphone"
        assert not configured.state.accounts.consume_challenge(nonce)
        assert google.post("/api/auth/google", json={"credential":"fixture"}).status_code == 401


def test_secure_cookie_and_public_url_validation(tmp_path):
    with pytest.raises(ValueError):
        create_app(tmp_path / "bad", "http://public.example")
    app = create_app(tmp_path / "secure", "https://photojoy.example", "", engine=TestEngine())
    with TestClient(app, base_url="https://photojoy.example", headers={**HEADERS,"Origin":"https://photojoy.example"}) as client:
        response = register(client)
        assert "Secure" in response.headers["set-cookie"]
        assert "max-age" in response.headers["strict-transport-security"]


def test_declared_body_limit(web):
    app, client = web
    register(client)
    response = client.post("/api/media", content=b"small", headers={"Content-Length":str(1024**3)})
    assert response.status_code == 413
