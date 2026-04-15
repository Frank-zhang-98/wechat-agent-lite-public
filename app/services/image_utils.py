from __future__ import annotations

from typing import Final


_MAGIC_MIME_PAIRS: Final[tuple[tuple[bytes, str], ...]] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)

_MIME_SUFFIXES: Final[dict[str, str]] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


def detect_image_mime(payload: bytes, *, fallback: str = "image/png") -> str:
    data = bytes(payload or b"")
    for magic, mime_type in _MAGIC_MIME_PAIRS:
        if data.startswith(magic):
            return mime_type
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback


def image_suffix_for_mime(mime_type: str, *, fallback: str = ".png") -> str:
    normalized = str(mime_type or "").strip().lower()
    return _MIME_SUFFIXES.get(normalized, fallback)
