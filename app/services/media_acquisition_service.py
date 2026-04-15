from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.core.config import CONFIG
from app.services.image_utils import detect_image_mime, image_suffix_for_mime
from app.services.visual_asset_schema import build_visual_asset


class MediaAcquisitionService:
    REMOTE_IMAGE_TIMEOUT_SECONDS = 30
    REMOTE_IMAGE_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    def __init__(self, *, proxy: str = "") -> None:
        self.proxy = str(proxy or "").strip()

    def acquire(self, *, run_id: str, visual_blueprint: dict[str, Any]) -> list[dict[str, Any]]:
        output_root = CONFIG.data_dir / "runs" / run_id / "visual-assets" / "crawled"
        output_root.mkdir(parents=True, exist_ok=True)
        assets: list[dict[str, Any]] = []
        for item in list(visual_blueprint.get("items") or []):
            if not isinstance(item, dict) or str(item.get("mode", "") or "").strip() != "crawl":
                continue
            constraints = dict(item.get("constraints") or {})
            urls = [str(url).strip() for url in (constraints.get("candidate_image_urls") or []) if str(url).strip()]
            metadata_by_url = {
                str(entry.get("url", "") or "").strip(): dict(entry)
                for entry in (constraints.get("candidate_metadata") or [])
                if isinstance(entry, dict) and str(entry.get("url", "") or "").strip()
            }
            asset_payload = {
                "status": "failed",
                "path": "",
                "remote_url": "",
                "source_page": "",
                "origin_type": "",
                "query_source": "",
                "source_role": "",
                "page_host": "",
                "is_official_host": False,
                "image_kind": "",
                "provenance_score": 0,
                "relevance_features": {},
                "errors": [],
            }
            asset = build_visual_asset(item=item, mode="crawl", payload=asset_payload)
            for idx, image_url in enumerate(urls, start=1):
                try:
                    cached_path = self._cache_remote_image(
                        image_url=image_url,
                        output_root=output_root,
                        placement_key=asset["placement_key"],
                        index=idx,
                    )
                except Exception as exc:
                    asset["errors"].append(f"{image_url}: {exc}")
                    continue
                metadata = metadata_by_url.get(image_url, {})
                asset["status"] = "acquired"
                asset["path"] = str(cached_path).replace("\\", "/")
                asset["remote_url"] = image_url
                asset["source_page"] = str(metadata.get("source_page", "") or "").strip()
                asset["origin_type"] = str(metadata.get("origin_type", "") or "").strip()
                asset["query_source"] = str(metadata.get("query_source", "") or "").strip()
                asset["source_role"] = str(metadata.get("source_role", "") or "").strip()
                asset["page_host"] = str(metadata.get("page_host", "") or "").strip()
                asset["is_official_host"] = bool(metadata.get("is_official_host", False))
                asset["image_kind"] = str(metadata.get("image_kind", "") or "").strip()
                asset["provenance_score"] = int(metadata.get("provenance_score", 0) or 0)
                asset["relevance_features"] = dict(metadata.get("relevance_features") or {})
                break
            assets.append(asset)
        return assets

    def _cache_remote_image(self, *, image_url: str, output_root: Path, placement_key: str, index: int) -> Path:
        parsed = urlparse(str(image_url or "").strip())
        headers = dict(self.REMOTE_IMAGE_HEADERS)
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        response = requests.get(
            image_url,
            headers=headers,
            timeout=self.REMOTE_IMAGE_TIMEOUT_SECONDS,
            proxies=self._request_proxies(),
        )
        response.raise_for_status()
        payload = bytes(response.content or b"")
        if not payload:
            raise RuntimeError("remote image response is empty")
        header_mime_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if header_mime_type and not header_mime_type.startswith("image/"):
            raise RuntimeError(f"remote image content-type is not image: {header_mime_type}")
        mime_type = detect_image_mime(payload, fallback=header_mime_type or "image/png")
        suffix = self._resolve_remote_image_suffix(image_url=image_url, mime_type=mime_type)
        safe_key = placement_key or f"image-{index}"
        output_path = output_root / f"{safe_key}-{index}{suffix}"
        output_path.write_bytes(payload)
        return output_path

    def _request_proxies(self) -> dict[str, str] | None:
        if not self.proxy:
            return None
        return {"http": self.proxy, "https": self.proxy}

    @staticmethod
    def _resolve_remote_image_suffix(*, image_url: str, mime_type: str) -> str:
        if mime_type.startswith("image/"):
            return image_suffix_for_mime(mime_type)
        path_suffix = Path(urlparse(str(image_url or "").strip()).path).suffix.lower()
        if path_suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
            return path_suffix
        guessed = mimetypes.guess_extension(mime_type or "")
        if guessed in {".jpe", ".jpeg"}:
            return ".jpg"
        if guessed in {".png", ".jpg", ".gif", ".webp", ".bmp"}:
            return guessed
        return ".png"
