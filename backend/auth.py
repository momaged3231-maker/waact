import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone

from config import config


ROLE_LEVELS = {
    "viewer": 10,
    "agent": 20,
    "marketing": 25,
    "manager": 40,
    "admin": 80,
    "owner": 100,
}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return "pbkdf2_sha256$120000$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, rounds, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def sign_value(value: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def make_session_token(user_id: str) -> str:
    signature = sign_value(user_id)
    raw = f"{user_id}:{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def parse_session_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, signature = raw.rsplit(":", 1)
        if hmac.compare_digest(signature, sign_value(user_id)):
            return user_id
    except Exception:
        return None
    return None


def ensure_default_user(db):
    from database.models import User

    existing = db.query(User).first()
    if existing:
        return existing

    user = User(
        username=config.AUTH_USERNAME,
        password_hash=hash_password(config.AUTH_PASSWORD),
        role=config.AUTH_ROLE,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def get_current_user(request, db):
    from database.models import User

    user_id = parse_session_token(request.cookies.get("waact_auth"))
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def has_role(user, minimum_role: str) -> bool:
    if not user:
        return False
    return ROLE_LEVELS.get(user.role, 0) >= ROLE_LEVELS.get(minimum_role, 999)


def log_audit(
    action: str,
    user=None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict | None = None,
    request=None,
) -> None:
    try:
        from database.db import SessionLocal
        from database.models import AuditLog

        db = SessionLocal()
        try:
            ip = None
            if request and request.client:
                ip = request.client.host
            db.add(AuditLog(
                user_id=getattr(user, "id", None),
                username=getattr(user, "username", None),
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details or {},
                ip_address=ip,
                created_at=datetime.now(timezone.utc),
            ))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass
