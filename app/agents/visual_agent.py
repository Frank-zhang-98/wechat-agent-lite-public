from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from app.agents.base import AgentContext
from app.core.config import CONFIG
from app.runtime.state_models import VisualAssetSet, VisualBlueprint
from app.services.visual_asset_schema import build_visual_asset


_COVER_SCORE_KEYS = (
    "subject",
    "composition",
    "style",
    "lighting",
    "copy_hierarchy",
)


class VisualAgent:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    def generate(
        self,
        *,
        run: Any,
        article_title: str,
        visual_blueprint: VisualBlueprint,
        include_cover_assets: bool,
        size: str,
    ) -> tuple[VisualAssetSet, dict[str, Any]]:
        output_root = CONFIG.data_dir / "runs" / run.id / "visual-assets" / "generated"
        output_root.mkdir(parents=True, exist_ok=True)
        body_assets: list[dict[str, Any]] = []
        for item in list(visual_blueprint.items or []):
            if str(item.get("mode", "") or "").strip() != "generate":
                continue
            brief = dict(item.get("brief") or {})
            output_path = output_root / f"{str(item.get('placement_key', '') or 'visual')}.png"
            generated = self.ctx.support.visual_renderer.render_body_illustration(
                article_title=article_title,
                brief=brief,
                output_path=output_path,
                size=size,
            )
            body_assets.append(build_visual_asset(item=item, mode="generate", payload=dict(generated or {})))

        cover_5d = self._build_cover_5d(run=run, article_title=article_title)
        cover_asset = self._build_cover_asset(
            run=run,
            article_title=article_title,
            visual_blueprint=visual_blueprint,
            cover_5d=cover_5d,
            include_cover_assets=include_cover_assets,
        )
        assets = VisualAssetSet(body_assets=body_assets, cover_5d=cover_5d, cover_asset=cover_asset)
        return assets, {
            "outputs": [
                {
                    "title": "runtime_visual_blueprint",
                    "text": json.dumps(visual_blueprint.as_dict(), ensure_ascii=False, indent=2),
                    "language": "json",
                },
                {
                    "title": "runtime_generated_visual_assets",
                    "text": json.dumps(assets.as_dict(), ensure_ascii=False, indent=2),
                    "language": "json",
                },
            ]
        }

    def _build_cover_5d(self, *, run: Any, article_title: str) -> dict[str, Any]:
        support = self.ctx.support
        prompt = (
            "Generate cover scores as JSON with keys: "
            "subject, composition, style, lighting, copy_hierarchy. "
            "Each score must be between 0 and 100.\n"
            f"Article title: {article_title}"
        )
        text = support.llm.call(run.id, "COVER_5D", "cover_prompt", prompt, temperature=0.3).text
        dims = self._parse_cover_dims(text)
        if not dims:
            dims = {
                "subject": round(random.uniform(75, 92), 2),
                "composition": round(random.uniform(72, 90), 2),
                "style": round(random.uniform(74, 91), 2),
                "lighting": round(random.uniform(70, 89), 2),
                "copy_hierarchy": round(random.uniform(71, 88), 2),
            }
        dims["total_score"] = round(
            0.30 * dims["subject"]
            + 0.20 * dims["composition"]
            + 0.20 * dims["style"]
            + 0.15 * dims["lighting"]
            + 0.15 * dims["copy_hierarchy"],
            2,
        )
        return dims

    def _build_cover_asset(
        self,
        *,
        run: Any,
        article_title: str,
        visual_blueprint: VisualBlueprint,
        cover_5d: dict[str, Any],
        include_cover_assets: bool,
    ) -> dict[str, Any]:
        if not include_cover_assets:
            return {}
        support = self.ctx.support
        output_dir = CONFIG.data_dir / "runs" / run.id
        output_dir.mkdir(parents=True, exist_ok=True)
        cover_size = support.settings.get("visual.cover_size", "1280*720")
        strategy = {
            "cover_family": visual_blueprint.cover_family,
            "cover_brief": dict(visual_blueprint.cover_brief or {}),
        }
        cover_brief = dict(visual_blueprint.cover_brief or {})
        prompt_request = support.visual_strategy.build_cover_prompt_request(
            article_title=article_title,
            strategy=strategy,
            cover_5d=cover_5d,
        )
        prompt_result = support.llm.call(run.id, "COVER_GEN", "cover_prompt", prompt_request, temperature=0.35)
        image_prompt = prompt_result.text.strip() or self._fallback_cover_prompt(article_title, cover_5d)
        try:
            raw_asset = support.llm.generate_cover_image(
                run.id,
                "COVER_GEN",
                "cover_image",
                prompt=image_prompt,
                output_dir=output_dir / "cover-image",
                size=cover_size,
            )
        except Exception as exc:
            raw_asset = {"status": "generation_failed", "error": str(exc), "size": cover_size.replace("*", "x")}
        raw_path = str(raw_asset.get("path", "") or "").strip()
        if raw_asset.get("status") == "generated" and raw_path:
            try:
                overlaid = support.visual_renderer.overlay_cover_title(
                    base_image_path=Path(raw_path),
                    article_title=article_title,
                    output_path=output_dir / "cover-final.png",
                    size=cover_size,
                    title_safe_zone=str(cover_brief.get("title_safe_zone", "left_bottom") or "left_bottom"),
                )
                return {
                    **raw_asset,
                    **overlaid,
                    "base_image_path": raw_path,
                    "image_prompt": image_prompt[:2000],
                    "generator": "native_image_with_title_overlay",
                }
            except Exception as exc:
                return {
                    **raw_asset,
                    "image_prompt": image_prompt[:2000],
                    "generator": "native_image_raw",
                    "overlay_error": str(exc),
                }
        fallback_path = output_dir / "cover-programmatic.png"
        fallback_asset = support.visual_renderer.render_cover(
            article_title=article_title,
            strategy=strategy,
            cover_5d=cover_5d,
            output_path=fallback_path,
            size=cover_size,
        )
        return {
            **fallback_asset,
            "fallback_reason": raw_asset.get("status") or "unknown",
            "image_prompt": image_prompt[:2000],
            "generator": "programmatic_fallback",
        }

    @staticmethod
    def _parse_cover_dims(text: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for key in _COVER_SCORE_KEYS:
            match = re.search(rf"{re.escape(key)}\s*[:：]\s*(\d{{1,3}}(?:\.\d+)?)", str(text or ""), flags=re.IGNORECASE)
            if not match:
                continue
            value = float(match.group(1))
            if 0 <= value <= 100:
                out[key] = round(value, 2)
        return out if len(out) == len(_COVER_SCORE_KEYS) else {}

    @staticmethod
    def _fallback_cover_prompt(title: str, cover_5d: dict[str, Any]) -> str:
        total = cover_5d.get("total_score", "-")
        return (
            f"Wide technical cover image for an article titled '{title}'. "
            f"Clean composition, strong focal subject, layered lighting, clear negative space for title overlay, "
            f"no readable text or watermark, target visual score {total}."
        )
