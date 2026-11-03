from datetime import date
from functools import lru_cache
import hmac
import json
import logging
import os
from pathlib import Path
import re
import threading
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from photojoy.engine import SFaceEngine
from photojoy.exporting import export_csv, make_zips
from photojoy.media import MEDIA_EXT
from photojoy.paths import inside, safe_name, uid
from photojoy.service import Service
from photojoy.store import Store
from .auth import Accounts, SESSION_SECONDS

ROOT = Path(__file__).resolve().parent
Platform = Literal["windows", "android", "iphone"]
MAX_FILE = 100 * 1024 * 1024
MAX_REQUEST = MAX_FILE + 1024 * 1024
logger = logging.getLogger("photojoy.web")


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)
    platform: Platform = "windows"


class GoogleCredential(BaseModel):
    credential: str = Field(min_length=1, max_length=16384)
    platform: Platform = "windows"


class ChildInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    group: str = Field(default="", max_length=80)


class ReviewInput(BaseModel):
    children: list[str] = Field(default_factory=list, max_length=100)
    excluded: bool = False


class ReferenceInput(BaseModel):
    child: str = Field(min_length=1, max_length=32)


class ExportInput(BaseModel):
    children: list[str] = Field(min_length=1, max_length=100)
    start: date = date(1900, 1, 1)
    end: date = date(2100, 12, 31)


class RequestTooLarge(Exception):
    pass


