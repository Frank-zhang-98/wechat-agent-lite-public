from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import feedparser
import requests
import yaml

from app.core.config import CONFIG


def _normalize_datetime_text(value: str) -> str:
    raw = FetchService._clean_text(value)
    if not raw:
        return ""
    candidates = [raw]
    if raw.endswith("Z"):
        candidates.append(raw[:-1] + "+00:00")
    for pattern in (
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
        r"(\d{4})\.(\d{1,2})\.(\d{1,2})",
        r"(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5",
    ):
        match = re.fullmatch(pattern, raw)
        if not match:
            continue
        year, month, day = match.groups()
        candidates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}T00:00:00+00:00")
    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            continue
    return ""


def _coerce_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    if isinstance(value, (tuple, list)) and len(value) >= 6:
        try:
            return datetime(*[int(part) for part in value[:6]], tzinfo=timezone.utc)
        except Exception:
            return None
    if all(hasattr(value, attr) for attr in ("tm_year", "tm_mon", "tm_mday", "tm_hour", "tm_min", "tm_sec")):
        try:
            return datetime(
                int(value.tm_year),
                int(value.tm_mon),
                int(value.tm_mday),
                int(value.tm_hour),
                int(value.tm_min),
                int(value.tm_sec),
                tzinfo=timezone.utc,
            )
        except Exception:
            return None

    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = _normalize_datetime_text(raw)
    if normalized:
        try:
            return datetime.fromisoformat(normalized)
        except Exception:
            pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_time(entry: Any) -> dict[str, Any]:
    candidates = [
        ("rss_published_parsed", "high", entry.get("published_parsed")),
        ("rss_updated_parsed", "medium", entry.get("updated_parsed")),
        ("rss_published", "medium", entry.get("published")),
        ("rss_updated", "low", entry.get("updated")),
    ]
    for source, confidence, raw_value in candidates:
        published_dt = _coerce_utc_datetime(raw_value)
        if published_dt is None:
            continue
        return {
            "published_dt": published_dt,
            "published_source": source,
            "published_confidence": confidence,
        }
    return {
        "published_dt": None,
        "published_source": "",
        "published_confidence": "low",
    }


