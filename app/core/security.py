from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet

from app.core.config import CONFIG


SECRET_PLACEHOLDER = "******"
_LEGACY_DEFAULT_KEY = base64.urlsafe_b64encode(hashlib.sha256(b"wechat-agent-lite-dev-key").digest())


def _derive_key(raw_value: str | None = None) -> bytes:
    """
    Resolve a valid fernet key from either:
    - an explicit 32-byte urlsafe base64 fernet key, or
    - an arbitrary passphrase that we deterministically hash into a fernet key.
    """
    raw = str(CONFIG.encryption_key if raw_value is None else raw_value).strip()
    if not raw:
        return _LEGACY_DEFAULT_KEY

    raw_bytes = raw.encode("utf-8")
    try:
        Fernet(raw_bytes)
        return raw_bytes
    except Exception:
        digest = hashlib.sha256(raw_bytes).digest()
        return base64.urlsafe_b64encode(digest)


def has_external_encryption_key() -> bool:
    return bool(CONFIG.encryption_key.strip())


def allow_insecure_secret_storage() -> bool:
    raw = os.getenv("WAL_ALLOW_INSECURE_DEV", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def ensure_secret_storage_allowed(*, key: str, value: str) -> None:
    if not str(value or "").strip():
        return
    if has_external_encryption_key() or allow_insecure_secret_storage():
        return
    raise RuntimeError(
        f"refusing to store secret '{key}' without WAL_ENCRYPTION_KEY; "
        "set WAL_ENCRYPTION_KEY or WAL_ALLOW_INSECURE_DEV=1 for explicit local-only override"
    )


_FERNET = Fernet(_derive_key())
_LEGACY_FERNET = Fernet(_LEGACY_DEFAULT_KEY)


def _decrypt_with_fernets(value: str, fernets: list[Fernet]) -> str:
    for fernet in fernets:
        try:
            return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:
            continue
    return ""


def encrypt_text(value: str) -> str:
    if value == "":
        return ""
    return _FERNET.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str) -> str:
    if value == "":
        return ""
    fernets = [_FERNET]
    if _derive_key() != _LEGACY_DEFAULT_KEY:
        fernets.append(_LEGACY_FERNET)
    return _decrypt_with_fernets(value, fernets)
