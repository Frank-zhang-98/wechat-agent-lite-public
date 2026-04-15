from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import CONFIG
from app.services.visual_asset_schema import build_visual_asset


class PageCaptureService:
    DEFAULT_VIEWPORT = {"width": 1440, "height": 1024}
    DEFAULT_TIMEOUT_MS = 30000

    def capture(self, *, run_id: str, visual_blueprint: dict[str, Any]) -> list[dict[str, Any]]:
        output_root = CONFIG.data_dir / "runs" / run_id / "visual-assets" / "captured"
        output_root.mkdir(parents=True, exist_ok=True)
        assets: list[dict[str, Any]] = []
        for item in list(visual_blueprint.get("items") or []):
            if not isinstance(item, dict) or str(item.get("mode", "") or "").strip() != "capture":
                continue
            constraints = dict(item.get("constraints") or {})
            targets = [dict(entry) for entry in (constraints.get("capture_targets") or []) if isinstance(entry, dict)]
            asset = build_visual_asset(
                item=item,
                mode="capture",
                payload={
                    "status": "failed",
                    "path": "",
                    "source_page": "",
                    "origin_type": "",
                    "query_source": "",
                    "source_role": "",
                    "page_host": "",
                    "is_official_host": False,
                    "errors": [],
                },
            )
            for index, target in enumerate(targets, start=1):
                url = str(target.get("url", "") or "").strip()
                if not url:
                    continue
                output_path = output_root / f"{asset['placement_key'] or 'capture'}-{index}.png"
                try:
                    metadata = self._capture_url(
                        url=url,
                        output_path=output_path,
                        viewport=dict(target.get("viewport") or {}),
                        timeout_ms=int(target.get("timeout_ms", 0) or self.DEFAULT_TIMEOUT_MS),
                    )
                except Exception as exc:
                    asset["errors"].append(f"{url}: {exc}")
                    continue
                asset.update(
                    {
                        "status": "captured",
                        "path": str(output_path).replace("\\", "/"),
                        "source_page": url,
                        "origin_type": str(target.get("origin_type", "") or "").strip(),
                        "query_source": str(target.get("query_source", "") or "").strip(),
                        "source_role": str(target.get("source_role", "") or "").strip(),
                        "page_host": str(target.get("page_host", "") or "").strip(),
                        "is_official_host": bool(target.get("is_official_host", False)),
                        "title": str(target.get("title", "") or metadata.get("title", "") or asset.get("title", "")).strip(),
                        "caption": str(target.get("caption", "") or asset.get("caption", "")).strip(),
                    }
                )
                break
            assets.append(asset)
        return assets

    def _capture_url(
        self,
        *,
        url: str,
        output_path: Path,
        viewport: dict[str, Any] | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(f"playwright_unavailable: {exc}") from exc

        resolved_viewport = dict(self.DEFAULT_VIEWPORT)
        if viewport:
            resolved_viewport.update(
                {
                    "width": int(viewport.get("width", resolved_viewport["width"]) or resolved_viewport["width"]),
                    "height": int(viewport.get("height", resolved_viewport["height"]) or resolved_viewport["height"]),
                }
            )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    ignore_https_errors=True,
                    viewport=resolved_viewport,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
                    ),
                )
                try:
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=max(5000, int(timeout_ms)))
                    try:
                        page.wait_for_load_state("networkidle", timeout=min(max(3000, int(timeout_ms)), 8000))
                    except Exception:
                        pass
                    page.wait_for_timeout(1500)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(output_path), full_page=False)
                    return {"title": str(page.title() or "").strip()}
                finally:
                    context.close()
            finally:
                browser.close()