class FetchService:
    _HTML_ATTR_NAMES = (
        "target",
        "title",
        "href",
        "src",
        "alt",
        "class",
        "style",
        "rel",
        "id",
        "width",
        "height",
        "loading",
        "decoding",
        "referrerpolicy",
    )
    _GITHUB_SPECIAL_FILENAMES = {
        "dockerfile": "dockerfile",
        "docker-compose.yml": "yaml",
        "docker-compose.yaml": "yaml",
        "compose.yml": "yaml",
        "compose.yaml": "yaml",
        "package.json": "json",
        "pyproject.toml": "toml",
        "poetry.lock": "text",
        "requirements.txt": "text",
        "go.mod": "go",
        "go.sum": "text",
        "cargo.toml": "toml",
        "cargo.lock": "text",
        "pom.xml": "xml",
        "build.gradle": "gradle",
        "build.gradle.kts": "kotlin",
        "settings.gradle": "gradle",
        "settings.gradle.kts": "kotlin",
        "makefile": "makefile",
        ".env.example": "dotenv",
    }
    _GITHUB_LANGUAGE_BY_SUFFIX = {
        ".py": "python",
        ".ts": "ts",
        ".tsx": "tsx",
        ".js": "js",
        ".jsx": "jsx",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".kt": "kotlin",
        ".swift": "swift",
        ".rb": "ruby",
        ".php": "php",
        ".cs": "csharp",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".m": "objective-c",
        ".mm": "objective-c",
        ".scala": "scala",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        ".ps1": "powershell",
        ".sql": "sql",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".ini": "ini",
        ".cfg": "ini",
        ".env": "dotenv",
        ".proto": "proto",
        ".md": "markdown",
    }
    _GITHUB_EXCLUDED_PATH_MARKERS = (
        "/node_modules/",
        "/dist/",
        "/build/",
        "/coverage/",
        "/vendor/",
        "/.next/",
        "/.nuxt/",
        "/__pycache__/",
        "/site-packages/",
    )
    _GITHUB_LOW_SIGNAL_PATH_MARKERS = (
        "/test/",
        "/tests/",
        "/spec/",
        "/__tests__/",
        "/example/",
        "/examples/",
        "/demo/",
        "/demos/",
        "/docs/",
        "/doc/",
        "/fixtures/",
        "/fixture/",
    )

    def __init__(self, all_proxy: str | None = None):
        self.all_proxy = all_proxy or ""
        self._rerank_excerpt_cache: dict[str, dict[str, Any]] = {}
        self._rerank_excerpt_cache_ttl_seconds = 1800

    @staticmethod
    def _published_payload(
        published_dt: datetime | None,
        *,
        source: str = "",
        confidence: str = "low",
        status: str = "",
    ) -> dict[str, Any]:
        normalized_status = str(status or "").strip().lower()
        if not normalized_status:
            normalized_status = "unknown" if published_dt is None else "fresh"
        return {
            "published": published_dt.isoformat() if published_dt is not None else "",
            "published_source": str(source or "").strip(),
            "published_confidence": str(confidence or "low").strip().lower() or "low",
            "published_status": normalized_status,
        }

    @staticmethod
    def _source_meta(source: dict[str, Any]) -> dict[str, Any]:
        pools = source.get("pools") or []
        if not isinstance(pools, list):
            pools = [pools]
        normalized_pools = []
        seen: set[str] = set()
        for pool in pools:
            token = str(pool or "").strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            normalized_pools.append(token)
        return {
            "source_category": str(source.get("category", "") or "").strip().lower(),
            "source_tier": str(source.get("tier", "") or "").strip().lower(),
            "source_mode": str(source.get("mode", "rss") or "rss").strip().lower(),
            "source_pools": normalized_pools,
        }

    def _fetch_html_document(self, url: str, *, timeout: int = 20) -> dict[str, Any]:
        try:
            response = self._request(url, timeout=timeout)
            response.raise_for_status()
        except Exception as exc:
            return {
                "url": url,
                "status": "failed",
                "reason": f"request_failed: {exc}",
                "html_text": "",
                "title": "",
                "fetch_mode": "http",
            }

        content_type = (response.headers.get("Content-Type", "") or "").lower()
        if "html" not in content_type and "xml" not in content_type and "text" not in content_type:
            return {
                "url": url,
                "status": "failed",
                "reason": f"unsupported_content_type: {content_type or '-'}",
                "html_text": "",
                "title": "",
                "fetch_mode": "http",
            }

        html_text = response.text or ""
        return {
            "url": url,
            "status": "ok",
            "reason": "",
            "html_text": html_text,
            "title": self._extract_html_title(html_text),
            "fetch_mode": "http",
        }

    @staticmethod
    def _extract_meta_description(html_text: str) -> str:
        html_source = str(html_text or "")
        patterns = [
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html_source, flags=re.IGNORECASE)
            if match:
                return FetchService._clean_text(match.group(1))
        return ""

    @staticmethod
    def _infer_date_from_url(url: str) -> str:
        raw = str(url or "").strip()
        if not raw:
            return ""
        patterns = [
            r"/(20\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])(?:/|$)",
            r"[-_/](20\d{2})[-_/](0?[1-9]|1[0-2])[-_/](0?[1-9]|[12]\d|3[01])(?:[-_/]|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw)
            if not match:
                continue
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}T00:00:00+00:00"
        return ""

    def _get_rerank_excerpt_cache(self, url: str, *, max_chars: int) -> dict[str, Any] | None:
        cache_key = f"{str(url or '').strip()}|{int(max_chars)}"
        cached = dict(self._rerank_excerpt_cache.get(cache_key) or {})
        if not cached:
            return None
        expires_at = float(cached.get("_expires_at", 0.0) or 0.0)
        if expires_at <= time.time():
            self._rerank_excerpt_cache.pop(cache_key, None)
            return None
        cached.pop("_expires_at", None)
        cached["cache_hit"] = True
        return cached

    def _set_rerank_excerpt_cache(self, url: str, *, max_chars: int, payload: dict[str, Any]) -> None:
        cache_key = f"{str(url or '').strip()}|{int(max_chars)}"
        record = dict(payload or {})
        record["_expires_at"] = time.time() + max(60, int(self._rerank_excerpt_cache_ttl_seconds))
        self._rerank_excerpt_cache[cache_key] = record
        if len(self._rerank_excerpt_cache) > 256:
            now = time.time()
            expired = [key for key, value in self._rerank_excerpt_cache.items() if float(value.get("_expires_at", 0.0) or 0.0) <= now]
            for key in expired[:96]:
                self._rerank_excerpt_cache.pop(key, None)

    def extract_rerank_excerpt_light(self, url: str, max_chars: int = 1200, timeout: int = 6) -> dict[str, Any]:
        clean_url = str(url or "").strip()
        if not clean_url:
            return {
                "url": clean_url,
                "status": "failed",
                "reason": "empty_url",
                "title": "",
                "excerpt": "",
                "paragraphs": [],
                "fetch_mode": "http_light",
                "cache_hit": False,
            }
        cached = self._get_rerank_excerpt_cache(clean_url, max_chars=max_chars)
        if cached is not None:
            return cached

        document = self._fetch_html_document(clean_url, timeout=max(3, int(timeout)))
        if document.get("status") != "ok":
            payload = {
                "url": clean_url,
                "status": "failed",
                "reason": str(document.get("reason", "") or "request_failed"),
                "title": "",
                "excerpt": "",
                "paragraphs": [],
                "fetch_mode": "http_light",
                "cache_hit": False,
            }
            self._set_rerank_excerpt_cache(clean_url, max_chars=max_chars, payload=payload)
            return payload

        html_text = str(document.get("html_text", "") or "")
        title = str(document.get("title", "") or "")
        description = self._extract_meta_description(html_text)
        content_text, paragraphs = self._extract_main_text(html_text, max_chars=max_chars, title=title)
        excerpt_parts: list[str] = []
        for candidate in [description, *paragraphs[:2], content_text[: max_chars // 2]]:
            cleaned = self._clean_text(candidate)
            if cleaned and cleaned not in excerpt_parts:
                excerpt_parts.append(cleaned)
        excerpt = "\n".join(excerpt_parts).strip()[:max_chars].strip()
        status = "ok" if excerpt or title else "failed"
        payload = {
            "url": clean_url,
            "status": status,
            "reason": "" if status == "ok" else "content_not_found",
            "title": title,
            "excerpt": excerpt,
            "paragraphs": paragraphs[:3],
            "fetch_mode": "http_light",
            "cache_hit": False,
        }
        self._set_rerank_excerpt_cache(clean_url, max_chars=max_chars, payload=payload)
        return payload

    def _render_page_html(self, url: str, *, timeout_ms: int = 30000) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {
                "url": url,
                "status": "failed",
                "reason": f"playwright_unavailable: {exc}",
                "html_text": "",
                "title": "",
                "fetch_mode": "browser_rendered",
            }

        browser = None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    ignore_https_errors=True,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
                    ),
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=max(5000, int(timeout_ms)))
                try:
                    page.wait_for_load_state("networkidle", timeout=min(max(3000, int(timeout_ms)), 8000))
                except Exception:
                    pass
                page.wait_for_timeout(1800)
                html_text = page.content() or ""
                title = page.title() or self._extract_html_title(html_text)
                context.close()
                browser.close()
                return {
                    "url": url,
                    "status": "ok",
                    "reason": "",
                    "html_text": html_text,
                    "title": title,
                    "fetch_mode": "browser_rendered",
                }
        except Exception as exc:
            return {
                "url": url,
                "status": "failed",
                "reason": f"browser_render_failed: {exc}",
                "html_text": "",
                "title": "",
                "fetch_mode": "browser_rendered",
            }
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    @classmethod
    def _looks_like_js_shell(
        cls,
        html_text: str,
        *,
        title: str = "",
        content_text: str = "",
        paragraphs: list[str] | None = None,
    ) -> bool:
        if str(content_text or "").strip():
            return False
        paragraph_items = [cls._clean_text(item) for item in (paragraphs or []) if cls._clean_text(item)]
        if any(len(item) >= 48 for item in paragraph_items[:3]):
            return False
        lowered = str(html_text or "").lower()
        if not lowered.strip():
            return False

        body = cls._match_body(html_text, lowered) or html_text
        visible = cls._clean_text(body)
        visible_len = len(visible)
        root_shell = bool(
            re.search(
                r"<div[^>]+id=[\"'](?:root|__next|app|app-root|__nuxt|root-app)[\"'][^>]*>\s*</div>",
                body,
                flags=re.IGNORECASE | re.DOTALL,
            )
        )
        module_signals = sum(
            1
            for marker in (
                'type="module"',
                "modulepreload",
                "/assets/",
                "__next",
                "__nuxt",
                "hydrateRoot",
                "createRoot(",
            )
            if marker in lowered
        )
        if root_shell and module_signals >= 1 and visible_len <= 180:
            return True
        if visible_len <= 80 and module_signals >= 2 and "<article" not in lowered and "<main" not in lowered:
            return True
        if title and visible and cls._clean_text(title) == visible and module_signals >= 1:
            return True
        return False

    @staticmethod
    def _has_meaningful_structure(structure: dict[str, Any]) -> bool:
        return bool(
            str(structure.get("lead", "") or "").strip()
            or list(structure.get("sections") or [])
            or list(structure.get("code_blocks") or [])
            or list(structure.get("lists") or [])
            or list(structure.get("tables") or [])
        )

    @staticmethod
    def _github_repo_slug(repo_url: str) -> str:
        url = str(repo_url or "").strip()
        if "github.com/" not in url.lower():
            return ""
        path = urlparse(url).path.strip("/")
        parts = [part for part in path.split("/") if part]
        if len(parts) < 2:
            return ""
        if parts[0].lower() in {"features", "topics", "orgs", "organizations", "marketplace"}:
            return ""
        return f"{parts[0]}/{parts[1]}"

    @classmethod
    def _looks_like_github_repo_url(cls, url: str) -> bool:
        return bool(cls._github_repo_slug(url))

    def _github_api_get_json(self, url: str, *, timeout: int = 15) -> dict[str, Any]:
        proxies = None
        if self.all_proxy:
            proxies = {"http": self.all_proxy, "https": self.all_proxy}
        headers = {
            "User-Agent": "wechat-agent-lite/1.0 (+github-repo-enricher)",
            "Accept": "application/vnd.github+json",
        }
        try:
            response = requests.get(url, timeout=timeout, headers=headers, proxies=proxies)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _github_file_language(cls, path: str) -> str:
        raw_path = str(path or "").strip()
        if not raw_path:
            return ""
        name = Path(raw_path).name.lower()
        if name in cls._GITHUB_SPECIAL_FILENAMES:
            return cls._GITHUB_SPECIAL_FILENAMES[name]
        suffix = Path(name).suffix.lower()
        return cls._GITHUB_LANGUAGE_BY_SUFFIX.get(suffix, "")

    @classmethod
    def _github_should_ignore_file(cls, path: str) -> bool:
        normalized = f"/{str(path or '').strip().lower().lstrip('/')}"
        if not normalized or normalized == "/":
            return True
        if any(marker in normalized for marker in cls._GITHUB_EXCLUDED_PATH_MARKERS):
            return True
        return False

    @classmethod
    def _github_repo_file_score(cls, path: str) -> float:
        normalized = str(path or "").strip().lower()
        if not normalized or cls._github_should_ignore_file(normalized):
            return -1.0
        language = cls._github_file_language(normalized)
        if not language:
            return -1.0
        filename = Path(normalized).name.lower()
        score = 0.0
        if filename in cls._GITHUB_SPECIAL_FILENAMES:
            score += 65.0
        if cls._github_is_lockfile(normalized):
            score -= 48.0
        if filename in {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            score += 24.0
        if filename in {"package.json", "pyproject.toml", "requirements.txt", "go.mod", "cargo.toml"}:
            score += 10.0
        if filename == ".env.example":
            score -= 18.0
        if normalized.startswith(("src/", "app/", "server/", "backend/", "api/", "core/", "lib/")):
            score += 45.0
        if any(marker in normalized for marker in ("/src/", "/app/", "/server/", "/backend/", "/api/", "/core/", "/lib/", "/packages/")):
            score += 25.0
        if any(token in filename for token in ("main", "index", "app", "server", "client", "router", "workflow", "agent", "runtime")):
            score += 20.0
        if filename in {"index.ts", "index.tsx", "index.js", "index.jsx", "__init__.py"} and not any(
            marker in normalized for marker in ("/api/", "/router", "/routes", "/server", "/app", "/runtime", "/store")
        ):
            score -= 22.0
        if any(marker in normalized for marker in cls._GITHUB_LOW_SIGNAL_PATH_MARKERS):
            score -= 25.0
        if cls._github_is_test_file(normalized):
            score -= 28.0
        if filename.startswith("readme"):
            score -= 80.0
        depth = max(0, normalized.count("/"))
        score += max(0.0, 8.0 - min(depth, 8))
        return score

    @staticmethod
    def _github_is_lockfile(path: str) -> bool:
        filename = Path(str(path or "").strip().lower()).name
        return filename in {"poetry.lock", "cargo.lock", "go.sum", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}

    @classmethod
    def _github_is_test_file(cls, path: str) -> bool:
        normalized = f"/{str(path or '').strip().lower().lstrip('/')}"
        if not normalized or normalized == "/":
            return False
        return any(marker in normalized for marker in ("/test/", "/tests/", "/spec/", "/__tests__/"))

    @classmethod
    def _github_is_deployment_file(cls, path: str) -> bool:
        normalized = str(path or "").strip().lower()
        filename = Path(normalized).name.lower()
        return filename in {
            "dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "go.mod",
            "cargo.toml",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "makefile",
            ".env.example",
        } or ".github/workflows/" in normalized

    @staticmethod
    def _extract_repo_file_snippet(text: str, *, path: str, max_chars: int = 1800, max_lines: int = 42) -> str:
        raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not raw.strip():
            return ""
        lines = raw.split("\n")
        suffix = Path(str(path or "")).suffix.lower()
        filename = Path(str(path or "")).name.lower()
        snippet = ""
        if suffix in {".md", ".mdx"}:
            fenced_blocks = re.findall(r"```([^\n`]*)\n([\s\S]*?)```", raw)
            for language, block in fenced_blocks:
                code_text = str(block or "").strip()
                if not code_text:
                    continue
                inferred_language = str(language or "").strip().lower()
                kind = FetchService._classify_code_block(text=code_text, language=inferred_language)
                if kind in {"command", "code"} and not FetchService._github_repo_snippet_is_low_signal(code_text, path=path):
                    return code_text[:max_chars].strip()
            markdown_lines = [
                line for line in lines
                if line.strip()
                and not line.lstrip().startswith("#")
                and not line.lstrip().startswith("```")
                and not re.match(r"^\s*[-*]\s+\[?.+\]?\s*$", line)
            ]
            snippet = "\n".join(markdown_lines[: max_lines // 2]).strip()[:max_chars].strip()
            return "" if FetchService._github_repo_snippet_is_low_signal(snippet, path=path) else snippet
        if filename in {
            "dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "go.mod",
            "cargo.toml",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "makefile",
            ".env.example",
        }:
            if filename == ".env.example":
                assignment_lines = [
                    line
                    for line in lines
                    if re.match(r"^\s*[A-Z][A-Z0-9_]*\s*=", str(line or ""))
                ]
                snippet_lines = assignment_lines[:max_lines] if assignment_lines else []
            else:
                snippet_lines = lines[:max_lines]
            snippet = "\n".join(snippet_lines).strip()[:max_chars].strip()
            return "" if FetchService._github_repo_snippet_is_low_signal(snippet, path=path) else snippet

        start_index = 0
        definition_patterns = (
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+",
            r"^\s*(?:export\s+)?class\s+\w+",
            r"^\s*def\s+\w+",
            r"^\s*func\s+\w+",
            r"^\s*pub\s+fn\s+\w+",
            r"^\s*(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?(?:\(|\w)",
            r"^\s*(?:app|router|server|workflow|graph)\.",
        )
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if any(re.search(pattern, line) for pattern in definition_patterns):
                start_index = idx
                break
        snippet_lines: list[str] = []
        total_chars = 0
        for line in lines[start_index:]:
            snippet_lines.append(line)
            total_chars += len(line) + 1
            if len(snippet_lines) >= max_lines or total_chars >= max_chars:
                break
        snippet = "\n".join(snippet_lines).strip()[:max_chars].strip()
        return "" if FetchService._github_repo_snippet_is_low_signal(snippet, path=path) else snippet

    @staticmethod
    def _github_repo_snippet_is_low_signal(snippet: str, *, path: str) -> bool:
        text = str(snippet or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return True
        nonempty = [line.strip() for line in text.split("\n") if line.strip()]
        if not nonempty:
            return True
        comment_like = tuple(prefix for prefix in ("#", "//", "/*", "*", "<!--", ";", "--"))
        if all(line.startswith(comment_like) for line in nonempty):
            return True
        filename = Path(str(path or "")).name.lower()
        if filename == ".env.example":
            return not any(re.match(r"^[A-Z][A-Z0-9_]*\s*=", line) for line in nonempty)
        meaningful_patterns = (
            r"\b(export|import|from|class|function|async|await|const|let|var|return|router|app|create|mount|writable|derived)\b",
            r"[{}();=<>]",
        )
        has_signal = any(re.search(pattern, line) for line in nonempty for pattern in meaningful_patterns)
        if filename in {"index.ts", "index.tsx", "index.js", "index.jsx", "__init__.py"} and not has_signal:
            return True
        if len(nonempty) <= 2 and not has_signal:
            return True
        return False

    @classmethod
    def _build_github_repo_section_heading(cls, path: str) -> str:
        filename = Path(str(path or "")).name
        if cls._github_is_deployment_file(path):
            return f"仓库部署文件：{filename}"
        return f"仓库源码：{path}"

    @staticmethod
    def _github_repo_is_collection_like(repo_meta: dict[str, Any]) -> bool:
        text = " ".join(
            str(repo_meta.get(key, "") or "").strip()
            for key in ("name", "description")
        )
        if not text:
            return False
        return bool(
            re.search(
                r"\b(awesome|collection|curated|examples?|playground|showcase|templates?|starter|boilerplate)\b",
                text,
                flags=re.IGNORECASE,
            )
        )

    @classmethod
    def _github_repo_focus_root(cls, path: str) -> str:
        normalized = str(path or "").strip().strip("/")
        if not normalized:
            return ""
        parts = [part for part in normalized.split("/") if part]
        if not parts:
            return ""
        service_markers = {
            "backend",
            "frontend",
            "src",
            "app",
            "server",
            "api",
            "core",
            "lib",
            "client",
            "web",
            "ui",
        }
        for idx, part in enumerate(parts):
            if part.lower() in service_markers and idx > 0:
                if idx == 1 and parts[0].lower() in {"apps", "packages", "services", "examples", "projects"}:
                    continue
                return "/".join(parts[:idx])
        if len(parts) <= 2:
            return "/".join(parts[:-1]) or normalized
        return "/".join(parts[:-1])

    @staticmethod
    def _github_focus_label(focus_root: str) -> str:
        normalized = str(focus_root or "").strip().strip("/")
        if not normalized:
            return ""
        return normalized.split("/")[-1]

    @classmethod
    def _choose_github_dominant_focus_root(
        cls,
        *,
        source_candidates: list[tuple[float, str]],
        deploy_candidates: list[tuple[float, str]],
    ) -> tuple[str, str, str]:
        root_scores: dict[str, float] = {}
        root_source_counts: dict[str, int] = {}
        root_deploy_counts: dict[str, int] = {}
        for score, path in source_candidates:
            root = cls._github_repo_focus_root(path)
            if not root or "/" not in root:
                continue
            root_scores[root] = root_scores.get(root, 0.0) + score
            root_source_counts[root] = root_source_counts.get(root, 0) + 1
        for score, path in deploy_candidates:
            root = cls._github_repo_focus_root(path)
            if not root or "/" not in root:
                continue
            root_scores[root] = root_scores.get(root, 0.0) + score * 0.35
            root_deploy_counts[root] = root_deploy_counts.get(root, 0) + 1
        if len(root_scores) < 2:
            return "", "", ""
        ranked_roots = sorted(
            root_scores,
            key=lambda root: (
                root_scores.get(root, 0.0),
                root_source_counts.get(root, 0),
                root_deploy_counts.get(root, 0),
                root.count("/"),
            ),
            reverse=True,
        )
        best_root = ranked_roots[0]
        best_score = float(root_scores.get(best_root, 0.0))
        best_source_count = int(root_source_counts.get(best_root, 0))
        best_deploy_count = int(root_deploy_counts.get(best_root, 0))
        second_score = float(root_scores.get(ranked_roots[1], 0.0)) if len(ranked_roots) >= 2 else 0.0
        second_source_count = int(root_source_counts.get(ranked_roots[1], 0)) if len(ranked_roots) >= 2 else 0
        if best_source_count < 2:
            return "", "", ""
        clearly_better = best_score >= second_score + 18.0 or best_score >= second_score * 1.18
        structurally_better = best_source_count > second_source_count or best_deploy_count >= 1
        if not clearly_better and not structurally_better:
            return "", "", ""
        return best_root, cls._github_focus_label(best_root), "dominant_service_root"

    def _extract_github_repo_context(self, repo_url: str) -> dict[str, Any]:
        repo_slug = self._github_repo_slug(repo_url)
        if not repo_slug:
            return {"status": "skipped", "reason": "not_github_repo", "sections": [], "code_blocks": [], "files": []}

        repo_meta = self._github_api_get_json(f"https://api.github.com/repos/{repo_slug}", timeout=15)
        default_branch = str(repo_meta.get("default_branch", "") or "").strip() or "main"
        collection_like = self._github_repo_is_collection_like(repo_meta)
        tree_payload = self._github_api_get_json(
            f"https://api.github.com/repos/{repo_slug}/git/trees/{default_branch}?recursive=1",
            timeout=20,
        )
        tree_items = [item for item in (tree_payload.get("tree") or []) if isinstance(item, dict) and item.get("type") == "blob"]
        if not tree_items:
            return {"status": "failed", "reason": "repo_tree_not_found", "sections": [], "code_blocks": [], "files": []}

        deploy_candidates: list[tuple[float, str]] = []
        source_candidates: list[tuple[float, str]] = []
        for item in tree_items:
            path = str(item.get("path", "") or "").strip()
            score = self._github_repo_file_score(path)
            if score <= 0:
                continue
            if self._github_is_deployment_file(path):
                deploy_candidates.append((score, path))
            else:
                source_candidates.append((score, path))
        deploy_candidates.sort(key=lambda item: (-item[0], item[1]))
        source_candidates.sort(key=lambda item: (-item[0], item[1]))
        preferred_source_candidates = [
            item for item in source_candidates if not self._github_is_test_file(item[1])
        ] or list(source_candidates)

        selected_paths: list[str] = []
        focus_root = ""
        focus_label = ""
        focus_reason = ""
        if collection_like:
            root_scores: dict[str, float] = {}
            root_source_counts: dict[str, int] = {}
            root_deploy_counts: dict[str, int] = {}
            source_by_root: dict[str, list[tuple[float, str]]] = {}
            deploy_by_root: dict[str, list[tuple[float, str]]] = {}
            for score, path in preferred_source_candidates:
                root = self._github_repo_focus_root(path)
                if not root:
                    continue
                root_scores[root] = root_scores.get(root, 0.0) + score
                root_source_counts[root] = root_source_counts.get(root, 0) + 1
                source_by_root.setdefault(root, []).append((score, path))
            for score, path in deploy_candidates:
                root = self._github_repo_focus_root(path)
                if not root:
                    continue
                root_scores[root] = root_scores.get(root, 0.0) + score * 0.35
                root_deploy_counts[root] = root_deploy_counts.get(root, 0) + 1
                deploy_by_root.setdefault(root, []).append((score, path))
            if len(root_scores) >= 2:
                focus_root = max(
                    root_scores,
                    key=lambda root: (
                        root_scores.get(root, 0.0),
                        root_source_counts.get(root, 0),
                        root_deploy_counts.get(root, 0),
                        root.count("/"),
                    ),
                )
                focus_label = self._github_focus_label(focus_root)
                focus_reason = "collection_repo_focused_subproject"
                for _, path in sorted(source_by_root.get(focus_root, []), key=lambda item: (-item[0], item[1]))[:3]:
                    if path not in selected_paths:
                        selected_paths.append(path)
                for _, path in sorted(deploy_by_root.get(focus_root, []), key=lambda item: (-item[0], item[1]))[:2]:
                    if path not in selected_paths:
                        selected_paths.append(path)

        if not selected_paths:
            dominant_root, dominant_label, dominant_reason = self._choose_github_dominant_focus_root(
                source_candidates=preferred_source_candidates,
                deploy_candidates=deploy_candidates,
            )
            if dominant_root:
                focus_root = dominant_root
                focus_label = dominant_label
                focus_reason = dominant_reason
                for _, path in preferred_source_candidates:
                    if self._github_repo_focus_root(path) == focus_root and path not in selected_paths:
                        selected_paths.append(path)
                    if len(selected_paths) >= 3:
                        break
                for _, path in deploy_candidates:
                    if self._github_repo_focus_root(path) == focus_root and path not in selected_paths:
                        selected_paths.append(path)
                    if len(selected_paths) >= 5:
                        break

        if not selected_paths:
            for _, path in preferred_source_candidates[:3]:
                if path not in selected_paths:
                    selected_paths.append(path)
            for _, path in deploy_candidates[:2]:
                if path not in selected_paths:
                    selected_paths.append(path)
            for _, path in preferred_source_candidates[3:]:
                if len(selected_paths) >= 5:
                    break
                if path not in selected_paths:
                    selected_paths.append(path)

        non_lock_selected = [path for path in selected_paths if not self._github_is_lockfile(path)]
        if non_lock_selected:
            selected_paths = non_lock_selected + [path for path in selected_paths if self._github_is_lockfile(path)]
        non_test_selected = [path for path in selected_paths if not self._github_is_test_file(path)]
        if len(non_test_selected) >= 2:
            selected_paths = non_test_selected + [path for path in selected_paths if self._github_is_test_file(path)]
        if len(non_lock_selected) >= 3:
            selected_paths = non_lock_selected[:3] + [
                path for path in selected_paths if path not in non_lock_selected[:3]
            ]

        code_blocks: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        for path in selected_paths:
            raw_url = f"https://raw.githubusercontent.com/{repo_slug}/{default_branch}/{quote(path, safe='/')}"
            try:
                response = self._request(raw_url, timeout=20)
                response.raise_for_status()
            except Exception:
                continue
            snippet = self._extract_repo_file_snippet(response.text, path=path)
            if not snippet:
                continue
            language = self._github_file_language(path)
            heading = self._build_github_repo_section_heading(path)
            summary = f"真实仓库文件片段，来自 {path}"
            code_index = len(code_blocks)
            code_blocks.append(
                {
                    "language": language,
                    "code_excerpt": snippet[:1200],
                    "code_text": snippet,
                    "line_count": len([line for line in snippet.splitlines() if line.strip()]),
                    "kind": self._classify_code_block(text=snippet, language=language),
                    "origin": "repo_file",
                    "source_path": path,
                }
            )
            sections.append(
                {
                    "heading": heading,
                    "level": 2,
                    "summary": summary,
                    "paragraphs": [summary],
                    "code_refs": [code_index],
                    "list_refs": [],
                    "table_refs": [],
                }
            )
            files.append(
                {
                    "path": path,
                    "language": language,
                    "kind": str(code_blocks[-1].get("kind", "code") or "code"),
                    "summary": summary,
                }
            )
        if not code_blocks:
            return {"status": "failed", "reason": "repo_source_snippets_not_found", "sections": [], "code_blocks": [], "files": []}
        return {
            "status": "ok",
            "reason": "",
            "repo_slug": repo_slug,
            "default_branch": default_branch,
            "is_collection_repo": collection_like,
            "focus_root": focus_root,
            "focus_label": focus_label,
            "focus_reason": focus_reason,
            "sections": sections,
            "code_blocks": code_blocks,
            "files": files,
        }

    @staticmethod
    def sources_path() -> Path:
        path = Path(CONFIG.data_dir).parents[0] / "config" / "sources.yaml"
        if not path.exists():
            # fallback for dev in project root
            path = Path(__file__).resolve().parents[2] / "config" / "sources.yaml"
        return path

    def _request(self, url: str, timeout: int = 15) -> requests.Response:
        proxies = None
        if self.all_proxy:
            proxies = {"http": self.all_proxy, "https": self.all_proxy}
        headers = {"User-Agent": "wechat-agent-lite/1.0 (+rss-fetcher)"}
        try:
            response = requests.get(url, timeout=timeout, headers=headers, proxies=proxies)
            setattr(response, "_wal_proxy_fallback", False)
            return response
        except Exception as exc:
            if proxies and "SOCKS" in str(exc).upper():
                response = requests.get(url, timeout=timeout, headers=headers)
                setattr(response, "_wal_proxy_fallback", True)
                setattr(response, "_wal_proxy_fallback_reason", str(exc))
                return response
            raise

    def load_sources(self) -> dict[str, Any]:
        path = self.sources_path()
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def save_sources(self, payload: dict[str, Any]) -> None:
        path = self.sources_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        dumped = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
        temp_path.write_text(dumped, encoding="utf-8", newline="\n")
        temp_path.replace(path)

    def extract_article_content(self, url: str, max_chars: int = 8000, include_images: bool = True) -> dict[str, Any]:
        if not url.strip():
            return {"url": url, "status": "failed", "reason": "empty_url", "title": "", "content_text": "", "paragraphs": [], "images": []}
        document = self._fetch_html_document(url, timeout=20)
        if document.get("status") != "ok":
            return {
                "url": url,
                "status": "failed",
                "reason": str(document.get("reason", "") or "request_failed"),
                "title": "",
                "content_text": "",
                "paragraphs": [],
                "images": [],
            }

        html_text = str(document.get("html_text", "") or "")
        title = str(document.get("title", "") or "")
        content_text, paragraphs = self._extract_main_text(html_text, max_chars=max_chars, title=title)
        images = (
            self._extract_html_images(
                html_text,
                base_url=url,
                max_items=6,
                article_title=title,
                article_hint=" ".join(paragraphs[:2]),
            )
            if include_images
            else []
        )
        fetch_mode = str(document.get("fetch_mode", "http") or "http")
        shell_like = self._looks_like_js_shell(html_text, title=title, content_text=content_text, paragraphs=paragraphs)
        if not content_text and shell_like:
            # Some official blogs only return an empty SPA shell to raw HTTP clients.
            rendered = self._render_page_html(url, timeout_ms=30000)
            if rendered.get("status") == "ok":
                html_text = str(rendered.get("html_text", "") or "")
                title = str(rendered.get("title", "") or "") or self._extract_html_title(html_text) or title
                content_text, paragraphs = self._extract_main_text(html_text, max_chars=max_chars, title=title)
                images = (
                    self._extract_html_images(
                        html_text,
                        base_url=url,
                        max_items=6,
                        article_title=title,
                        article_hint=" ".join(paragraphs[:2]),
                    )
                    if include_images
                    else []
                )
                fetch_mode = str(rendered.get("fetch_mode", "") or fetch_mode)
            else:
                document["reason"] = rendered.get("reason", "") or "spa_shell_detected"
        if not content_text:
            return {
                "url": url,
                "status": "failed",
                "reason": str(document.get("reason", "") or ("spa_shell_detected" if shell_like else "content_not_found")),
                "title": title,
                "content_text": "",
                "paragraphs": [],
                "images": images,
                "fetch_mode": fetch_mode,
            }
        return {
            "url": url,
            "status": "ok",
            "reason": "",
            "title": title,
            "content_text": content_text,
            "paragraphs": paragraphs,
            "images": images,
            "fetch_mode": fetch_mode,
        }

    def extract_lightweight_image_candidates(
        self,
        url: str,
        *,
        max_items: int = 4,
        timeout: int = 8,
        article_title: str = "",
        article_hint: str = "",
    ) -> list[dict[str, Any]]:
        clean_url = str(url or "").strip()
        if not clean_url:
            return []
        document = self._fetch_html_document(clean_url, timeout=timeout)
        if document.get("status") != "ok":
            return []
        html_text = str(document.get("html_text", "") or "")
        title = str(document.get("title", "") or "")
        return self._extract_lightweight_html_images(
            html_text,
            base_url=clean_url,
            max_items=max_items,
            article_title=article_title or title,
            article_hint=article_hint,
        )

    def extract_article_structure(self, url: str, max_chars: int = 12000) -> dict[str, Any]:
        if not url.strip():
            return {
                "url": url,
                "status": "failed",
                "reason": "empty_url",
                "title": "",
                "lead": "",
                "sections": [],
                "code_blocks": [],
                "lists": [],
                "tables": [],
                "coverage_checklist": [],
            }
        document = self._fetch_html_document(url, timeout=20)
        if document.get("status") != "ok":
            return {
                "url": url,
                "status": "failed",
                "reason": str(document.get("reason", "") or "request_failed"),
                "title": "",
                "lead": "",
                "sections": [],
                "code_blocks": [],
                "lists": [],
                "tables": [],
                "coverage_checklist": [],
            }

        html_text = str(document.get("html_text", "") or "")
        title = str(document.get("title", "") or "")
        structure = self._build_article_structure(html_text, title=title, max_chars=max_chars)
        fetch_mode = str(document.get("fetch_mode", "http") or "http")
        shell_like = self._looks_like_js_shell(html_text, title=title)
        if not self._has_meaningful_structure(structure) and shell_like:
            rendered = self._render_page_html(url, timeout_ms=30000)
            if rendered.get("status") == "ok":
                html_text = str(rendered.get("html_text", "") or "")
                title = str(rendered.get("title", "") or "") or self._extract_html_title(html_text) or title
                structure = self._build_article_structure(html_text, title=title, max_chars=max_chars)
                fetch_mode = str(rendered.get("fetch_mode", "") or fetch_mode)
            else:
                document["reason"] = rendered.get("reason", "") or "spa_shell_detected"
        if not self._has_meaningful_structure(structure):
            return {
                "url": url,
                "status": "failed",
                "reason": str(document.get("reason", "") or ("spa_shell_detected" if shell_like else "content_not_found")),
                "title": title,
                "lead": "",
                "sections": [],
                "code_blocks": [],
                "lists": [],
                "tables": [],
                "coverage_checklist": [],
                "fetch_mode": fetch_mode,
            }
        if self._looks_like_github_repo_url(url):
            repo_context = self._extract_github_repo_context(url)
            if repo_context.get("status") == "ok":
                repo_code_blocks = list(repo_context.get("code_blocks") or [])
                repo_sections = list(repo_context.get("sections") or [])
                if repo_code_blocks:
                    shift = len(repo_code_blocks)
                    shifted_sections: list[dict[str, Any]] = []
                    for section in list(structure.get("sections") or []):
                        item = dict(section)
                        refs = [int(ref) + shift for ref in (section.get("code_refs") or [])]
                        item["code_refs"] = refs[:3]
                        shifted_sections.append(item)
                    structure["code_blocks"] = repo_code_blocks + list(structure.get("code_blocks") or [])
                    structure["sections"] = repo_sections + shifted_sections
                    structure["github_repo_context"] = {
                        "repo_slug": repo_context.get("repo_slug", ""),
                        "default_branch": repo_context.get("default_branch", ""),
                        "is_collection_repo": bool(repo_context.get("is_collection_repo")),
                        "focus_root": repo_context.get("focus_root", ""),
                        "focus_label": repo_context.get("focus_label", ""),
                        "focus_reason": repo_context.get("focus_reason", ""),
                        "files": repo_context.get("files", []),
                    }
        structure["url"] = url
        structure["fetch_mode"] = fetch_mode
        return structure

    def fetch_rss(self, source: dict[str, Any], max_age_hours: int, max_items: int) -> list[dict[str, Any]]:
        response = self._request(source["url"], timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        items: list[dict[str, Any]] = []
        source_meta = self._source_meta(source)
        for entry in feed.entries[:max_items]:
            time_meta = _parse_time(entry)
            published_dt = time_meta.get("published_dt")
            published_meta = self._published_payload(
                published_dt,
                source=str(time_meta.get("published_source", "") or ""),
                confidence=str(time_meta.get("published_confidence", "low") or "low"),
                status="unknown" if published_dt is None else "fresh",
            )
            entry_url = str(entry.get("link", "") or "").strip()
            if published_dt is None and entry_url:
                article_meta = self.extract_article_metadata(entry_url)
                inferred_dt = _coerce_utc_datetime(article_meta.get("published"))
                if inferred_dt is not None:
                    published_dt = inferred_dt
                    published_meta = self._published_payload(
                        inferred_dt,
                        source=str(article_meta.get("published_source", "") or "html_meta"),
                        confidence=str(article_meta.get("published_confidence", "medium") or "medium"),
                    )
            if published_dt is not None and published_dt < cutoff:
                continue
            items.append(
                {
                    "title": entry.get("title", "").strip(),
                    "url": entry_url,
                    "summary": (entry.get("summary", "") or "").strip()[:500],
                    **published_meta,
                    "source": source["name"],
                    "source_weight": float(source.get("weight", 0.7)),
                    "type": "rss",
                    **source_meta,
                }
            )
        return items

    def fetch_html_list(
        self,
        source: dict[str, Any],
        *,
        max_age_hours: int,
        max_items: int,
        scrapling: Any | None = None,
    ) -> list[dict[str, Any]]:
        if scrapling is None:
            raise RuntimeError("scrapling_fallback_unavailable")
        raw_items = scrapling.build_html_list_items(
            url=str(source.get("url", "") or "").strip(),
            source_name=str(source.get("name", "") or ""),
            source_weight=float(source.get("weight", 0.7) or 0.7),
            max_items=max_items,
        )
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        items: list[dict[str, Any]] = []
        for item in raw_items:
            normalized = self._normalize_html_list_item(item=item, source=source)
            if not normalized:
                continue
            published_dt = _coerce_utc_datetime(normalized.get("published"))
            if published_dt is not None and published_dt < cutoff:
                continue
            items.append(normalized)
            if len(items) >= max_items:
                break
        return items

    def fetch_source(
        self,
        source: dict[str, Any],
        *,
        max_age_hours: int,
        max_items: int,
        scrapling: Any | None = None,
    ) -> list[dict[str, Any]]:
        mode = str(source.get("mode", "rss") or "rss").strip().lower()
        if mode == "html_list":
            return self.fetch_html_list(source, max_age_hours=max_age_hours, max_items=max_items, scrapling=scrapling)
        return self.fetch_rss(source, max_age_hours=max_age_hours, max_items=max_items)

    @staticmethod
    def _normalize_github_query_string(query: str, *, min_stars: int) -> str:
        normalized = re.sub(r"\s+", " ", str(query or "").strip())
        if not normalized:
            return ""
        if re.search(r"\bstars:\s*[<>]=?\s*\d+", normalized):
            return normalized
        if min_stars > 0:
            return f"{normalized} stars:>={min_stars}"
        return normalized

    @staticmethod
    def _legacy_github_query(github_cfg: dict[str, Any]) -> str:
        languages = " ".join(f"language:{x}" for x in github_cfg.get("languages", ["python"]))
        topics = " ".join(f"topic:{x}" for x in github_cfg.get("topics", ["llm"]))
        min_stars = int(github_cfg.get("min_stars", 10))
        return FetchService._normalize_github_query_string(
            f"{languages} {topics}".strip(),
            min_stars=min_stars,
        )

    @classmethod
    def _github_query_groups(cls, github_cfg: dict[str, Any]) -> list[dict[str, Any]]:
        configured = github_cfg.get("query_groups") or github_cfg.get("queries") or []
        default_min_stars = int(github_cfg.get("min_stars", 10))
        default_per_query = int(github_cfg.get("max_results_per_query", github_cfg.get("max_results", 20)))
        default_weight = float(github_cfg.get("weight", 0.85) or 0.85)
        groups: list[dict[str, Any]] = []
        if isinstance(configured, list):
            for index, entry in enumerate(configured, start=1):
                if isinstance(entry, str):
                    raw_query = entry
                    name = f"query-{index}"
                    min_stars = default_min_stars
                    per_page = default_per_query
                    weight = default_weight
                elif isinstance(entry, dict):
                    raw_query = str(entry.get("q") or entry.get("query") or "").strip()
                    if not raw_query:
                        languages = " ".join(f"language:{lang}" for lang in (entry.get("languages") or []))
                        topics = " ".join(f"topic:{topic}" for topic in (entry.get("topics") or []))
                        terms = " ".join(str(term or "").strip() for term in (entry.get("terms") or []))
                        raw_query = " ".join(part for part in (languages, topics, terms) if part).strip()
                    name = str(entry.get("name") or entry.get("label") or f"query-{index}").strip() or f"query-{index}"
                    min_stars = int(entry.get("min_stars", default_min_stars))
                    per_page = int(entry.get("max_results", default_per_query))
                    weight = float(entry.get("weight", default_weight) or default_weight)
                else:
                    continue
                query = cls._normalize_github_query_string(raw_query, min_stars=min_stars)
                if not query:
                    continue
                groups.append(
                    {
                        "name": name,
                        "q": query,
                        "per_page": max(1, per_page),
                        "weight": weight,
                    }
                )
        if groups:
            return groups
        return [
            {
                "name": "default",
                "q": cls._legacy_github_query(github_cfg),
                "per_page": max(1, default_per_query),
                "weight": default_weight,
            }
        ]

    def fetch_github(self, github_cfg: dict[str, Any], max_age_hours: int) -> list[dict[str, Any]]:
        if not github_cfg.get("enabled", True):
            return []
        queries = self._github_query_groups(github_cfg)
        source_pools = github_cfg.get("pools") or ["github"]
        if not isinstance(source_pools, list):
            source_pools = [source_pools]
        proxies = None
        if self.all_proxy:
            proxies = {"http": self.all_proxy, "https": self.all_proxy}
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        collected: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for query_group in queries:
            params = {
                "q": str(query_group.get("q", "") or "").strip(),
                "sort": "stars",
                "order": "desc",
                "per_page": int(query_group.get("per_page", github_cfg.get("max_results", 20)) or github_cfg.get("max_results", 20)),
            }
            try:
                response = requests.get(
                    "https://api.github.com/search/repositories",
                    params=params,
                    timeout=30,
                    proxies=proxies,
                    headers={"User-Agent": "wechat-agent-lite/1.0 (+github-fetcher)"},
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                errors.append(f"{query_group.get('name', 'default')}: {exc}")
                continue

            group_name = str(query_group.get("name", "") or "default")
            source_weight = float(query_group.get("weight", github_cfg.get("weight", 0.85)) or 0.85)
            for repo in payload.get("items", []):
                updated = datetime.strptime(repo["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if updated < cutoff:
                    continue
                repo_url = str(repo.get("html_url", "") or "").strip()
                if not repo_url:
                    continue
                item = {
                    "title": repo["name"],
                    "url": repo_url,
                    "summary": (repo.get("description") or "")[:500],
                    **self._published_payload(updated, source="github_updated_at", confidence="high"),
                    "source": "GitHub Trending",
                    "source_weight": source_weight,
                    "type": "github",
                    "stars": int(repo.get("stargazers_count", 0)),
                    "github_query_groups": [group_name],
                    "source_category": "github",
                    "source_tier": str(github_cfg.get("tier", "core") or "core").strip().lower(),
                    "source_mode": "github",
                    "source_pools": [str(pool or "").strip().lower() for pool in source_pools if str(pool or "").strip()],
                }
                existing = collected.get(repo_url)
                if existing is None:
                    collected[repo_url] = item
                    continue
                if group_name not in existing.setdefault("github_query_groups", []):
                    existing["github_query_groups"].append(group_name)
                existing["stars"] = max(int(existing.get("stars", 0) or 0), item["stars"])
                if str(item["published"]) > str(existing.get("published", "") or ""):
                    existing["published"] = item["published"]
                if len(str(item["summary"] or "").strip()) > len(str(existing.get("summary", "") or "").strip()):
                    existing["summary"] = item["summary"]
                existing["source_weight"] = max(float(existing.get("source_weight", 0.85) or 0.85), source_weight)
                existing_pools = set(existing.get("source_pools") or [])
                for pool in item.get("source_pools") or []:
                    existing_pools.add(pool)
                existing["source_pools"] = sorted(existing_pools)
        if not collected and errors:
            raise RuntimeError("; ".join(errors[:3]))
        out = list(collected.values())
        out.sort(key=lambda item: (-int(item.get("stars", 0) or 0), str(item.get("published", "") or ""), str(item.get("title", "") or "")))
        return out[: int(github_cfg.get("max_results", 20))]

    @staticmethod
    def dedup(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_url: dict[str, dict[str, Any]] = {}
        for item in items:
            url = item.get("url", "").strip()
            if not url:
                continue
            existing = by_url.get(url)
            if existing is None:
                by_url[url] = dict(item)
                continue
            if len(str(item.get("summary", "") or "").strip()) > len(str(existing.get("summary", "") or "").strip()):
                existing["summary"] = item.get("summary", "")
            if not str(existing.get("title", "") or "").strip() and str(item.get("title", "") or "").strip():
                existing["title"] = item.get("title", "")
            existing["source_weight"] = max(float(existing.get("source_weight", 0.0) or 0.0), float(item.get("source_weight", 0.0) or 0.0))
            pools = set(existing.get("source_pools") or [])
            for pool in item.get("source_pools") or []:
                pools.add(pool)
            if pools:
                existing["source_pools"] = sorted(pools)
        return list(by_url.values())

    @staticmethod
    def dump_debug(items: list[dict[str, Any]], run_id: str) -> None:
        target = CONFIG.data_dir / "runs" / run_id
        target.mkdir(parents=True, exist_ok=True)
        with (target / "hotspots.json").open("w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _extract_html_title(html_text: str) -> str:
        patterns = [
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\'](.*?)["\']',
            r"<title[^>]*>(.*?)</title>",
        ]
        for pattern in patterns:
            match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return FetchService._clean_text(match.group(1))
        return ""

    def extract_article_metadata(self, url: str) -> dict[str, str]:
        if not url.strip():
            return {"title": "", "published": "", "published_source": "", "published_confidence": "low", "summary": ""}
        document = self._fetch_html_document(url, timeout=20)
        if document.get("status") != "ok":
            return {"title": "", "published": "", "published_source": "", "published_confidence": "low", "summary": ""}
        html_text = str(document.get("html_text", "") or "")
        title = str(document.get("title", "") or "")
        published_meta = self._extract_html_published_metadata(html_text, url=url)
        content_text, paragraphs = self._extract_main_text(html_text, max_chars=1200)
        shell_like = self._looks_like_js_shell(html_text, title=title, content_text=content_text, paragraphs=paragraphs)
        if not content_text and shell_like:
            rendered = self._render_page_html(url, timeout_ms=30000)
            if rendered.get("status") == "ok":
                html_text = str(rendered.get("html_text", "") or "")
                title = str(rendered.get("title", "") or "") or self._extract_html_title(html_text) or title
                refreshed_meta = self._extract_html_published_metadata(html_text, url=url)
                if refreshed_meta.get("published"):
                    published_meta = refreshed_meta
                content_text, paragraphs = self._extract_main_text(html_text, max_chars=1200, title=title)
        summary = ""
        for paragraph in paragraphs:
            cleaned = self._clean_text(paragraph)
            if len(cleaned) >= 24 and cleaned != title:
                summary = cleaned[:500]
                break
        if not summary and content_text:
            summary = self._clean_text(content_text)[:500]
        return {
            "title": title,
            "published": str(published_meta.get("published", "") or ""),
            "published_source": str(published_meta.get("published_source", "") or ""),
            "published_confidence": str(published_meta.get("published_confidence", "low") or "low"),
            "summary": summary,
        }

    @staticmethod
    def _extract_main_text(html_text: str, max_chars: int = 8000, title: str = "") -> tuple[str, list[str]]:
        lowered = html_text.lower()
        candidates = [
            FetchService._match_first_block(html_text, lowered, "article"),
            FetchService._match_first_block(html_text, lowered, "main"),
            FetchService._match_body(html_text, lowered),
            html_text,
        ]
        best_blocks: list[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            blocks = FetchService._html_to_blocks(candidate)
            if len(" ".join(blocks)) > len(" ".join(best_blocks)):
                best_blocks = blocks

        filtered: list[str] = []
        seen: set[str] = set()
        total_len = 0
        for block in best_blocks:
            cleaned = FetchService._clean_text(block)
            if len(cleaned) < 24:
                continue
            if title and FetchService._clean_text(cleaned) == FetchService._clean_text(title):
                continue
            if FetchService._looks_like_editorial_noise(cleaned):
                continue
            lowered_block = cleaned.lower()
            if any(noise in lowered_block for noise in ("cookie", "subscribe now", "privacy policy", "all rights reserved")):
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            filtered.append(cleaned)
            total_len += len(cleaned)
            if total_len >= max_chars:
                break

        content_text = "\n\n".join(filtered)
        return content_text[:max_chars].strip(), filtered[:24]

    @classmethod
    def _extract_html_images(
        cls,
        html_text: str,
        *,
        base_url: str,
        max_items: int = 6,
        article_title: str = "",
        article_hint: str = "",
    ) -> list[dict[str, Any]]:
        if not html_text.strip():
            return []

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        article_tokens = cls._image_tokens(" ".join([article_title, article_hint]))

        def add_candidate(
            url: str,
            *,
            alt: str = "",
            caption: str = "",
            source: str = "body",
            score: int = 0,
            context_text: str = "",
        ) -> None:
            normalized = cls._normalize_image_url(url, base_url=base_url)
            if not normalized or normalized in seen or cls._should_skip_image_url(normalized):
                return
            noisy_text = " ".join([str(alt or ""), str(caption or ""), str(context_text or ""), normalized])
            if re.search(r"\b(?:author|editor|byline|headshot|portrait|avatar|staff)\b", noisy_text, flags=re.IGNORECASE):
                return
            seen.add(normalized)
            text = cls._clean_text(alt or caption)
            context = cls._clean_text(context_text)
            signal_tokens = cls._image_tokens(" ".join([text, context, normalized]))
            relevance_hits = len(article_tokens & signal_tokens)
            adjusted_score = int(score)
            if relevance_hits > 0:
                adjusted_score += min(54, relevance_hits * 18)
            else:
                adjusted_score -= 24
            candidates.append(
                {
                    "url": normalized,
                    "alt": text[:160],
                    "caption": text[:200],
                    "context": context[:220],
                    "source": source,
                    "score": adjusted_score,
                    "relevance_hits": relevance_hits,
                    "host": urlparse(normalized).netloc.lower(),
                }
            )

        meta_pairs = [
            ("og", cls._extract_meta_content(html_text, "property", "og:image"), cls._extract_meta_content(html_text, "property", "og:image:alt")),
            ("twitter", cls._extract_meta_content(html_text, "name", "twitter:image"), cls._extract_meta_content(html_text, "name", "twitter:image:alt")),
        ]
        for source_name, image_url, image_alt in meta_pairs:
            if image_url:
                add_candidate(
                    image_url,
                    alt=image_alt,
                    source=f"meta_{source_name}",
                    score=72 if source_name == "og" else 64,
                    context_text="",
                )

        fragment = (
            cls._match_first_block(html_text, html_text.lower(), "article")
            or cls._match_first_block(html_text, html_text.lower(), "main")
            or cls._match_body(html_text, html_text.lower())
            or html_text
        )
        sanitized = re.sub(
            r"<(script|style|svg|noscript|iframe|form|button|nav|footer|header|aside)[^>]*>.*?</\1>",
            " ",
            fragment,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for match in re.finditer(r"<img\b([^>]*)>", sanitized, flags=re.IGNORECASE | re.DOTALL):
            attrs = match.group(1)
            attr_map = cls._parse_html_attrs(attrs)
            src = (
                attr_map.get("src")
                or attr_map.get("data-src")
                or attr_map.get("data-original")
                or cls._pick_src_from_srcset(attr_map.get("srcset", ""))
            )
            alt = attr_map.get("alt", "") or attr_map.get("title", "")
            class_name = str(attr_map.get("class", "") or "").lower()
            if any(token in class_name for token in ("author-card", "promo", "logo", "avatar", "headshot", "byline")):
                continue
            if re.search(r"\b(?:author|editor|byline|headshot|portrait|avatar|staff)\b", f"{alt} {class_name}", flags=re.IGNORECASE):
                continue
            ctx_start = max(0, match.start() - 500)
            ctx_end = min(len(sanitized), match.end() + 500)
            context_html = sanitized[ctx_start:ctx_end]
            context_text = cls._clean_text(re.sub(r"<[^>]+>", " ", context_html))
            score = 60
            if alt and len(cls._clean_text(alt)) >= 6:
                score += 8
            width = cls._int_from_text(attr_map.get("width", ""))
            height = cls._int_from_text(attr_map.get("height", ""))
            if max(width, height) >= 280:
                score += 8
            add_candidate(src or "", alt=alt, source="body", score=score, context_text=context_text)

        candidates.sort(
            key=lambda item: (
                -int(item.get("relevance_hits", 0) or 0),
                -int(item.get("score", 0) or 0),
                item.get("url", ""),
            )
        )
        return [
            {
                "url": str(item.get("url", "") or ""),
                "alt": str(item.get("alt", "") or ""),
                "caption": str(item.get("caption", "") or ""),
                "context": str(item.get("context", "") or ""),
                "source": str(item.get("source", "") or ""),
                "score": int(item.get("score", 0) or 0),
                "relevance_hits": int(item.get("relevance_hits", 0) or 0),
                "host": str(item.get("host", "") or ""),
            }
            for item in candidates[:max_items]
        ]

    @classmethod
    def _extract_lightweight_html_images(
        cls,
        html_text: str,
        *,
        base_url: str,
        max_items: int = 4,
        article_title: str = "",
        article_hint: str = "",
    ) -> list[dict[str, Any]]:
        if not html_text.strip():
            return []

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        article_tokens = cls._image_tokens(" ".join([article_title, article_hint]))

        def add_candidate(
            url: str,
            *,
            alt: str = "",
            caption: str = "",
            source: str = "body",
            score: int = 0,
            context_text: str = "",
        ) -> None:
            normalized = cls._normalize_image_url(url, base_url=base_url)
            if not normalized or normalized in seen or cls._should_skip_image_url(normalized):
                return
            seen.add(normalized)
            text = cls._clean_text(alt or caption)
            context = cls._clean_text(context_text)
            signal_tokens = cls._image_tokens(" ".join([text, context, normalized]))
            candidates.append(
                {
                    "url": normalized,
                    "alt": text[:160],
                    "caption": text[:200],
                    "context": context[:220],
                    "source": source,
                    "score": int(score),
                    "relevance_hits": len(article_tokens & signal_tokens),
                    "host": urlparse(normalized).netloc.lower(),
                }
            )

        meta_pairs = [
            ("meta_og", cls._extract_meta_content(html_text, "property", "og:image"), cls._extract_meta_content(html_text, "property", "og:image:alt")),
            ("meta_twitter", cls._extract_meta_content(html_text, "name", "twitter:image"), cls._extract_meta_content(html_text, "name", "twitter:image:alt")),
            ("link_image_src", cls._extract_link_href(html_text, "image_src"), ""),
        ]
        for source_name, image_url, image_alt in meta_pairs:
            if image_url:
                add_candidate(image_url, alt=image_alt, source=source_name, score=90 if source_name == "meta_og" else 82)

        fragment = (
            cls._match_first_block(html_text, html_text.lower(), "article")
            or cls._match_first_block(html_text, html_text.lower(), "main")
            or cls._match_body(html_text, html_text.lower())
            or html_text
        )
        sanitized = re.sub(
            r"<(script|style|svg|noscript|iframe|form|button|nav|footer|header|aside)[^>]*>.*?</\1>",
            " ",
            fragment,
            flags=re.IGNORECASE | re.DOTALL,
        )
        hero_matches = 0
        for match in re.finditer(r"<img\b([^>]*)>", sanitized[:8000], flags=re.IGNORECASE | re.DOTALL):
            attrs = cls._parse_html_attrs(match.group(1))
            src = (
                attrs.get("src")
                or attrs.get("data-src")
                or attrs.get("data-original")
                or cls._pick_src_from_srcset(attrs.get("srcset", ""))
            )
            alt = attrs.get("alt", "") or attrs.get("title", "")
            class_name = str(attrs.get("class", "") or "").lower()
            if any(token in class_name for token in ("author-card", "promo", "logo", "avatar", "headshot", "byline")):
                continue
            width = cls._int_from_text(attrs.get("width", ""))
            height = cls._int_from_text(attrs.get("height", ""))
            if width and width < 240 and height and height < 240:
                continue
            ctx_start = max(0, match.start() - 180)
            ctx_end = min(len(sanitized), match.end() + 180)
            context_html = sanitized[ctx_start:ctx_end]
            context_text = cls._clean_text(re.sub(r"<[^>]+>", " ", context_html))
            add_candidate(src or "", alt=alt, source="hero_image", score=70, context_text=context_text)
            hero_matches += 1
            if hero_matches >= 2 or len(candidates) >= max_items:
                break

        candidates.sort(
            key=lambda item: (
                -int(item.get("relevance_hits", 0) or 0),
                -int(item.get("score", 0) or 0),
                item.get("url", ""),
            )
        )
        return [dict(item) for item in candidates[:max_items]]

    @staticmethod
    def _match_first_block(html_text: str, lowered: str, tag_name: str) -> str:
        start = lowered.find(f"<{tag_name}")
        if start < 0:
            return ""
        end = lowered.find(f"</{tag_name}>", start)
        if end < 0:
            return ""
        end += len(tag_name) + 3
        return html_text[start:end]

    @staticmethod
    def _match_body(html_text: str, lowered: str) -> str:
        start = lowered.find("<body")
        if start < 0:
            return ""
        end = lowered.find("</body>", start)
        if end < 0:
            return ""
        return html_text[start : end + len("</body>")]

    @staticmethod
    def _extract_meta_content(html_text: str, attr_name: str, attr_value: str) -> str:
        patterns = [
            rf'<meta[^>]+{attr_name}=["\']{re.escape(attr_value)}["\'][^>]+content=["\'](.*?)["\']',
            rf'<meta[^>]+content=["\'](.*?)["\'][^>]+{attr_name}=["\']{re.escape(attr_value)}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return html.unescape(str(match.group(1) or "").strip())
        return ""

    @staticmethod
    def _extract_link_href(html_text: str, rel_value: str) -> str:
        patterns = [
            rf'<link[^>]+rel=["\']{re.escape(rel_value)}["\'][^>]+href=["\'](.*?)["\']',
            rf'<link[^>]+href=["\'](.*?)["\'][^>]+rel=["\']{re.escape(rel_value)}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return html.unescape(str(match.group(1) or "").strip())
        return ""

    @staticmethod
    def _parse_html_attrs(attrs: str) -> dict[str, str]:
        output: dict[str, str] = {}
        for key, _, value in re.findall(r'([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(["\'])(.*?)\2', attrs or "", flags=re.DOTALL):
            output[key.lower()] = html.unescape(str(value or "").strip())
        return output

    @staticmethod
    def _pick_src_from_srcset(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        first = raw.split(",", 1)[0].strip()
        return first.split(" ", 1)[0].strip()

    @staticmethod
    def _normalize_image_url(url: str, *, base_url: str) -> str:
        raw = html.unescape(str(url or "").strip())
        if not raw or raw.startswith("data:image/"):
            return ""
        if raw.startswith("//"):
            parsed = urlparse(base_url)
            raw = f"{parsed.scheme or 'https'}:{raw}"
        normalized = urljoin(base_url, raw)
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return normalized

    @staticmethod
    def _should_skip_image_url(url: str) -> bool:
        lowered = str(url or "").lower()
        if not lowered:
            return True
        if lowered.endswith(".svg"):
            return True
        skip_tokens = ("logo", "icon", "avatar", "emoji", "sprite", "favicon", "badge")
        return any(token in lowered for token in skip_tokens)

    @staticmethod
    def _int_from_text(value: str) -> int:
        match = re.search(r"\d+", str(value or ""))
        return int(match.group(0)) if match else 0

    @staticmethod
    def _image_tokens(text: str) -> set[str]:
        raw = str(text or "").strip().lower()
        if not raw:
            return set()
        tokens = re.findall(r"[a-z0-9][a-z0-9._/-]{2,}|[\u4e00-\u9fff]{2,8}", raw)
        stopwords = {
            "image", "images", "photo", "photos", "credit", "credits", "usage", "support",
            "this", "that", "with", "from", "will", "need", "have", "about", "article",
            "news", "today", "update", "story", "techcrunch", "gettyimages", "getty",
        }
        return {token for token in tokens if token not in stopwords}

    @staticmethod
    def _html_to_blocks(fragment: str) -> list[str]:
        text = fragment
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
        text = re.sub(r"<(script|style|svg|noscript|iframe|form|button|nav|footer|header|aside)[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</(p|div|section|article|main|li|ul|ol|h1|h2|h3|h4|h5|h6)>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        blocks = re.split(r"\n+", text)
        return [FetchService._clean_text(block) for block in blocks if FetchService._clean_text(block)]

    @staticmethod
    def _looks_like_editorial_noise(text: str) -> bool:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return False
        markers = [
            "this week only",
            "save up to",
            "save close to",
            "register now",
            "offer ends",
            "disrupt 2026",
            "most popular",
            "image credits",
            "getty images",
            "topics",
            "related video",
            "recommended videos",
            "advertisement",
            "sponsored",
            "sign up for",
            "save your spot",
            "your next round",
            "your next hire",
            "breakout opportunity",
            "meet your next investor",
            "portfolio startup",
            "this founder helped build",
            "developer of veracrypt",
            "you may also like",
            "more from techcrunch",
            "recommended reading",
            "read more:",
        ]
        if re.match(r"^\d{1,2}:\d{2}\s*(?:am|pm)\b", lowered):
            return True
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _clean_text(value: str) -> str:
        text = html.unescape(value or "")
        text = re.sub(r"<[^>]+>", " ", text)
        attr_group = "|".join(FetchService._HTML_ATTR_NAMES)
        text = re.sub(
            rf"\b(?:{attr_group}|data-[A-Za-z0-9_:-]+)\s*=\s*\"[^\"]*\"?",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"\b(?:{attr_group}|data-[A-Za-z0-9_:-]+)\s*=\s*'[^']*'?",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"\b(?:{attr_group}|data-[A-Za-z0-9_:-]+)\s*=\s*[^\s>]+",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"https?://\S+\.(?:png|jpe?g|webp|gif)\S*", " ", text, flags=re.IGNORECASE)
        # Strip dangling tag fragments left by context window slicing, e.g. a truncated "<img".
        text = re.sub(r"(?<!\w)</?[A-Za-z][A-Za-z0-9:-]*\b", " ", text)
        text = re.sub(r"(^|\s)[>＞]+(?=\s|$)", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def _extract_html_published(cls, html_text: str) -> str:
        patterns = [
            r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+property=["\']og:published_time["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+name=["\'](?:publishdate|pubdate|date|article:published_time)["\'][^>]+content=["\'](.*?)["\']',
            r'<time[^>]+datetime=["\'](.*?)["\']',
            r'"datePublished"\s*:\s*"([^"]+)"',
            r'"dateCreated"\s*:\s*"([^"]+)"',
            r'"dateModified"\s*:\s*"([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            normalized = cls._normalize_published_text(match.group(1))
            if normalized:
                return normalized
        # Fallback: scan visible text near the article header/body for date strings.
        visible = cls._clean_text(cls._match_first_block(html_text, html_text.lower(), "article") or cls._match_body(html_text, html_text.lower()) or html_text)
        for pattern in [
            r"\b(20\d{2}-\d{1,2}-\d{1,2})\b",
            r"\b(20\d{2}/\d{1,2}/\d{1,2})\b",
            r"\b(20\d{2}\.\d{1,2}\.\d{1,2})\b",
            r"(20\d{2}年\d{1,2}月\d{1,2}日)",
        ]:
            match = re.search(pattern, visible)
            if not match:
                continue
            normalized = cls._normalize_published_text(match.group(1))
            if normalized:
                return normalized
        return ""

    @classmethod
    def _extract_html_published_metadata(cls, html_text: str, *, url: str = "") -> dict[str, str]:
        header_visible_meta = cls._extract_visible_published_metadata(html_text, header_only=True)
        patterns = [
            ("meta_article_published_time", "high", r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\'](.*?)["\']'),
            ("meta_og_published_time", "high", r'<meta[^>]+property=["\']og:published_time["\'][^>]+content=["\'](.*?)["\']'),
            ("meta_publishdate", "medium", r'<meta[^>]+name=["\'](?:publishdate|pubdate|date|article:published_time)["\'][^>]+content=["\'](.*?)["\']'),
            ("time_datetime", "medium", r'<time[^>]+datetime=["\'](.*?)["\']'),
            ("serialized_article_title_date", "high", r'"type"\s*:\s*"ArticleTitle".{0,1200}?"date"\s*:\s*"([^"]+)"'),
            ("jsonld_datePublished", "high", r'"datePublished"\s*:\s*"([^"]+)"'),
            ("jsonld_dateCreated", "medium", r'"dateCreated"\s*:\s*"([^"]+)"'),
            ("jsonld_dateModified", "low", r'"dateModified"\s*:\s*"([^"]+)"'),
        ]
        for source, confidence, pattern in patterns:
            match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            normalized = cls._normalize_published_text(match.group(1))
            if normalized:
                if source.startswith("jsonld_") and cls._should_prefer_visible_date_over_jsonld(
                    jsonld_published=normalized,
                    visible_meta=header_visible_meta,
                ):
                    return header_visible_meta
                return {
                    "published": normalized,
                    "published_source": source,
                    "published_confidence": confidence,
                }

        if header_visible_meta.get("published"):
            return header_visible_meta

        inferred_from_url = cls._infer_date_from_url(url)
        if inferred_from_url:
            return {
                "published": inferred_from_url,
                "published_source": "url_date",
                "published_confidence": "medium",
            }

        visible_meta = cls._extract_visible_published_metadata(html_text, header_only=False)
        if visible_meta.get("published"):
            return visible_meta

        visible = cls._clean_text(
            cls._match_first_block(html_text, html_text.lower(), "article")
            or cls._match_body(html_text, html_text.lower())
            or html_text
        )
        for pattern in [
            r"\b(20\d{2}-\d{1,2}-\d{1,2})\b",
            r"\b(20\d{2}/\d{1,2}/\d{1,2})\b",
            r"\b(20\d{2}\.\d{1,2}\.\d{1,2})\b",
            r"(20\d{2}年\d{1,2}月\d{1,2}日)",
        ]:
            match = re.search(pattern, visible)
            if not match:
                continue
            normalized = cls._normalize_published_text(match.group(1))
            if normalized:
                return {
                    "published": normalized,
                    "published_source": "visible_text_date",
                    "published_confidence": "low",
                }
        return {
            "published": "",
            "published_source": "",
            "published_confidence": "low",
        }

    @classmethod
    def _extract_visible_published_metadata(cls, html_text: str, *, header_only: bool) -> dict[str, str]:
        fragment = (
            cls._match_first_block(html_text, html_text.lower(), "article")
            or cls._match_first_block(html_text, html_text.lower(), "main")
            or cls._match_body(html_text, html_text.lower())
            or html_text
        )
        visible = cls._clean_text(fragment)
        if header_only:
            visible = visible[:1200]
        for pattern in [
            r"\b(20\d{2}-\d{1,2}-\d{1,2})\b",
            r"\b(20\d{2}/\d{1,2}/\d{1,2})\b",
            r"\b(20\d{2}\.\d{1,2}\.\d{1,2})\b",
            r"(20\d{2}年\d{1,2}月\d{1,2}日)",
        ]:
            match = re.search(pattern, visible)
            if not match:
                continue
            normalized = cls._normalize_published_text(match.group(1))
            if normalized:
                return {
                    "published": normalized,
                    "published_source": "visible_header_date" if header_only else "visible_text_date",
                    "published_confidence": "medium" if header_only else "low",
                }
        return {
            "published": "",
            "published_source": "",
            "published_confidence": "low",
        }

    @classmethod
    def _should_prefer_visible_date_over_jsonld(cls, *, jsonld_published: str, visible_meta: dict[str, str]) -> bool:
        visible_published = str(visible_meta.get("published", "") or "").strip()
        if not visible_published:
            return False
        jsonld_dt = _coerce_utc_datetime(jsonld_published)
        visible_dt = _coerce_utc_datetime(visible_published)
        if jsonld_dt is None or visible_dt is None:
            return False
        delta_seconds = abs((jsonld_dt - visible_dt).total_seconds())
        if delta_seconds < 48 * 3600:
            return False
        now = datetime.now(timezone.utc)
        if jsonld_dt >= now - timedelta(days=2) and visible_dt <= now - timedelta(days=7):
            return True
        return visible_dt < jsonld_dt and delta_seconds >= 30 * 24 * 3600

    @staticmethod
    def _normalize_published_text(value: str) -> str:
        return _normalize_datetime_text(value)

    def _normalize_html_list_item(self, *, item: dict[str, Any], source: dict[str, Any]) -> dict[str, Any] | None:
        url = str(item.get("url", "") or "").strip()
        if not url:
            return None
        title = str(item.get("title", "") or "").strip()
        summary = str(item.get("summary", "") or "").strip()[:500]
        published = str(item.get("published", "") or "").strip()
        published_source = ""
        published_confidence = "low"
        needs_meta = self._looks_like_url_title(title, url) or not published or not summary
        if needs_meta:
            meta = self.extract_article_metadata(url)
            if self._looks_like_url_title(title, url):
                title = str(meta.get("title", "") or "").strip()
            if not published:
                published = str(meta.get("published", "") or "").strip()
                published_source = str(meta.get("published_source", "") or "").strip()
                published_confidence = str(meta.get("published_confidence", "low") or "low").strip().lower() or "low"
            if not summary:
                summary = str(meta.get("summary", "") or "").strip()[:500]
        if self._looks_like_url_title(title, url):
            return None
        if published and not published_source:
            published_source = "html_list_item"
            published_confidence = "medium"
        return {
            "title": title,
            "url": url,
            "summary": summary,
            "published": published,
            "published_source": published_source,
            "published_confidence": published_confidence,
            "published_status": "fresh" if published else "unknown",
            "source": str(source.get("name", "") or ""),
            "source_weight": float(source.get("weight", 0.7) or 0.7),
            "type": "html_list",
            **self._source_meta(source),
        }

    @staticmethod
    def _looks_like_url_title(title: str, url: str) -> bool:
        raw_title = str(title or "").strip()
        raw_url = str(url or "").strip()
        if not raw_title:
            return True
        lowered = raw_title.lower()
        if lowered.startswith("http://") or lowered.startswith("https://"):
            return True
        return raw_title == raw_url

    @staticmethod
    def _build_article_structure(html_text: str, *, title: str, max_chars: int = 12000) -> dict[str, Any]:
        fragment = (
            FetchService._match_first_block(html_text, html_text.lower(), "article")
            or FetchService._match_first_block(html_text, html_text.lower(), "main")
            or FetchService._match_body(html_text, html_text.lower())
            or html_text
        )
        sanitized = re.sub(r"<!--.*?-->", " ", fragment, flags=re.DOTALL)
        sanitized = re.sub(
            r"<(script|style|svg|noscript|iframe|form|button|nav|footer|header|aside)[^>]*>.*?</\1>",
            " ",
            sanitized,
            flags=re.IGNORECASE | re.DOTALL,
        )

        code_blocks: list[dict[str, Any]] = []
        code_placeholders: dict[str, str] = {}

        def stash_code(match: re.Match[str]) -> str:
            idx = len(code_blocks)
            attrs = match.group(1) or ""
            inner = match.group(2) or ""
            language_match = re.search(r"language-([a-z0-9_+-]+)", attrs, flags=re.IGNORECASE)
            text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
            language = (language_match.group(1).lower() if language_match else "")
            code_blocks.append(
                {
                    "language": language,
                    "code_excerpt": text[:1200],
                    "code_text": text[:12000],
                    "line_count": len([line for line in text.splitlines() if line.strip()]),
                    "kind": FetchService._classify_code_block(text=text, language=language),
                }
            )
            token = f"__CODE_BLOCK_{idx}__"
            code_placeholders[token] = text[:1200]
            return f"\n{token}\n"

        sanitized = re.sub(
            r"<pre([^>]*)>(.*?)</pre>",
            stash_code,
            sanitized,
            flags=re.IGNORECASE | re.DOTALL,
        )

        heading_pattern = re.compile(r"<(h[1-4])[^>]*>(.*?)</\1>", flags=re.IGNORECASE | re.DOTALL)
        paragraph_pattern = re.compile(r"<p[^>]*>(.*?)</p>", flags=re.IGNORECASE | re.DOTALL)
        list_pattern = re.compile(r"<(ul|ol)[^>]*>(.*?)</\1>", flags=re.IGNORECASE | re.DOTALL)
        li_pattern = re.compile(r"<li[^>]*>(.*?)</li>", flags=re.IGNORECASE | re.DOTALL)
        table_pattern = re.compile(r"<table[^>]*>(.*?)</table>", flags=re.IGNORECASE | re.DOTALL)
        tr_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", flags=re.IGNORECASE | re.DOTALL)
        cell_pattern = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", flags=re.IGNORECASE | re.DOTALL)

        sections: list[dict[str, Any]] = []
        current_section: dict[str, Any] | None = None
        lead_parts: list[str] = []
        lists: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        coverage_checklist: list[str] = []
        consumed_chars = 0

        token_pattern = re.compile(
            r"(<h[1-4][^>]*>.*?</h[1-4]>|<p[^>]*>.*?</p>|<(?:ul|ol)[^>]*>.*?</(?:ul|ol)>|<table[^>]*>.*?</table>|__CODE_BLOCK_\d+__)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        for token in token_pattern.findall(sanitized):
            code_match = re.fullmatch(r"__CODE_BLOCK_(\d+)__", token.strip())
            if code_match:
                if current_section is not None:
                    code_idx = int(code_match.group(1))
                    if code_idx not in current_section["code_refs"]:
                        current_section["code_refs"].append(code_idx)
                continue

            heading_match = heading_pattern.match(token)
            if heading_match:
                level = int(heading_match.group(1)[1])
                heading_text = FetchService._clean_text(re.sub(r"<[^>]+>", " ", heading_match.group(2)))
                if not heading_text:
                    continue
                if FetchService._looks_like_editorial_noise(heading_text):
                    continue
                if title and FetchService._clean_text(heading_text) == FetchService._clean_text(title):
                    continue
                current_section = {"heading": heading_text, "level": level, "paragraphs": [], "code_refs": [], "list_refs": [], "table_refs": []}
                sections.append(current_section)
                if heading_text not in coverage_checklist:
                    coverage_checklist.append(heading_text)
                consumed_chars += len(heading_text)
                if consumed_chars >= max_chars:
                    break
                continue

            paragraph_match = paragraph_pattern.match(token)
            if paragraph_match:
                text = re.sub(r"<[^>]+>", " ", paragraph_match.group(1))
                for placeholder, code_text in code_placeholders.items():
                    text = text.replace(placeholder, code_text)
                cleaned = FetchService._clean_text(text)
                if not cleaned:
                    continue
                if FetchService._looks_like_editorial_noise(cleaned):
                    continue
                if current_section is None:
                    lead_parts.append(cleaned)
                else:
                    current_section["paragraphs"].append(cleaned)
                    for idx, code in enumerate(code_blocks):
                        excerpt = str(code.get("code_excerpt", "") or "")
                        if excerpt and excerpt[:80] in cleaned and idx not in current_section["code_refs"]:
                            current_section["code_refs"].append(idx)
                consumed_chars += len(cleaned)
                if consumed_chars >= max_chars:
                    break
                continue

            list_match = list_pattern.match(token)
            if list_match:
                items = [
                    FetchService._clean_text(re.sub(r"<[^>]+>", " ", match))
                    for match in li_pattern.findall(list_match.group(2))
                ]
                items = [item for item in items if item]
                if items:
                    lists.append({"type": list_match.group(1).lower(), "items": items[:8]})
                    if current_section is not None:
                        current_section["list_refs"].append(len(lists) - 1)
                consumed_chars += sum(len(item) for item in items[:4])
                if consumed_chars >= max_chars:
                    break
                continue

            table_match = table_pattern.match(token)
            if table_match:
                rows = []
                for tr in tr_pattern.findall(table_match.group(1)):
                    cells = [FetchService._clean_text(re.sub(r"<[^>]+>", " ", cell)) for cell in cell_pattern.findall(tr)]
                    cells = [cell for cell in cells if cell]
                    if cells:
                        rows.append(cells[:6])
                if rows:
                    tables.append({"rows": rows[:6]})
                    if current_section is not None:
                        current_section["table_refs"].append(len(tables) - 1)
                consumed_chars += sum(len(cell) for row in rows[:2] for cell in row)
                if consumed_chars >= max_chars:
                    break

        lead = "\n\n".join(lead_parts[:2]).strip()
        normalized_sections: list[dict[str, Any]] = []
        for section in sections[:12]:
            paragraphs = list(section.get("paragraphs") or [])
            normalized_sections.append(
                {
                    "heading": section.get("heading", ""),
                    "level": section.get("level", 2),
                    "summary": " ".join(paragraphs[:2])[:600],
                    "paragraphs": paragraphs[:4],
                    "code_refs": list(section.get("code_refs") or [])[:3],
                    "list_refs": list(section.get("list_refs") or [])[:2],
                    "table_refs": list(section.get("table_refs") or [])[:2],
                }
            )

        return {
            "status": "ok",
            "reason": "",
            "title": title,
            "lead": lead,
            "sections": normalized_sections,
            "code_blocks": code_blocks[:10],
            "lists": lists[:10],
            "tables": tables[:4],
            "coverage_checklist": coverage_checklist[:12],
        }

    @staticmethod
    def _classify_code_block(*, text: str, language: str) -> str:
        lowered_language = str(language or "").strip().lower()
        if lowered_language in {"bash", "shell", "sh", "zsh", "powershell", "ps1", "cmd", "console", "terminal"}:
            return "command"
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        if not lines:
            return "code"
        command_like = 0
        for line in lines[:8]:
            if line.startswith(("$ ", "# ", "PS>", "sudo ", "curl ", "ollama ", "pip ", "python ", "npm ", "uv ", "git ")):
                command_like += 1
        return "command" if command_like >= max(1, min(3, len(lines))) else "code"
