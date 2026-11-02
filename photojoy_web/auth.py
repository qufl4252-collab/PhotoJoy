"""Server-owned accounts and revocable opaque sessions. No browser password storage."""
from contextlib import contextmanager
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3
import time
import unicodedata

from fastapi import HTTPException

SESSION_SECONDS = 24 * 60 * 60


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768,
                           r=8, p=1, maxmem=64 * 1024 * 1024).hex()
    return f"scrypt${salt}${value}"


def password_matches(password, stored):
    if not stored:
        # Keep unknown-user verification comparable to an existing account.
        password_hash(password, "00" * 16)
        return False
    return hmac.compare_digest(password_hash(password, stored.split("$")[1]), stored)


def normalize_username(value):
    return unicodedata.normalize("NFKC", value).strip().casefold()


class Accounts:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "accounts.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE, password TEXT,
                    google_sub TEXT UNIQUE, display_name TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id),
                    platform TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                    key TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS attempts_key ON attempts(key,at);
                CREATE TABLE IF NOT EXISTS challenges (nonce TEXT PRIMARY KEY, expires REAL NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def limit(self, key, maximum=20):
        now = time.time()
        key = token_hash(key)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM attempts WHERE at<?", (now - 600,))
            count = db.execute("SELECT COUNT(*) FROM attempts WHERE key=?", (key,)).fetchone()[0]
            if count >= maximum:
                raise HTTPException(429, "시도가 너무 많습니다. 10분 후 다시 시도하세요.")
            db.execute("INSERT INTO attempts VALUES (?,?)", (key, now))

    def register(self, username, password):
        key = normalize_username(username)
        if not 3 <= len(key) <= 40 or any(not (c.isalnum() or c in "_.@-") for c in key):
            raise HTTPException(400, "아이디는 한글·영문·숫자와 _.@-를 사용해 3~40자로 입력하세요.")
        if not 10 <= len(password) <= 128:
            raise HTTPException(400, "비밀번호는 10~128자로 입력하세요.")
        user = secrets.token_hex(16)
        hashed = password_hash(password)
        try:
            with self.connect() as db:
                db.execute("INSERT INTO users VALUES (?,?,?,NULL,?,?)",
                           (user, key, hashed, username.strip(), time.time()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "사용할 수 없는 아이디입니다. 다른 아이디를 선택하세요.")
        return user

    def login(self, username, password):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (normalize_username(username),)).fetchone()
        if not password_matches(password, row["password"] if row else None):
            raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
        return row["id"]

    def google_user(self, sub, name):
        # Never merge accounts merely because an email address matches.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM users WHERE google_sub=?", (sub,)).fetchone()
            if row:
                return row[0]
            user = secrets.token_hex(16)
            db.execute("INSERT INTO users VALUES (?,NULL,NULL,?,?,?)", (user, sub, name[:80], time.time()))
            return user

    def session(self, user, platform):
        token = secrets.token_urlsafe(48)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token_hash(token), user, platform, time.time()+SESSION_SECONDS))
        return token

    def resolve(self, token):
        with self.connect() as db:
            row = db.execute("""SELECT u.id,u.display_name,s.platform FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token=? AND s.expires>?""", (token_hash(token or ""), time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (token_hash(token or ""),))

    def challenge(self):
        nonce = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM challenges WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO challenges VALUES (?,?)", (token_hash(nonce), time.time()+600))
        return nonce

    def consume_challenge(self, nonce):
        with self.connect() as db:
            result = db.execute("DELETE FROM challenges WHERE nonce=? AND expires>?", (token_hash(nonce), time.time()))
            return result.rowcount == 1