class BodyLimit:
    """Count streamed bytes before the multipart parser can fill temporary storage."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        limit = MAX_REQUEST if scope["path"] == "/api/media" else 128 * 1024
        try:
            if int(headers.get(b"content-length", b"0")) > limit:
                return await JSONResponse({"detail": "파일은 한 개당 100MB까지 업로드할 수 있습니다."}, 413)(scope, receive, send)
        except ValueError:
            return await JSONResponse({"detail": "잘못된 요청입니다."}, 400)(scope, receive, send)
        total = 0

        async def limited():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise RequestTooLarge()
            return message

        try:
            await self.app(scope, limited, send)
        except RequestTooLarge:
            await JSONResponse({"detail": "요청 크기가 너무 큽니다."}, 413)(scope, receive, send)


def verify_google(credential, client_id):
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token
    return id_token.verify_oauth2_token(credential, GoogleRequest(), client_id)


def create_app(data_dir=None, public_url=None, google_client_id=None, engine=None):
    public_url = (public_url or os.getenv("PHOTOJOY_PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://127.0.0.1:8765").rstrip("/")
    parsed = urlparse(public_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("PHOTOJOY_PUBLIC_URL에는 경로 없는 서비스 주소를 입력하세요.")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("외부 서비스는 HTTPS 주소가 필요합니다.")
    secure = parsed.scheme == "https"
    client_id = google_client_id if google_client_id is not None else os.getenv("GOOGLE_CLIENT_ID", "")
    root = Path(data_dir or os.getenv("PHOTOJOY_DATA_DIR", str(ROOT.parent / "web-data"))).resolve()
    accounts = Accounts(root)
    app = FastAPI(title="PhotoJoy Web", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.accounts = accounts
    app.state.data_root = root
    app.state.verify_google = verify_google
    recognition = engine or SFaceEngine()
    engine_lock = threading.Lock()
    locks = [threading.RLock() for _ in range(64)]

    def lock(user):
        return locks[int(user["id"][:8], 16) % len(locks)]

    @lru_cache(maxsize=256)
    def user_store(user_id):
        if not re.fullmatch(r"[0-9a-f]{32}", user_id):
            raise HTTPException(401, "다시 로그인하세요.")
        return Store(inside(root, root / "users" / user_id))

    def current(request: Request):
        user = accounts.resolve(request.cookies.get("pj_session"))
        if not user:
            raise HTTPException(401, "로그인이 필요합니다.")
        return user

    def rate(request, username=None):
        accounts.limit("ip:" + (request.client.host if request.client else "unknown"), 30)
        if username:
            from .auth import normalize_username
            accounts.limit("username:" + normalize_username(username), 15)

    def session_response(request, response, user_id, platform):
        accounts.logout(request.cookies.get("pj_session"))
        token = accounts.session(user_id, platform)
        response.set_cookie("pj_session", token, max_age=SESSION_SECONDS, httponly=True, secure=secure, samesite="lax", path="/")
        return {"user": accounts.resolve(token)}

    @app.middleware("http")
    async def security(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != public_url or request.headers.get("x-photojoy") != "1":
                return JSONResponse({"detail": "이 페이지를 새로 열고 다시 시도하세요."}, 403)
        # Authenticate before reading potentially large multipart request bodies.
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/auth/") and request.url.path != "/api/config":
            if not accounts.resolve(request.cookies.get("pj_session")):
                return JSONResponse({"detail": "로그인이 필요합니다."}, 401, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; "
            "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style; "
            "img-src 'self' data: https://*.googleusercontent.com; "
            "connect-src 'self' https://accounts.google.com/gsi/; frame-src https://accounts.google.com/gsi/; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        if secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/api/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def bad_value(request, exc):
        return JSONResponse({"detail": "입력값이나 자료 상태를 확인하세요. 페이지를 새로고침한 후 다시 시도할 수 있습니다."}, 400)

    @app.exception_handler(RequestTooLarge)
    async def too_large(request, exc):
        return JSONResponse({"detail": "파일은 한 개당 100MB까지 업로드할 수 있습니다."}, 413)

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": "0.3.0"}

    @app.get("/api/config")
    def config(response: Response):
        nonce = accounts.challenge() if client_id else ""
        if nonce:
            response.set_cookie("pj_google_nonce", nonce, max_age=600, httponly=True, secure=secure, samesite="strict")
        return {"google_client_id": client_id, "google_nonce": nonce, "max_file_mb": 100,
                "registration": os.getenv("PHOTOJOY_REGISTRATION", "true").lower() == "true"}

    @app.get("/api/auth/me")
    def me(user=Depends(current)):
        return {"user": user}

    @app.post("/api/auth/register")
    def register(body: Credentials, request: Request, response: Response):
        rate(request, body.username)
        if os.getenv("PHOTOJOY_REGISTRATION", "true").lower() != "true":
            raise HTTPException(403, "새 계정 만들기가 닫혀 있습니다. 운영자에게 문의하세요.")
        return session_response(request, response, accounts.register(body.username, body.password), body.platform)

    @app.post("/api/auth/login")
    def login(body: Credentials, request: Request, response: Response):
        rate(request, body.username)
        return session_response(request, response, accounts.login(body.username, body.password), body.platform)

    @app.post("/api/auth/google")
    def google_login(body: GoogleCredential, request: Request, response: Response):
        rate(request)
        if not client_id:
            raise HTTPException(503, "Google 로그인 연결을 준비 중입니다. 아이디로 로그인해 주세요.")
        nonce = request.cookies.get("pj_google_nonce", "")
        if not nonce:
            raise HTTPException(401, "Google 로그인을 다시 시작하세요.")
        try:
            claims = app.state.verify_google(body.credential, client_id)
        except Exception:
            raise HTTPException(401, "Google 계정을 확인하지 못했습니다. 다시 로그인하세요.")
        if (not claims.get("sub") or not claims.get("email_verified")
                or not hmac.compare_digest(str(claims.get("nonce", "")), nonce)
                or not accounts.consume_challenge(nonce)):
            raise HTTPException(401, "Google 로그인 요청이 만료되었거나 올바르지 않습니다.")
        with accounts.connect() as db:
            existing = db.execute("SELECT id FROM users WHERE google_sub=?", (claims["sub"],)).fetchone()
        if not existing and os.getenv("PHOTOJOY_REGISTRATION", "true").lower() != "true":
            raise HTTPException(403, "새 계정 만들기가 닫혀 있습니다.")
        user_id = accounts.google_user(claims["sub"], claims.get("name") or "Google 사용자")
        response.delete_cookie("pj_google_nonce")
        return session_response(request, response, user_id, body.platform)

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        accounts.logout(request.cookies.get("pj_session"))
        response.delete_cookie("pj_session")
        return {"ok": True}

    def media_item(store, row):
        faces = store.faces(row["id"])
        candidates = [json.loads(face["candidate"]) for face in faces]
        status = row["status"]
        if not row["reviewed"] and status == "review":
            status = "candidate" if candidates and all(c["accepted"] for c in candidates) else "review"
        return {"id": row["id"], "name": Path(row["path"]).name, "kind": row["kind"],
                "captured": row["captured"], "status": status, "reviewed": bool(row["reviewed"]),
                "children": json.loads(row["assignments"]), "face_count": len(faces),
                "preview": f"/api/media/{row['id']}/preview" if row["thumbnail"] else None,
                "candidates": list(dict.fromkeys(c["child"] for c in candidates if c["child"]))}

    @app.get("/api/library")
    def library(user=Depends(current)):
        with lock(user):
            store = user_store(user["id"])
            media = [media_item(store, row) for row in store.media()]
            return {"children": store.children(), "media": media, "statistics": store.statistics()}

    @app.post("/api/children")
    def add_child(body: ChildInput, user=Depends(current)):
        if not body.name.strip():
            raise HTTPException(400, "아이 이름을 입력하세요.")
        with lock(user):
            store = user_store(user["id"])
            if len(store.children()) >= 100:
                raise HTTPException(400, "한 계정에 아이를 최대 100명까지 등록할 수 있습니다.")
            return {"id": store.add_child(body.name, body.group)}

    @app.put("/api/children/{child_id}")
    def edit_child(child_id: str, body: ChildInput, user=Depends(current)):
        with lock(user):
            store = user_store(user["id"])
            require_child(store, child_id)
            store.update_child(child_id, body.name, body.group, True)
            return {"ok": True}

    def require_child(store, child):
        if child not in {c["id"] for c in store.children()}:
            raise HTTPException(404, "아이 정보를 찾을 수 없습니다.")

    def require_media(store, media_id):
        rows = store.rows("SELECT * FROM media WHERE id=?", (media_id,))
        if not rows:
            raise HTTPException(404, "사진을 찾을 수 없습니다.")
        return rows[0]

    def protected_file(store, path, filename=None):
        if not path:
            raise HTTPException(404, "파일이 없습니다.")
        file = inside(store.root, Path(path))
        if not file.is_file():
            raise HTTPException(404, "파일이 없습니다.")
        return FileResponse(file, filename=filename)

    @app.post("/api/media")
    def upload(file: UploadFile, user=Depends(current)):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in MEDIA_EXT:
            raise HTTPException(400, "지원하는 사진 또는 영상 파일을 선택하세요.")
        with lock(user):
            store = user_store(user["id"])
            uploads = inside(store.root, store.root / "uploads")
            uploads.mkdir(exist_ok=True)
            quota = int(os.getenv("PHOTOJOY_USER_QUOTA_MB", "2048")) * 1024 * 1024
            used = sum(p.stat().st_size for p in uploads.rglob("*") if p.is_file())
            folder = uploads / uid()
            folder.mkdir()
            original_name = Path((file.filename or "photo").replace("\\", "/"))
            # Linux limits each filename by UTF-8 bytes, not Unicode characters.
            stem = safe_name(original_name.stem, 120)
            stem = stem.encode("utf-8")[:200-len(suffix.encode("utf-8"))].decode("utf-8", errors="ignore").rstrip(" .") or "photo"
            target = inside(folder, folder / (stem + suffix))
            size = 0
            try:
                with target.open("xb") as output:
                    while chunk := file.file.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE or size + used > quota:
                            raise HTTPException(413, "파일 한도(100MB) 또는 계정 보관 용량을 초과했습니다.")
                        output.write(chunk)
                if not size:
                    raise HTTPException(400, "빈 파일은 업로드할 수 없습니다.")
                with engine_lock:
                    result = Service(store, recognition).analyze([target])
                rows = store.rows("SELECT * FROM media WHERE path=?", (str(target),))
                if result["cached"] and not rows:
                    target.unlink()
                    folder.rmdir()
                    return {"duplicate": True, "message": "이미 보관된 사진입니다."}
                if result["errors"]:
                    raise HTTPException(422, "사진·영상 분석에 실패했습니다. 파일 형식과 서버의 모델 준비 상태를 확인하세요.")
                return {"media": media_item(store, rows[0]), "duplicate": False}
            except Exception:
                # Failed uploads cannot be returned as successful library entries.
                store.execute("DELETE FROM media WHERE path=? AND reviewed=0", (str(target),))
                target.unlink(missing_ok=True)
                if folder.exists():
                    folder.rmdir()
                raise
            finally:
                file.file.close()

    @app.get("/api/media/{media_id}")
    def detail(media_id: str, user=Depends(current)):
        store = user_store(user["id"])
        row = require_media(store, media_id)
        result = media_item(store, row)
        result["date_source"] = row["date_source"]
        result["faces"] = [{"id": f["id"], "bbox": json.loads(f["bbox"]), "frame": f["frame"],
                            "candidate": json.loads(f["candidate"]), "crop": f"/api/faces/{f['id']}/crop",
                            "preview": f"/api/faces/{f['id']}/preview"} for f in store.faces(media_id)]
        return result

    @app.get("/api/media/{media_id}/preview")
    def preview(media_id: str, user=Depends(current)):
        store = user_store(user["id"])
        return protected_file(store, require_media(store, media_id)["thumbnail"])

    @app.get("/api/faces/{face_id}/{variant}")
    def face_image(face_id: str, variant: Literal["crop", "preview"], user=Depends(current)):
        store = user_store(user["id"])
        rows = store.rows("SELECT * FROM faces WHERE id=?", (face_id,))
        if not rows:
            raise HTTPException(404, "얼굴을 찾을 수 없습니다.")
        return protected_file(store, rows[0][variant])

    @app.post("/api/faces/{face_id}/reference")
    def reference(face_id: str, body: ReferenceInput, user=Depends(current)):
        with lock(user):
            store = user_store(user["id"])
            require_child(store, body.child)
            if not store.rows("SELECT id FROM faces WHERE id=?", (face_id,)):
                raise HTTPException(404, "얼굴을 찾을 수 없습니다.")
            Service(store, recognition).learn_face(face_id, body.child)
            return {"ok": True}

    @app.post("/api/rematch")
    def rematch(user=Depends(current)):
        with lock(user), engine_lock:
            store = user_store(user["id"])
            service = Service(store, recognition)
            for row in store.media():
                if not row["reviewed"]:
                    service.rematch(row["id"])
        return {"ok": True}

    @app.post("/api/media/{media_id}/review")
    def review(media_id: str, body: ReviewInput, user=Depends(current)):
        with lock(user):
            store = user_store(user["id"])
            require_media(store, media_id)
            store.review([media_id], body.children, body.excluded)
        return {"ok": True}

    @app.post("/api/media/{media_id}/confirm")
    def confirm(media_id: str, user=Depends(current)):
        with lock(user):
            store = user_store(user["id"])
            require_media(store, media_id)
            Service(store, recognition).confirm_candidates([media_id])
        return {"ok": True}

    @app.post("/api/media/{media_id}/undo")
    def undo(media_id: str, user=Depends(current)):
        with lock(user):
            store = user_store(user["id"])
            require_media(store, media_id)
            store.undo_review(media_id)
        return {"ok": True}

    @app.post("/api/exports")
    def export(body: ExportInput, user=Depends(current)):
        if body.end < body.start:
            raise HTTPException(400, "종료일은 시작일 이후여야 합니다.")
        with lock(user):
            store = user_store(user["id"])
            for child in body.children:
                require_child(store, child)
            result = make_zips(store, body.children, str(body.start), str(body.end))
            exports = []
            for path in result["paths"]:
                row = store.rows("SELECT * FROM exports WHERE path=?", (path,))[0]
                exports.append({"name": Path(path).name, "count": row["file_count"], "url": f"/api/exports/{row['id']}"})
            return {"exports": exports}

    @app.get("/api/exports/{export_id}")
    def download(export_id: str, user=Depends(current)):
        store = user_store(user["id"])
        rows = store.rows("SELECT path FROM exports WHERE id=?", (export_id,))
        if not rows:
            raise HTTPException(404, "다운로드를 찾을 수 없습니다.")
        return protected_file(store, rows[0]["path"], Path(rows[0]["path"]).name)

    @app.get("/api/statistics.csv")
    def statistics_csv(user=Depends(current)):
        with lock(user):
            store = user_store(user["id"])
            target = store.data / "statistics.csv"
            export_csv(store, target, "1900-01-01", "2100-12-31")
            return protected_file(store, target, "PhotoJoy-통계.csv")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "static" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[parsed.hostname])
    return app


def app_factory():
    return create_app()
