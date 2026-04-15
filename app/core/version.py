from __future__ import annotations

from pathlib import Path

DEFAULT_APP_VERSION = "v0.0"
VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def get_console_version(*, version_file: Path | None = None) -> str:
    target = version_file or VERSION_FILE
    try:
        value = target.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_APP_VERSION
    return value or DEFAULT_APP_VERSION


def get_console_page_title(*, version: str | None = None) -> str:
    current_version = version or get_console_version()
    return f"wechat-agent-lite 控制台 {current_version}"
