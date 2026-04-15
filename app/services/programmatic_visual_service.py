from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path
import re
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.services.localization_service import LocalizationService


def parse_canvas_size(size: str, fallback: tuple[int, int]) -> tuple[int, int]:
    raw = str(size or "").strip().lower().replace("x", "*")
    try:
        width_text, height_text = raw.split("*", 1)
        return max(320, int(width_text)), max(320, int(height_text))
    except Exception:
        return fallback


class ProgrammaticVisualService:
    def render_cover(
        self,
        *,
        article_title: str,
        strategy: dict[str, Any],
        cover_5d: dict[str, Any],
        output_path: Path,
        size: str,
    ) -> dict[str, Any]:
        width, height = parse_canvas_size(size, (1280, 720))
        family = str(strategy.get("cover_family", "structure") or "structure").strip().lower()
        brief = dict(strategy.get("cover_brief") or {})
        palette = self._palette_for_family(family)
        image = Image.new("RGBA", (width, height), palette["background"] + (255,))
        self._draw_cover_background(image=image, width=width, height=height, palette=palette, family=family)
        draw = ImageDraw.Draw(image)

        localized_title = LocalizationService.localize_visual_text(article_title)
        title_size = max(46, int(height * (0.082 if len(localized_title) >= 24 else 0.10)))
        title_font = self._font(title_size, bold=True)
        subtitle_font = self._font(max(22, int(height * 0.04)), bold=False)
        eyebrow_font = self._font(max(15, int(height * 0.023)), bold=True)
        small_font = self._font(max(18, int(height * 0.027)), bold=False)

        chips = LocalizationService.localize_visual_items((brief.get("must_show") or []))[:4]

        left_x = int(width * 0.07)
        left_w = int(width * 0.44)
        y = int(height * 0.08)

        eyebrow_text = self._cover_family_label(family)
        eyebrow_h = max(32, int(height * 0.06))
        eyebrow_w = int(draw.textlength(eyebrow_text, font=eyebrow_font)) + 34
        self._draw_pill(
            image=image,
            box=(left_x, y, left_x + eyebrow_w, y + eyebrow_h),
            radius=eyebrow_h // 2,
            fill=palette["eyebrow_bg"],
            outline=palette["eyebrow_outline"],
            shadow=(10, 18, 36, 42),
        )
        draw = ImageDraw.Draw(image)
        draw.text((left_x + 18, y + max(7, eyebrow_h // 5)), eyebrow_text, fill=palette["eyebrow_text"], font=eyebrow_font)
        y += eyebrow_h + int(height * 0.045)

        title_font, title_lines = self._fit_text_lines(
            draw=draw,
            text=localized_title,
            font=title_font,
            max_width=left_w,
            max_lines=4,
            max_height=int(height * 0.34),
            min_size=30,
        )
        for line in title_lines:
            draw.text((left_x, y), line, fill=palette["title"], font=title_font)
            y += title_font.size + int(height * 0.012)

        self._draw_cover_visual(
            image=image,
            family=family,
            palette=palette,
            box=(int(width * 0.56), int(height * 0.09), width - int(width * 0.05), height - int(height * 0.10)),
            small_font=small_font,
            subtitle_font=subtitle_font,
            chips=chips,
            main_claim="",
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(output_path, format="PNG")
        return {"path": str(output_path), "size": f"{width}x{height}", "status": "generated", "family": family}

    def overlay_cover_title(
        self,
        *,
        base_image_path: Path,
        article_title: str,
        output_path: Path,
        size: str,
        title_safe_zone: str = "left_bottom",
    ) -> dict[str, Any]:
        width, height = parse_canvas_size(size, (1280, 720))
        with Image.open(base_image_path) as source:
            image = ImageOps.fit(source.convert("RGBA"), (width, height), method=Image.Resampling.LANCZOS)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Bottom gradient ensures the title remains readable on busy themed images.
        gradient_height = int(height * 0.42)
        for step in range(gradient_height):
            alpha = int(220 * (step / max(gradient_height - 1, 1)) ** 1.6)
            y = height - gradient_height + step
            draw.line((0, y, width, y), fill=(6, 11, 18, alpha))

        title = LocalizationService.localize_visual_text(article_title)
        title_font = self._font(max(40, int(height * (0.074 if len(title) >= 26 else 0.086))), bold=True)
        subtitle_font = self._font(max(16, int(height * 0.025)), bold=False)
        max_width = int(width * 0.58)
        title_font, title_lines = self._fit_text_lines(
            draw=draw,
            text=title,
            font=title_font,
            max_width=max_width,
            max_lines=4,
            max_height=int(height * 0.36),
            min_size=26,
        )
        panel_h = 36 + len(title_lines) * (title_font.size + 8) + 22
        zone = self._normalize_title_safe_zone(title_safe_zone)
        panel_box = self._cover_title_panel_box(width=width, height=height, max_width=max_width, panel_h=panel_h, zone=zone)

        draw.rounded_rectangle(panel_box, radius=28, fill=(8, 15, 25, 224), outline=(122, 171, 245, 156), width=2)
        eyebrow = "AI 技术解读"
        eyebrow_w = int(draw.textlength(eyebrow, font=subtitle_font)) + 22
        eyebrow_box = (panel_box[0] + 18, panel_box[1] - 18, panel_box[0] + 18 + eyebrow_w, panel_box[1] + 16)
        draw.rounded_rectangle(eyebrow_box, radius=17, fill=(20, 58, 120, 232), outline=(145, 195, 255, 176), width=1)
        draw.text((eyebrow_box[0] + 11, eyebrow_box[1] + 8), eyebrow, fill=(236, 245, 255, 255), font=subtitle_font)

        y = panel_box[1] + 20
        x = panel_box[0] + 18
        for line in title_lines:
            draw.text((x, y + 2), line, fill=(5, 11, 20, 180), font=title_font)
            draw.text(
                (x, y),
                line,
                fill=(246, 249, 252, 255),
                font=title_font,
                stroke_width=2,
                stroke_fill=(5, 11, 20, 220),
            )
            y += title_font.size + 8

        image.alpha_composite(overlay)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(output_path, format="PNG")
        return {
            "path": str(output_path),
            "size": f"{width}x{height}",
            "status": "generated",
            "source_path": str(base_image_path),
            "overlay_mode": "title_overlay",
            "title_safe_zone": zone,
        }

    def render_body_illustration(
        self,
        *,
        article_title: str,
        brief: dict[str, Any],
        output_path: Path,
        size: str,
    ) -> dict[str, Any]:
        width, height = parse_canvas_size(size, (1024, 1024))
        diagram_type = str(brief.get("type", "architecture_diagram") or "architecture_diagram").strip().lower()
        palette = self._palette_for_diagram(diagram_type)
        image = Image.new("RGBA", (width, height), palette["background"] + (255,))
        draw = ImageDraw.Draw(image)
        self._draw_gradient(draw, width, height, palette["background"], palette["background_alt"])
        self._draw_body_background(image=image, width=width, height=height, palette=palette, diagram_type=diagram_type)

        title_font = self._font(max(40, int(height * 0.040)), bold=True)
        subtitle_font = self._font(max(22, int(height * 0.023)), bold=False)
        node_font = self._font(max(22, int(height * 0.022)), bold=True)
        body_font = self._font(max(18, int(height * 0.019)), bold=False)
        meta_font = self._font(max(16, int(height * 0.016)), bold=False)
        eyebrow_font = self._font(max(15, int(height * 0.015)), bold=True)

        raw_title = str(brief.get("title", "") or article_title or "").strip()
        raw_caption = str(brief.get("caption", "") or "").strip()
        raw_must_show = [str(item).strip() for item in (brief.get("must_show") or []) if str(item).strip()]
        title = self._sanitize_visual_text(
            LocalizationService.localize_visual_text(raw_title),
            fallback=self._sanitize_visual_text(raw_title, fallback=str(article_title or "").strip()),
        )
        caption = self._sanitize_visual_text(
            LocalizationService.localize_visual_text(raw_caption),
            fallback=self._sanitize_visual_text(raw_caption, fallback=""),
        )
        must_show = [
            item
            for item in (
                self._sanitize_visual_text(
                    LocalizationService.localize_visual_text(text),
                    fallback=self._sanitize_visual_text(text, fallback=""),
                )
                for text in raw_must_show
            )
            if item
        ][:6]
        detail_items = self._body_detail_items(title=title, caption=caption, must_show=must_show, limit=8)

        y = 42
        eyebrow = self._body_family_label(diagram_type)
        eyebrow_h = 34
        eyebrow_w = int(draw.textlength(eyebrow, font=eyebrow_font)) + 28
        self._draw_pill(
            image=image,
            box=(48, y, 48 + eyebrow_w, y + eyebrow_h),
            radius=17,
            fill=palette["eyebrow_bg"],
            outline=palette["eyebrow_outline"],
            shadow=(8, 16, 28, 28),
        )
        draw = ImageDraw.Draw(image)
        draw.text((62, y + 8), eyebrow, fill=palette["eyebrow_text"], font=eyebrow_font)
        y += eyebrow_h + 16

        title_font, title_lines = self._fit_text_lines(
            draw=draw,
            text=title,
            font=title_font,
            max_width=width - 96,
            max_lines=3,
            max_height=int(height * 0.16),
            min_size=24,
        )
        for line in title_lines:
            draw.text((48, y), line, fill=palette["title"], font=title_font)
            y += title_font.size + 8
        if caption:
            subtitle_font, caption_lines = self._fit_text_lines(
                draw=draw,
                text=caption,
                font=subtitle_font,
                max_width=width - 96,
                max_lines=4,
                max_height=int(height * 0.14),
                min_size=15,
            )
            for line in caption_lines:
                draw.text((50, y + 2), line, fill=palette["text"], font=subtitle_font)
                y += subtitle_font.size + 4

        if detail_items:
            chip_x = 48
            chip_y = y + 18
            chip_h = 34
            max_x = width - 48
            for chip in detail_items[:4]:
                chip_w = int(draw.textlength(chip, font=meta_font)) + 26
                if chip_x + chip_w > max_x:
                    chip_x = 48
                    chip_y += chip_h + 10
                self._draw_pill(
                    image=image,
                    box=(chip_x, chip_y, chip_x + chip_w, chip_y + chip_h),
                    radius=17,
                    fill=palette["chip_bg"],
                    outline=palette["chip_outline"],
                    shadow=(6, 12, 22, 18),
                )
                draw = ImageDraw.Draw(image)
                draw.text((chip_x + 13, chip_y + 8), chip, fill=palette["chip_text"], font=meta_font)
                chip_x += chip_w + 10
            y = chip_y + chip_h

        if diagram_type in {"comparison_infographic", "system_layers_infographic", "process_explainer_infographic"}:
            insight_box = (48, y + 16, width - 48, y + 92)
            insight_text = " / ".join(self._dedupe_phrases(detail_items[:5], limit=4)) or caption or title
            self._draw_summary_callout(
                image=image,
                box=insight_box,
                title="图解重点",
                body=insight_text,
                palette=palette,
                title_font=meta_font,
                body_font=self._font(max(14, meta_font.size - 1), bold=False),
            )
            y = insight_box[3]

        content_box = (44, max(226, y + 26), width - 44, height - 44)
        if diagram_type == "workflow_diagram":
            self._draw_workflow(image=image, items=must_show, details=detail_items, box=content_box, palette=palette, node_font=node_font, body_font=body_font)
        elif diagram_type == "comparison_card":
            self._draw_comparison(image=image, items=must_show, details=detail_items, box=content_box, palette=palette, node_font=node_font, body_font=body_font)
        elif diagram_type == "comparison_infographic":
            self._draw_infographic_comparison(
                image=image,
                title=title,
                items=must_show,
                details=detail_items,
                box=content_box,
                palette=palette,
                node_font=node_font,
                body_font=body_font,
                meta_font=meta_font,
            )
        elif diagram_type == "system_layers_infographic":
            self._draw_infographic_system_layers(
                image=image,
                title=title,
                items=must_show,
                details=detail_items,
                box=content_box,
                palette=palette,
                node_font=node_font,
                body_font=body_font,
                meta_font=meta_font,
            )
        elif diagram_type == "process_explainer_infographic":
            self._draw_infographic_process(
                image=image,
                title=title,
                items=must_show,
                details=detail_items,
                box=content_box,
                palette=palette,
                node_font=node_font,
                body_font=body_font,
                meta_font=meta_font,
            )
        else:
            self._draw_architecture(image=image, items=must_show, details=detail_items, box=content_box, palette=palette, node_font=node_font, body_font=body_font)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(output_path, format="PNG")
        return {
            "path": str(output_path),
            "size": f"{width}x{height}",
            "status": "generated",
            "diagram_type": diagram_type,
        }

    def _draw_cover_visual(
        self,
        *,
        image: Image.Image,
        family: str,
        palette: dict[str, tuple[int, int, int] | str],
        box: tuple[int, int, int, int],
        small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        subtitle_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        chips: list[str],
        main_claim: str,
    ) -> None:
        self._draw_shadowed_card(
            image=image,
            box=box,
            radius=34,
            fill=palette["stage"],
            outline=palette["stage_outline"],
            shadow=(10, 30, 60, 56),
        )
        self._draw_glow(
            image=image,
            center=(int(box[0] + (box[2] - box[0]) * 0.72), int(box[1] + (box[3] - box[1]) * 0.34)),
            radius=int(min(box[2] - box[0], box[3] - box[1]) * 0.28),
            color=palette["glow"],
            alpha=82,
        )
        if family == "comparison":
            self._draw_cover_comparison(image=image, box=box, palette=palette, subtitle_font=subtitle_font, body_font=small_font, chips=chips)
        elif family == "command":
            self._draw_cover_command(
                image=image,
                box=box,
                palette=palette,
                title_font=subtitle_font,
                body_font=small_font,
                chips=chips,
                main_claim=main_claim,
            )
        elif family == "thesis":
            self._draw_cover_thesis(image=image, box=box, palette=palette, title_font=subtitle_font, body_font=small_font, chips=chips)
        else:
            self._draw_cover_structure(image=image, box=box, palette=palette, title_font=subtitle_font, body_font=small_font, chips=chips)

    def _draw_cover_background(
        self,
        *,
        image: Image.Image,
        width: int,
        height: int,
        palette: dict[str, tuple[int, int, int]],
        family: str,
    ) -> None:
        base = ImageDraw.Draw(image)
        self._draw_gradient(base, width, height, palette["background"], palette["background_alt"])
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.polygon(
            [
                (int(width * 0.58), -40),
                (width + 20, -40),
                (width + 20, int(height * 0.52)),
                (int(width * 0.72), int(height * 0.36)),
            ],
            fill=palette["surface"] + (76,),
        )
        draw.polygon(
            [
                (-30, int(height * 0.68)),
                (int(width * 0.42), int(height * 0.44)),
                (int(width * 0.54), height + 30),
                (-30, height + 30),
            ],
            fill=palette["surface_alt"] + (58,),
        )
        self._draw_glow(image=overlay, center=(int(width * 0.76), int(height * 0.24)), radius=int(height * 0.40), color=palette["glow"], alpha=64)
        self._draw_glow(image=overlay, center=(int(width * 0.12), int(height * 0.82)), radius=int(height * 0.28), color=palette["accent"], alpha=34)
        if family == "comparison":
            self._draw_glow(image=overlay, center=(int(width * 0.55), int(height * 0.50)), radius=int(height * 0.22), color=palette["accent"], alpha=28)
        image.alpha_composite(overlay)

    def _draw_cover_structure(
        self,
        *,
        image: Image.Image,
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int]],
        title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        chips: list[str],
    ) -> None:
        x1, y1, x2, y2 = box
        cx = int(x1 + (x2 - x1) * 0.58)
        cy = int(y1 + (y2 - y1) * 0.44)
        ring_radius = int(min(x2 - x1, y2 - y1) * 0.18)
        self._draw_glow(image=image, center=(cx, cy), radius=int(ring_radius * 1.6), color=palette["accent"], alpha=70)
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.ellipse((cx - ring_radius, cy - ring_radius, cx + ring_radius, cy + ring_radius), outline=palette["line"] + (190,), width=4)
        odraw.ellipse((cx - int(ring_radius * 0.62), cy - int(ring_radius * 0.62), cx + int(ring_radius * 0.62), cy + int(ring_radius * 0.62)), fill=palette["core"] + (255,))
        image.alpha_composite(overlay)

        core_box = (cx - 90, cy - 40, cx + 90, cy + 40)
        self._draw_shadowed_card(image=image, box=core_box, radius=24, fill=palette["core_card"], outline=palette["core_outline"], shadow=(8, 20, 30, 55))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=core_box, text=chips[0] if chips else "核心命题", font=title_font, fill=palette["title"], align="center", max_lines=2)

        top_box = (cx - 120, y1 + 34, cx + 120, y1 + 128)
        left_box = (x1 + 28, cy + 24, x1 + 240, cy + 136)
        right_box = (x2 - 228, cy + 18, x2 - 28, cy + 126)
        for idx, card in enumerate([top_box, left_box, right_box], start=1):
            fill = palette["node_a"] if idx == 1 else palette["node_b"] if idx == 2 else palette["node_c"]
            self._draw_shadowed_card(image=image, box=card, radius=24, fill=fill, outline=palette["card_outline"], shadow=(8, 18, 30, 36))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=top_box, text=chips[1] if len(chips) > 1 else "输入条件", font=body_font, fill=palette["title"], align="center", max_lines=2)
        self._draw_text_block(draw, box=left_box, text=chips[2] if len(chips) > 2 else "关键模块", font=body_font, fill=palette["title"], align="center", max_lines=3)
        self._draw_text_block(draw, box=right_box, text=chips[3] if len(chips) > 3 else "产出结果", font=body_font, fill=palette["title"], align="center", max_lines=3)
        draw.line((cx, core_box[1], (top_box[0] + top_box[2]) // 2, top_box[3]), fill=palette["line"], width=4)
        draw.line((core_box[0], cy + 6, left_box[2], (left_box[1] + left_box[3]) // 2), fill=palette["line"], width=4)
        draw.line((core_box[2], cy + 6, right_box[0], (right_box[1] + right_box[3]) // 2), fill=palette["line"], width=4)

    def _draw_cover_thesis(
        self,
        *,
        image: Image.Image,
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int]],
        title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        chips: list[str],
    ) -> None:
        x1, y1, x2, y2 = box
        slab = (int(x1 + (x2 - x1) * 0.22), y1 + 48, int(x1 + (x2 - x1) * 0.62), y2 - 54)
        self._draw_shadowed_card(image=image, box=slab, radius=30, fill=palette["core_card"], outline=palette["core_outline"], shadow=(12, 30, 48, 70))
        self._draw_glow(image=image, center=(slab[0] + 40, slab[1] + 44), radius=120, color=palette["accent"], alpha=58)

        chip_boxes = [
            (slab[2] - 40, y1 + 74, x2 - 24, y1 + 152),
            (slab[2] - 10, y1 + 178, x2 - 34, y1 + 268),
            (slab[2] - 66, y1 + 300, x2 - 22, y1 + 396),
        ]
        for idx, card in enumerate(chip_boxes):
            fill = palette["node_a"] if idx == 0 else palette["node_b"] if idx == 1 else palette["node_c"]
            self._draw_shadowed_card(image=image, box=card, radius=24, fill=fill, outline=palette["card_outline"], shadow=(8, 18, 30, 34))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=slab, text=chips[0] if chips else "核心判断", font=title_font, fill=palette["title"], align="center", max_lines=3)
        for idx, card in enumerate(chip_boxes, start=1):
            text = chips[idx] if len(chips) > idx else f"观察视角 {idx}"
            self._draw_text_block(draw, box=card, text=text, font=body_font, fill=palette["title"], align="center", max_lines=2)
        for card in chip_boxes:
            draw.line((slab[2], (slab[1] + slab[3]) // 2, card[0], (card[1] + card[3]) // 2), fill=palette["line"], width=4)

    def _draw_cover_comparison(
        self,
        *,
        image: Image.Image,
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int]],
        subtitle_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        chips: list[str],
    ) -> None:
        x1, y1, x2, y2 = box
        mid = (x1 + x2) // 2
        left = (x1 + 26, y1 + 62, mid - 18, y2 - 56)
        right = (mid + 18, y1 + 34, x2 - 26, y2 - 84)
        self._draw_shadowed_card(image=image, box=left, radius=26, fill=palette["node_a"], outline=palette["card_outline"], shadow=(10, 20, 30, 36))
        self._draw_shadowed_card(image=image, box=right, radius=26, fill=palette["node_b"], outline=palette["card_outline"], shadow=(12, 24, 34, 42))
        badge = (mid - 52, y1 + 24, mid + 52, y1 + 84)
        self._draw_pill(image=image, box=badge, radius=30, fill=palette["accent"], outline=palette["accent"], shadow=(8, 16, 28, 44))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=badge, text="对比", font=subtitle_font, fill=(255, 255, 255), align="center", max_lines=1)
        self._draw_text_block(draw, box=(left[0] + 20, left[1] + 20, left[2] - 20, left[1] + 96), text=chips[0] if chips else "方案 A", font=subtitle_font, fill=palette["title"], align="left", max_lines=2)
        self._draw_text_block(draw, box=(right[0] + 20, right[1] + 20, right[2] - 20, right[1] + 96), text=chips[1] if len(chips) > 1 else "方案 B", font=subtitle_font, fill=palette["title"], align="left", max_lines=2)
        for idx in range(3):
            ly = left[1] + 118 + idx * 74
            ry = right[1] + 118 + idx * 74
            text = chips[idx + 2] if len(chips) > idx + 2 else f"关键维度 {idx + 1}"
            self._draw_data_strip(image=image, box=(left[0] + 18, ly, left[2] - 18, ly + 56), text=text, palette=palette, fill=palette["card"], text_fill=palette["title"], font=body_font)
            self._draw_data_strip(image=image, box=(right[0] + 18, ry, right[2] - 18, ry + 56), text=text, palette=palette, fill=palette["card"], text_fill=palette["title"], font=body_font)

    def _draw_cover_command(
        self,
        *,
        image: Image.Image,
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int]],
        title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        chips: list[str],
        main_claim: str,
    ) -> None:
        x1, y1, x2, y2 = box
        terminal = (x1 + 34, y1 + 76, x2 - 44, y2 - 66)
        self._draw_shadowed_card(image=image, box=terminal, radius=28, fill=palette["terminal_bg"], outline=palette["terminal_outline"], shadow=(12, 26, 40, 68))
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle((terminal[0], terminal[1], terminal[2], terminal[1] + 54), fill=palette["terminal_top"] + (255,))
        image.alpha_composite(overlay)
        draw = ImageDraw.Draw(image)
        for idx, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            cx = terminal[0] + 22 + idx * 22
            draw.ellipse((cx, terminal[1] + 18, cx + 12, terminal[1] + 30), fill=color)
        self._draw_text_block(draw, box=(terminal[0] + 22, terminal[1] + 66, terminal[2] - 22, terminal[1] + 120), text=chips[0] if chips else "本地命令入口", font=title_font, fill=palette["terminal_text"], align="left", max_lines=2)
        lines = chips[1:4] or [main_claim or "聚焦命令、工具链与可执行路径", "命令原样保留", "解释紧贴正文"]
        ty = terminal[1] + 138
        for line in lines[:3]:
            localized = LocalizationService.localize_visual_text(line)
            draw.text((terminal[0] + 26, ty), f"> {localized}", fill=palette["terminal_text"], font=body_font)
            ty += body_font.size + 18
        side_card = (terminal[2] - 142, terminal[1] - 30, terminal[2] + 16, terminal[1] + 74)
        self._draw_shadowed_card(image=image, box=side_card, radius=22, fill=palette["node_c"], outline=palette["card_outline"], shadow=(10, 18, 26, 36))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=side_card, text=chips[3] if len(chips) > 3 else "执行入口", font=body_font, fill=palette["title"], align="center", max_lines=2)

    def _draw_text_block(
        self,
        draw: ImageDraw.ImageDraw,
        *,
        box: tuple[int, int, int, int],
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: tuple[int, int, int],
        align: str,
        max_lines: int,
    ) -> None:
        x1, y1, x2, y2 = box
        font, lines = self._fit_text_lines(
            draw=draw,
            text=text,
            font=font,
            max_width=max(20, x2 - x1 - 20),
            max_lines=max_lines,
            max_height=max(20, y2 - y1 - 6),
            min_size=12,
        )
        total_h = len(lines) * (font.size + 6) - 6
        y = y1 + max(0, (y2 - y1 - total_h) // 2)
        for line in lines:
            w = int(draw.textlength(line, font=font))
            if align == "center":
                x = x1 + max(0, (x2 - x1 - w) // 2)
            else:
                x = x1 + 12
            draw.text((x, y), line, fill=fill, font=font)
            y += font.size + 6

    def _draw_shadowed_card(
        self,
        *,
        image: Image.Image,
        box: tuple[int, int, int, int],
        radius: int,
        fill: tuple[int, int, int],
        outline: tuple[int, int, int],
        shadow: tuple[int, int, int, int],
    ) -> None:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        x1, y1, x2, y2 = box
        shadow_box = (x1 + 8, y1 + 10, x2 + 8, y2 + 10)
        draw.rounded_rectangle(shadow_box, radius=radius, fill=shadow)
        draw.rounded_rectangle(box, radius=radius, fill=fill + (255,), outline=outline + (255,), width=2)
        image.alpha_composite(overlay)

    def _draw_pill(
        self,
        image: Image.Image,
        *,
        box: tuple[int, int, int, int],
        radius: int,
        fill: tuple[int, int, int],
        outline: tuple[int, int, int],
        shadow: tuple[int, int, int, int],
    ) -> None:
        self._draw_shadowed_card(image=image, box=box, radius=radius, fill=fill, outline=outline, shadow=shadow)

    def _draw_data_strip(
        self,
        *,
        image: Image.Image,
        box: tuple[int, int, int, int],
        text: str,
        palette: dict[str, tuple[int, int, int]],
        fill: tuple[int, int, int],
        text_fill: tuple[int, int, int],
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        self._draw_shadowed_card(image=image, box=box, radius=18, fill=fill, outline=palette["card_outline"], shadow=(6, 12, 24, 24))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=box, text=text, font=font, fill=text_fill, align="left", max_lines=2)

    def _draw_glow(
        self,
        *,
        image: Image.Image,
        center: tuple[int, int],
        radius: int,
        color: tuple[int, int, int],
        alpha: int,
    ) -> None:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        cx, cy = center
        for step in range(7, 0, -1):
            current_radius = max(8, int(radius * step / 7))
            current_alpha = max(0, int(alpha * math.pow(step / 7, 2)))
            draw.ellipse((cx - current_radius, cy - current_radius, cx + current_radius, cy + current_radius), fill=color + (current_alpha,))
        image.alpha_composite(overlay)

    @staticmethod
    def _cover_family_label(family: str) -> str:
        return {
            "structure": "技术结构封面",
            "comparison": "对比分析封面",
            "command": "实战命令封面",
            "thesis": "核心观点封面",
        }.get(family, "技术解读封面")

    @staticmethod
    def _normalize_title_safe_zone(value: str) -> str:
        raw = str(value or "").strip().lower().replace("-", "_")
        if raw in {"top_left", "lefttop"}:
            return "left_top"
        if raw in {"left_middle", "middle_left", "center_left", "leftcenter"}:
            return "left_center"
        if raw in {"bottom_left", "leftbottom"}:
            return "left_bottom"
        if raw not in {"left_top", "left_center", "left_bottom"}:
            return "left_bottom"
        return raw

    @staticmethod
    def _cover_title_panel_box(*, width: int, height: int, max_width: int, panel_h: int, zone: str) -> tuple[int, int, int, int]:
        left = int(width * 0.06)
        if zone == "left_top":
            top = int(height * 0.08)
        elif zone == "left_center":
            top = max(int(height * 0.18), (height - panel_h) // 2)
        else:
            top = height - panel_h - int(height * 0.06)
        return (left, top, left + max_width + 28, top + panel_h)

    @staticmethod
    def _cover_metric_items(cover_5d: dict[str, Any]) -> list[tuple[str, str]]:
        labels = [
            ("主题主体", "主体"),
            ("场景构图", "构图"),
            ("视觉风格", "风格"),
            ("色彩光线", "光线"),
            ("文案层级", "层级"),
        ]
        items: list[tuple[str, str]] = []
        for key, short in labels:
            value = cover_5d.get(key)
            if value in (None, ""):
                continue
            try:
                display = f"{float(value):.0f}"
            except Exception:
                display = str(value)
            items.append((short, display))
        return items

    def _draw_body_background(
        self,
        *,
        image: Image.Image,
        width: int,
        height: int,
        palette: dict[str, tuple[int, int, int]],
        diagram_type: str,
    ) -> None:
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.polygon(
            [
                (int(width * 0.62), -20),
                (width + 30, -20),
                (width + 30, int(height * 0.42)),
                (int(width * 0.76), int(height * 0.30)),
            ],
            fill=palette["surface"] + (58,),
        )
        draw.polygon(
            [
                (-30, int(height * 0.66)),
                (int(width * 0.34), int(height * 0.48)),
                (int(width * 0.48), height + 20),
                (-30, height + 20),
            ],
            fill=palette["surface_alt"] + (48,),
        )
        self._draw_glow(image=overlay, center=(int(width * 0.12), int(height * 0.78)), radius=int(height * 0.24), color=palette["accent"], alpha=22)
        self._draw_glow(image=overlay, center=(int(width * 0.82), int(height * 0.20)), radius=int(height * 0.20), color=palette["glow"], alpha=30)
        if diagram_type in {"comparison_card", "comparison_infographic"}:
            self._draw_glow(image=overlay, center=(width // 2, int(height * 0.52)), radius=int(height * 0.16), color=palette["accent"], alpha=18)
        elif diagram_type in {"system_layers_infographic", "process_explainer_infographic"}:
            self._draw_glow(image=overlay, center=(width // 2, int(height * 0.30)), radius=int(height * 0.14), color=palette["glow"], alpha=16)
        if diagram_type in {"comparison_infographic", "system_layers_infographic", "process_explainer_infographic"}:
            self._draw_mesh_pattern(
                draw=draw,
                width=width,
                height=height,
                line_color=palette["line"],
                dot_color=palette["accent"],
            )
        image.alpha_composite(overlay)

    @staticmethod
    def _body_family_label(diagram_type: str) -> str:
        return {
            "architecture_diagram": "结构关系图",
            "workflow_diagram": "流程分解图",
            "comparison_card": "对比信息图",
            "comparison_infographic": "左右对比信息图",
            "system_layers_infographic": "系统分层信息图",
            "process_explainer_infographic": "执行流程解释图",
        }.get(diagram_type, "技术插图")

    def _body_detail_items(self, *, title: str, caption: str, must_show: list[str], limit: int) -> list[str]:
        raw: list[str] = []
        raw.extend(self._short_phrase(str(item).strip()) for item in must_show if str(item).strip())
        text = " ".join([title, caption]).strip()
        if text:
            fragments = re.split(r"[：:，,、；;。/\n]+", text)
            raw.extend(self._short_phrase(fragment.strip()) for fragment in fragments if fragment.strip())
        return self._dedupe_phrases(raw, limit=limit)

    @staticmethod
    def _dedupe_phrases(items: list[str], *, limit: int) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = ProgrammaticVisualService._sanitize_visual_text(item, fallback="")
            if len(text) < 2:
                continue
            if ProgrammaticVisualService._looks_corrupted_visual_text(text):
                continue
            key = re.sub(r"\s+", "", text.lower())
            if key in seen:
                continue
            seen.add(key)
            output.append(text)
            if len(output) >= limit:
                break
        return output

    @staticmethod
    def _slice_details(items: list[str], column_index: int, *, total_columns: int, desired: int) -> list[str]:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if not cleaned:
            return []
        picked: list[str] = []
        for idx, item in enumerate(cleaned):
            if idx % total_columns == column_index:
                picked.append(item)
            if len(picked) >= desired:
                break
        if len(picked) < desired:
            for item in cleaned:
                if item in picked:
                    continue
                picked.append(item)
                if len(picked) >= desired:
                    break
        return picked[:desired]

    @staticmethod
    def _shorten_label(text: str, limit: int) -> str:
        raw = str(text or "").strip()
        if len(raw) <= limit:
            return raw
        return raw[:limit]

    @staticmethod
    def _short_phrase(text: str, limit: int = 14) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        raw = ProgrammaticVisualService._sanitize_visual_text(raw, fallback="")
        if not raw or ProgrammaticVisualService._looks_corrupted_visual_text(raw):
            return ""
        if len(raw) <= limit:
            return raw
        splitters = ["：", ":", "，", ",", "、", "；", ";", "（", "(", "/", "|"]
        for splitter in splitters:
            head = raw.split(splitter, 1)[0].strip()
            if 2 <= len(head) <= limit:
                return head
        return raw[:limit]

    @staticmethod
    def _comparison_segments(title: str, items: list[str]) -> tuple[str, str]:
        cleaned_items = [ProgrammaticVisualService._sanitize_visual_text(item, fallback="") for item in items if str(item or "").strip()]
        cleaned_items = [item for item in cleaned_items if item]
        if len(cleaned_items) >= 2:
            return cleaned_items[0], cleaned_items[1]

        raw = ProgrammaticVisualService._sanitize_visual_text(title, fallback="")
        split_patterns = [
            r"(.+?)与(.+?)对比",
            r"(.+?)和(.+?)对比",
            r"(.+?)vs\.?\s*(.+)",
            r"(.+?) VS\.?\s*(.+)",
        ]
        for pattern in split_patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                left = ProgrammaticVisualService._sanitize_visual_text(match.group(1), fallback="")
                right = ProgrammaticVisualService._sanitize_visual_text(match.group(2), fallback="")
                if left and right:
                    return left, right
        return "方案 A", "方案 B"

    def _comparison_dimension_rows(
        self,
        *,
        left_title: str,
        right_title: str,
        title: str,
        details: list[str],
        desired: int = 4,
    ) -> list[dict[str, str]]:
        cleaned_details = self._dedupe_phrases(details, limit=12)
        dimension_candidates: list[str] = []
        for item in cleaned_details:
            short = self._short_phrase(item, limit=10)
            if not short:
                continue
            if short in {left_title, right_title, title}:
                continue
            dimension_candidates.append(short)
        dimension_candidates = self._dedupe_phrases(dimension_candidates, limit=desired)
        if len(dimension_candidates) < desired:
            dimension_candidates.extend(
                [item for item in ["能力重点", "使用方式", "工程代价", "适用边界"] if item not in dimension_candidates][
                    : desired - len(dimension_candidates)
                ]
            )

        left_details = [item for item in cleaned_details if item and item != right_title]
        right_details = [item for item in reversed(cleaned_details) if item and item != left_title]
        rows: list[dict[str, str]] = []
        for idx, dimension in enumerate(dimension_candidates[:desired]):
            left_value = self._slice_details(left_details, idx, total_columns=desired, desired=1)[0] if left_details else left_title
            right_value = self._slice_details(right_details, idx, total_columns=desired, desired=1)[0] if right_details else right_title
            left_value = self._sanitize_visual_text(left_value, fallback=left_title)
            right_value = self._sanitize_visual_text(right_value, fallback=right_title)
            if left_value == dimension:
                left_value = left_title
            if right_value == dimension:
                right_value = right_title
            if left_value == right_value:
                if idx % 2 == 0:
                    right_value = right_title
                else:
                    left_value = left_title
            rows.append(
                {
                    "dimension": dimension,
                    "left": self._shorten_label(left_value, 16),
                    "right": self._shorten_label(right_value, 16),
                }
            )
        return rows

    def _draw_workflow(
        self,
        *,
        image: Image.Image,
        items: list[str],
        details: list[str],
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int] | str],
        node_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        draw = ImageDraw.Draw(image)
        steps = (items[:5] or details[:5] or ["步骤 1", "步骤 2", "步骤 3"])[:5]
        secondary = details[1:] or steps
        x1, y1, x2, y2 = box
        available_h = y2 - y1
        gap = 18
        card_h = min(122, max(94, (available_h - gap * (len(steps) - 1)) // max(1, len(steps))))
        current_y = y1
        for idx, label in enumerate(steps, start=1):
            card = (x1 + 24, current_y, x2 - 24, current_y + card_h)
            fill = palette["node_a" if idx % 2 else "node_b"]
            self._draw_shadowed_card(image=image, box=card, radius=22, fill=fill, outline=palette["card_outline"], shadow=(8, 18, 28, 28))
            draw = ImageDraw.Draw(image)
            bubble = (card[0] + 18, card[1] + 18, card[0] + 70, card[1] + 70)
            draw.ellipse(bubble, fill=palette["accent"])
            draw.text((bubble[0] + 18, bubble[1] + 10), str(idx), fill=(255, 255, 255), font=node_font)
            header_box = (card[0] + 88, card[1] + 16, card[2] - 18, card[1] + 56)
            self._draw_text_block(draw, box=header_box, text=label, font=body_font, fill=palette["title"], align="left", max_lines=2)
            sub_box = (card[0] + 88, card[1] + 58, card[2] - 18, card[3] - 14)
            detail_text = secondary[min(idx - 1, len(secondary) - 1)]
            self._draw_text_block(draw, box=sub_box, text=detail_text, font=self._font(max(16, body_font.size - 2), bold=False), fill=palette["text"], align="left", max_lines=2)
            strip_y = card[3] - 18
            draw.rounded_rectangle((card[0] + 90, strip_y, card[2] - 22, strip_y + 6), radius=3, fill=palette["line"])
            if idx < len(steps):
                center_x = (card[0] + card[2]) // 2
                draw.line((center_x, card[3], center_x, card[3] + gap - 8), fill=palette["line"], width=4)
                draw.polygon([(center_x - 7, card[3] + gap - 16), (center_x + 7, card[3] + gap - 16), (center_x, card[3] + gap - 3)], fill=palette["line"])
            current_y += card_h + gap

    def _draw_architecture(
        self,
        *,
        image: Image.Image,
        items: list[str],
        details: list[str],
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int] | str],
        node_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        draw = ImageDraw.Draw(image)
        x1, y1, x2, y2 = box
        core_label = items[0] if items else "整体链路"
        columns = [text for text in (items[1:] + details) if text and text != core_label][:3]
        if len(columns) < 3:
            columns.extend(["调用入口", "处理逻辑", "结果落库"][len(columns):3])
        top = (x1 + 140, y1 + 6, x2 - 140, y1 + 84)
        self._draw_shadowed_card(image=image, box=top, radius=22, fill=palette["core_card"], outline=palette["core_outline"], shadow=(8, 18, 28, 30))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=top, text=core_label, font=node_font, fill=palette["title"], align="center", max_lines=2)

        col_gap = 18
        col_w = (x2 - x1 - col_gap * 2) // 3
        card_top = y1 + 132
        card_bottom = y2 - 92
        detail_pool = details or columns
        for idx in range(3):
            cx1 = x1 + idx * (col_w + col_gap)
            cx2 = cx1 + col_w
            card = (cx1, card_top, cx2, card_bottom)
            fill = palette["node_a"] if idx == 0 else palette["node_b"] if idx == 1 else palette["node_c"]
            self._draw_shadowed_card(image=image, box=card, radius=24, fill=fill, outline=palette["card_outline"], shadow=(8, 18, 30, 30))
            draw = ImageDraw.Draw(image)
            header = (card[0] + 16, card[1] + 16, card[2] - 16, card[1] + 72)
            self._draw_text_block(draw, box=header, text=columns[idx], font=body_font, fill=palette["title"], align="left", max_lines=2)
            line_y = card[1] + 86
            snippets = self._slice_details(detail_pool, idx, total_columns=3, desired=3)
            for snippet in snippets:
                strip = (card[0] + 14, line_y, card[2] - 14, line_y + 52)
                self._draw_data_strip(image=image, box=strip, text=snippet, palette=palette, fill=palette["card"], text_fill=palette["title"], font=self._font(max(15, body_font.size - 2), bold=False))
                line_y += 62

        draw = ImageDraw.Draw(image)
        top_center_x = (top[0] + top[2]) // 2
        for idx in range(3):
            cx1 = x1 + idx * (col_w + col_gap)
            cx2 = cx1 + col_w
            child_center = ((cx1 + cx2) // 2, card_top)
            draw.line((top_center_x, top[3], child_center[0], child_center[1]), fill=palette["line"], width=4)

        footer = (x1 + 10, y2 - 70, x2 - 10, y2)
        self._draw_shadowed_card(image=image, box=footer, radius=20, fill=palette["card"], outline=palette["card_outline"], shadow=(6, 12, 24, 20))
        draw = ImageDraw.Draw(image)
        footer_text = " / ".join(detail_pool[:4]) if detail_pool else "链路要点已结构化整理"
        self._draw_text_block(draw, box=footer, text=footer_text, font=self._font(max(15, body_font.size - 3), bold=False), fill=palette["text"], align="left", max_lines=2)

    def _draw_comparison(
        self,
        *,
        image: Image.Image,
        items: list[str],
        details: list[str],
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int] | str],
        node_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        draw = ImageDraw.Draw(image)
        x1, y1, x2, y2 = box
        left_title = items[0] if items else "方案 A"
        right_title = items[1] if len(items) > 1 else "方案 B"
        dims = details[2:] if len(details) > 2 else details
        if len(dims) < 4:
            dims.extend(["问题发现时效", "数据维度", "部署复杂度", "运维负担"][len(dims):4])

        mid = (x1 + x2) // 2
        header_h = 126
        left = (x1 + 6, y1 + 8, mid - 10, y1 + header_h)
        right = (mid + 10, y1 + 8, x2 - 6, y1 + header_h)
        self._draw_shadowed_card(image=image, box=left, radius=24, fill=palette["node_a"], outline=palette["card_outline"], shadow=(8, 18, 30, 28))
        self._draw_shadowed_card(image=image, box=right, radius=24, fill=palette["node_b"], outline=palette["card_outline"], shadow=(8, 18, 30, 28))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=left, text=left_title, font=node_font, fill=palette["title"], align="center", max_lines=2)
        self._draw_text_block(draw, box=right, text=right_title, font=node_font, fill=palette["title"], align="center", max_lines=2)

        strip_items_left = self._slice_details([left_title] + details, 0, total_columns=2, desired=2)
        strip_items_right = self._slice_details([right_title] + details, 1, total_columns=2, desired=2)
        strip_y = y1 + header_h + 20
        for idx, text in enumerate(strip_items_left):
            self._draw_data_strip(image=image, box=(left[0] + 16, strip_y + idx * 58, left[2] - 16, strip_y + idx * 58 + 46), text=text, palette=palette, fill=palette["card"], text_fill=palette["title"], font=self._font(max(14, body_font.size - 2), bold=False))
        for idx, text in enumerate(strip_items_right):
            self._draw_data_strip(image=image, box=(right[0] + 16, strip_y + idx * 58, right[2] - 16, strip_y + idx * 58 + 46), text=text, palette=palette, fill=palette["card"], text_fill=palette["title"], font=self._font(max(14, body_font.size - 2), bold=False))

        rows_top = y1 + header_h + 152
        row_gap = 14
        row_h = max(56, min(70, (y2 - rows_top - row_gap * 3) // 4))
        for idx, label in enumerate(dims[:4]):
            row = (x1 + 18, rows_top + idx * (row_h + row_gap), x2 - 18, rows_top + idx * (row_h + row_gap) + row_h)
            self._draw_shadowed_card(image=image, box=row, radius=18, fill=palette["card"], outline=palette["card_outline"], shadow=(6, 12, 20, 18))
            draw = ImageDraw.Draw(image)
            left_cell = (row[0] + 14, row[1] + 8, row[0] + 148, row[3] - 8)
            right_cell = (row[2] - 148, row[1] + 8, row[2] - 14, row[3] - 8)
            center_cell = (left_cell[2] + 12, row[1] + 6, right_cell[0] - 12, row[3] - 6)
            self._draw_shadowed_card(image=image, box=left_cell, radius=14, fill=palette["node_a"], outline=palette["card_outline"], shadow=(0, 0, 0, 0))
            self._draw_shadowed_card(image=image, box=right_cell, radius=14, fill=palette["node_b"], outline=palette["card_outline"], shadow=(0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            self._draw_text_block(draw, box=left_cell, text=left_title, font=self._font(max(14, body_font.size - 3), bold=True), fill=palette["title"], align="center", max_lines=2)
            self._draw_text_block(draw, box=right_cell, text=right_title, font=self._font(max(14, body_font.size - 3), bold=True), fill=palette["title"], align="center", max_lines=2)
            self._draw_text_block(draw, box=center_cell, text=label, font=body_font, fill=palette["title"], align="center", max_lines=2)

    def _draw_infographic_comparison(
        self,
        *,
        image: Image.Image,
        title: str,
        items: list[str],
        details: list[str],
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int] | str],
        node_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        x1, y1, x2, y2 = box
        left_title, right_title = self._comparison_segments(title, items)
        rows = self._comparison_dimension_rows(
            left_title=left_title,
            right_title=right_title,
            title=title,
            details=details or items[2:],
            desired=4,
        )

        mid = (x1 + x2) // 2
        panel_gap = 22
        panel_w = (x2 - x1 - panel_gap) // 2
        top_y = y1 + 18
        left = (x1, top_y, x1 + panel_w, y2 - 96)
        right = (mid + panel_gap // 2, top_y, x2, y2 - 96)
        self._draw_shadowed_card(image=image, box=left, radius=28, fill=palette["node_a"], outline=palette["card_outline"], shadow=(10, 20, 34, 36))
        self._draw_shadowed_card(image=image, box=right, radius=28, fill=palette["node_b"], outline=palette["card_outline"], shadow=(10, 20, 34, 36))

        left_header = (left[0] + 16, left[1] + 16, left[2] - 16, left[1] + 86)
        right_header = (right[0] + 16, right[1] + 16, right[2] - 16, right[1] + 86)
        self._draw_shadowed_card(image=image, box=left_header, radius=20, fill=palette["accent"], outline=palette["accent"], shadow=(4, 10, 16, 12))
        self._draw_shadowed_card(image=image, box=right_header, radius=20, fill=palette["line"], outline=palette["line"], shadow=(4, 10, 16, 12))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=left_header, text=left_title, font=node_font, fill=(255, 255, 255), align="center", max_lines=2)
        self._draw_text_block(draw, box=right_header, text=right_title, font=node_font, fill=(255, 255, 255), align="center", max_lines=2)

        self._draw_section_badge(
            image=image,
            box=(left[0] + 22, left[1] + 102, left[0] + 132, left[1] + 136),
            text="?? A",
            fill=palette["surface"],
            outline=palette["card_outline"],
            text_fill=palette["chip_text"],
            font=meta_font,
        )
        self._draw_section_badge(
            image=image,
            box=(right[2] - 132, right[1] + 102, right[2] - 22, right[1] + 136),
            text="?? B",
            fill=palette["surface"],
            outline=palette["card_outline"],
            text_fill=palette["chip_text"],
            font=meta_font,
        )

        axis_top = left[1] + 110
        axis_bottom = left[3] - 108
        draw = ImageDraw.Draw(image)
        draw.line((mid, axis_top, mid, axis_bottom), fill=palette["line"], width=4)
        for step in range(4):
            dot_y = axis_top + int((axis_bottom - axis_top) * step / 3)
            draw.ellipse((mid - 7, dot_y - 7, mid + 7, dot_y + 7), fill=palette["surface"], outline=palette["line"], width=3)

        row_top = left[1] + 146
        row_gap = 16
        row_h = max(56, min(74, (axis_bottom - row_top - row_gap * 3) // 4))
        strip_font = self._font(max(14, body_font.size - 2), bold=False)
        for idx, row in enumerate(rows):
            top = row_top + idx * (row_h + row_gap)
            dimension_box = (mid - 92, top + 8, mid + 92, top + row_h - 8)
            self._draw_shadowed_card(
                image=image,
                box=dimension_box,
                radius=16,
                fill=palette["surface"],
                outline=palette["card_outline"],
                shadow=(0, 0, 0, 0),
            )
            draw = ImageDraw.Draw(image)
            self._draw_text_block(draw, box=dimension_box, text=row["dimension"], font=body_font, fill=palette["title"], align="center", max_lines=2)
            self._draw_data_strip(
                image=image,
                box=(left[0] + 18, top, dimension_box[0] - 14, top + row_h),
                text=row["left"],
                palette=palette,
                fill=palette["surface_alt"],
                text_fill=palette["text"],
                font=strip_font,
            )
            self._draw_data_strip(
                image=image,
                box=(dimension_box[2] + 14, top, right[2] - 18, top + row_h),
                text=row["right"],
                palette=palette,
                fill=palette["surface_alt"],
                text_fill=palette["text"],
                font=strip_font,
            )

        footer = (x1 + 16, y2 - 76, x2 - 16, y2 - 8)
        summary = " / ".join(self._dedupe_phrases([left_title, right_title] + [item["dimension"] for item in rows], limit=5))
        self._draw_summary_callout(
            image=image,
            box=footer,
            title="????",
            body=summary,
            palette=palette,
            title_font=meta_font,
            body_font=self._font(max(14, meta_font.size - 1), bold=False),
        )
        left_note = (left[0] + 18, left[3] - 86, left[2] - 18, left[3] - 18)
        right_note = (right[0] + 18, right[3] - 86, right[2] - 18, right[3] - 18)
        self._draw_summary_callout(
            image=image,
            box=left_note,
            title="????",
            body=rows[0]["left"],
            palette=palette,
            title_font=meta_font,
            body_font=self._font(max(14, meta_font.size - 1), bold=False),
        )
        self._draw_summary_callout(
            image=image,
            box=right_note,
            title="????",
            body=rows[0]["right"],
            palette=palette,
            title_font=meta_font,
            body_font=self._font(max(14, meta_font.size - 1), bold=False),
        )

    def _draw_infographic_system_layers(
        self,
        *,
        image: Image.Image,
        title: str,
        items: list[str],
        details: list[str],
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int] | str],
        node_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        x1, y1, x2, y2 = box
        layers = items[:3] if len(items) >= 3 else []
        if len(layers) < 3:
            layers.extend(["输入与上下文", "核心推理与编排", "执行与落地"][len(layers):3])
        layer_details = details or items[3:]
        col_gap = 18
        col_w = (x2 - x1 - col_gap * 2) // 3
        top = y1 + 32
        bottom = y2 - 92
        draw = ImageDraw.Draw(image)
        for idx, layer in enumerate(layers):
            cx1 = x1 + idx * (col_w + col_gap)
            cx2 = cx1 + col_w
            card = (cx1, top, cx2, bottom)
            fill = palette["node_a"] if idx == 0 else palette["node_b"] if idx == 1 else palette["node_c"]
            self._draw_shadowed_card(image=image, box=card, radius=28, fill=fill, outline=palette["card_outline"], shadow=(10, 20, 34, 36))
            self._draw_section_badge(image=image, box=(cx1 + 16, top + 14, cx1 + 110, top + 46), text=f"第 {idx + 1} 层", fill=palette["surface"], outline=palette["card_outline"], text_fill=palette["chip_text"], font=meta_font)
            snippets = self._slice_details(layer_details, idx, total_columns=3, desired=3)
            icon_center = ((cx1 + cx2) // 2, top + 38)
            layer_context = " ".join([layer] + snippets[:2])
            self._draw_tech_icon(image=image, center=icon_center, accent=palette["accent"], kind=self._infer_icon_kind(layer_context))
            header = (cx1 + 18, top + 60, cx2 - 18, top + 128)
            header_fill = palette["accent"] if idx == 0 else palette["line"] if idx == 1 else palette["chip_text"]
            self._draw_shadowed_card(image=image, box=header, radius=18, fill=header_fill, outline=header_fill, shadow=(4, 10, 16, 12))
            draw = ImageDraw.Draw(image)
            self._draw_text_block(draw, box=header, text=layer, font=node_font, fill=(255, 255, 255), align="center", max_lines=2)
            row_y = top + 142
            for snippet in snippets:
                self._draw_data_strip(
                    image=image,
                    box=(cx1 + 16, row_y, cx2 - 16, row_y + 54),
                    text=snippet,
                    palette=palette,
                    fill=palette["card"],
                    text_fill=palette["text"],
                    font=self._font(max(14, body_font.size - 2), bold=False),
                )
                row_y += 66
            note_box = (cx1 + 16, bottom - 70, cx2 - 16, bottom - 14)
            self._draw_summary_callout(
                image=image,
                box=note_box,
                title="本层作用",
                body=self._slice_details(layer_details or layers, idx, total_columns=3, desired=1)[0],
                palette=palette,
                title_font=meta_font,
                body_font=self._font(max(13, meta_font.size - 1), bold=False),
            )

        draw = ImageDraw.Draw(image)
        link_y = top + 22
        for idx in range(2):
            start_x = x1 + (idx + 1) * col_w + idx * col_gap + col_gap // 2
            end_x = start_x + col_gap
            draw.line((start_x, link_y, end_x, link_y), fill=palette["line"], width=5)
            draw.polygon([(end_x - 12, link_y - 8), (end_x - 12, link_y + 8), (end_x + 2, link_y)], fill=palette["line"])

        footer = (x1 + 20, y2 - 72, x2 - 20, y2 - 6)
        summary = " -> ".join(layers)
        self._draw_summary_callout(
            image=image,
            box=footer,
            title="层级关系",
            body=summary,
            palette=palette,
            title_font=meta_font,
            body_font=self._font(max(14, meta_font.size - 1), bold=False),
        )

    def _draw_infographic_process(
        self,
        *,
        image: Image.Image,
        title: str,
        items: list[str],
        details: list[str],
        box: tuple[int, int, int, int],
        palette: dict[str, tuple[int, int, int] | str],
        node_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        x1, y1, x2, y2 = box
        steps = items[:4] if items else []
        if len(steps) < 4:
            steps.extend(["输入", "分析", "执行", "反馈"][len(steps):4])
        snippets = details or steps
        gap = 18
        card_w = (x2 - x1 - gap * 3) // 4
        top = y1 + 22
        bottom = y2 - 112
        for idx, step in enumerate(steps):
            cx1 = x1 + idx * (card_w + gap)
            cx2 = cx1 + card_w
            y_offset = 16 if idx % 2 else 0
            card = (cx1, top + y_offset, cx2, bottom - y_offset)
            fill = palette["node_a"] if idx % 3 == 0 else palette["node_b"] if idx % 3 == 1 else palette["node_c"]
            self._draw_shadowed_card(image=image, box=card, radius=24, fill=fill, outline=palette["card_outline"], shadow=(8, 18, 30, 30))
            draw = ImageDraw.Draw(image)
            bubble = (card[0] + 18, card[1] + 16, card[0] + 70, card[1] + 68)
            draw.ellipse(bubble, fill=palette["accent"])
            draw.text((bubble[0] + 18, bubble[1] + 8), str(idx + 1), fill=(255, 255, 255), font=node_font)
            step_snippets = self._slice_details(snippets, idx, total_columns=4, desired=3)
            step_context = " ".join([step] + step_snippets[:2])
            self._draw_tech_icon(image=image, center=(card[2] - 36, card[1] + 42), accent=palette["line"], kind=self._infer_icon_kind(step_context), radius=18)
            header = (card[0] + 12, card[1] + 78, card[2] - 12, card[1] + 140)
            self._draw_shadowed_card(image=image, box=header, radius=16, fill=palette["surface"], outline=palette["card_outline"], shadow=(2, 6, 10, 8))
            draw = ImageDraw.Draw(image)
            self._draw_text_block(draw, box=header, text=step, font=node_font, fill=palette["title"], align="center", max_lines=2)
            row_y = card[1] + 154
            for text in step_snippets:
                self._draw_data_strip(
                    image=image,
                    box=(card[0] + 14, row_y, card[2] - 14, row_y + 48),
                    text=text,
                    palette=palette,
                    fill=palette["card"],
                    text_fill=palette["text"],
                    font=self._font(max(13, body_font.size - 3), bold=False),
                )
                row_y += 58
            if idx < len(steps) - 1:
                arrow_y1 = card[1] + 44
                arrow_y2 = top + (16 if (idx + 1) % 2 else 0) + 44
                draw.line((card[2] + 4, arrow_y1, card[2] + gap - 10, arrow_y2), fill=palette["line"], width=5)
                draw.polygon([(card[2] + gap - 20, arrow_y2 - 8), (card[2] + gap - 20, arrow_y2 + 8), (card[2] + gap - 4, arrow_y2)], fill=palette["line"])

        footer = (x1 + 24, y2 - 88, x2 - 24, y2 - 14)
        summary = " -> ".join(steps)
        self._draw_summary_callout(
            image=image,
            box=footer,
            title="流程摘要",
            body=summary,
            palette=palette,
            title_font=meta_font,
            body_font=self._font(max(14, meta_font.size - 1), bold=False),
        )

    def _draw_tech_icon(
        self,
        *,
        image: Image.Image,
        center: tuple[int, int],
        accent: tuple[int, int, int] | str,
        kind: str = "generic",
        radius: int = 24,
    ) -> None:
        color = accent if isinstance(accent, tuple) else (39, 108, 228)
        draw = ImageDraw.Draw(image)
        cx, cy = center
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(255, 255, 255), outline=color, width=3)
        inner = max(8, radius - 10)
        if kind == "database":
            draw.ellipse((cx - inner, cy - inner + 4, cx + inner, cy - inner + 14), outline=color, width=3)
            draw.rectangle((cx - inner, cy - inner + 9, cx + inner, cy + inner - 9), outline=color, width=3)
            draw.arc((cx - inner, cy + inner - 18, cx + inner, cy + inner - 2), 0, 180, fill=color, width=3)
        elif kind == "planner":
            draw.rounded_rectangle((cx - inner + 2, cy - inner + 2, cx + inner - 2, cy + inner - 2), radius=6, outline=color, width=3)
            draw.line((cx - inner + 8, cy - inner + 10, cx + inner - 8, cy - inner + 10), fill=color, width=3)
            for offset in (-6, 4):
                draw.rectangle((cx - inner + 9, cy + offset, cx - inner + 15, cy + offset + 6), outline=color, width=2)
                draw.line((cx - inner + 18, cy + offset + 3, cx + inner - 8, cy + offset + 3), fill=color, width=3)
        elif kind == "api":
            draw.arc((cx - inner, cy - inner, cx + inner, cy + inner), 10, 350, fill=color, width=3)
            draw.line((cx, cy - inner + 3, cx, cy + inner - 3), fill=color, width=3)
            draw.line((cx - inner + 3, cy, cx + inner - 3, cy), fill=color, width=3)
        elif kind == "search":
            draw.ellipse((cx - inner + 2, cy - inner + 2, cx + inner - 8, cy + inner - 8), outline=color, width=3)
            draw.line((cx + 4, cy + 4, cx + inner, cy + inner), fill=color, width=4)
        elif kind == "frontend":
            draw.rounded_rectangle((cx - inner, cy - inner + 2, cx + inner, cy + inner - 2), radius=7, outline=color, width=3)
            draw.line((cx - inner, cy - inner + 11, cx + inner, cy - inner + 11), fill=color, width=3)
            for dot_x in (cx - inner + 8, cx - inner + 16, cx - inner + 24):
                draw.ellipse((dot_x - 2, cy - inner + 5, dot_x + 2, cy - inner + 9), fill=color)
            draw.rectangle((cx - inner + 8, cy - inner + 18, cx - 4, cy + inner - 8), outline=color, width=2)
            draw.rectangle((cx + 4, cy - inner + 18, cx + inner - 8, cy + inner - 8), outline=color, width=2)
        elif kind == "backend":
            draw.rounded_rectangle((cx - inner, cy - inner + 2, cx + inner, cy + inner - 2), radius=6, outline=color, width=3)
            draw.line((cx - inner + 6, cy - 4, cx + inner - 6, cy - 4), fill=color, width=3)
            draw.line((cx - inner + 6, cy + 6, cx + inner - 6, cy + 6), fill=color, width=3)
            for light_y in (cy - 9, cy + 1):
                draw.ellipse((cx - inner + 7, light_y, cx - inner + 13, light_y + 6), fill=color)
        elif kind == "browser":
            draw.rounded_rectangle((cx - inner, cy - inner + 2, cx + inner, cy + inner - 2), radius=8, outline=color, width=3)
            draw.line((cx - inner, cy - inner + 11, cx + inner, cy - inner + 11), fill=color, width=3)
            for dot_x in (cx - inner + 8, cx - inner + 16, cx - inner + 24):
                draw.ellipse((dot_x - 2, cy - inner + 5, dot_x + 2, cy - inner + 9), fill=color)
            draw.arc((cx - 10, cy - 4, cx + 10, cy + 16), 210, 330, fill=color, width=3)
            draw.line((cx - 10, cy + 6, cx + 10, cy + 6), fill=color, width=2)
        elif kind == "file":
            draw.rounded_rectangle((cx - inner + 2, cy - inner + 1, cx + inner - 2, cy + inner - 1), radius=6, outline=color, width=3)
            draw.line((cx + 2, cy - inner + 1, cx + inner - 2, cy - inner + 1), fill=color, width=3)
            draw.line((cx + 6, cy - inner + 1, cx + 6, cy - inner + 12), fill=color, width=3)
        elif kind == "security":
            shield = [
                (cx, cy - inner),
                (cx + inner - 4, cy - inner + 6),
                (cx + inner - 6, cy + 2),
                (cx, cy + inner),
                (cx - inner + 6, cy + 2),
                (cx - inner + 4, cy - inner + 6),
            ]
            draw.line(shield + [shield[0]], fill=color, width=3)
            draw.line((cx - 6, cy + 1, cx - 1, cy + 7), fill=color, width=3)
            draw.line((cx - 1, cy + 7, cx + 9, cy - 5), fill=color, width=3)
        elif kind == "user":
            draw.ellipse((cx - 8, cy - inner + 3, cx + 8, cy - 2), outline=color, width=3)
            draw.arc((cx - 14, cy - 1, cx + 14, cy + inner), 200, 340, fill=color, width=3)
        elif kind == "agent":
            draw.ellipse((cx - inner + 4, cy - inner + 2, cx + inner - 4, cy + inner - 4), outline=color, width=3)
            draw.ellipse((cx - 8, cy - 4, cx - 2, cy + 2), fill=color)
            draw.ellipse((cx + 2, cy - 4, cx + 8, cy + 2), fill=color)
            draw.arc((cx - 10, cy + 2, cx + 10, cy + 12), 10, 170, fill=color, width=3)
        elif kind == "model":
            draw.rounded_rectangle((cx - inner + 3, cy - inner + 3, cx + inner - 3, cy + inner - 3), radius=6, outline=color, width=3)
            draw.line((cx - 6, cy - 2, cx + 6, cy - 2), fill=color, width=3)
            draw.line((cx - 6, cy + 4, cx + 6, cy + 4), fill=color, width=3)
            draw.line((cx - inner - 4, cy - 6, cx - inner + 3, cy - 6), fill=color, width=3)
            draw.line((cx + inner - 3, cy - 6, cx + inner + 4, cy - 6), fill=color, width=3)
            draw.line((cx - inner - 4, cy + 6, cx - inner + 3, cy + 6), fill=color, width=3)
            draw.line((cx + inner - 3, cy + 6, cx + inner + 4, cy + 6), fill=color, width=3)
        elif kind == "runtime":
            draw.rectangle((cx - inner + 2, cy - inner + 4, cx + inner - 2, cy + inner - 6), outline=color, width=3)
            draw.line((cx - inner + 8, cy + inner - 1, cx + inner - 8, cy + inner - 1), fill=color, width=3)
            draw.line((cx - 6, cy + inner + 7, cx + 6, cy + inner + 7), fill=color, width=3)
        else:
            draw.line((cx, cy - 10, cx, cy + 10), fill=color, width=4)
            draw.line((cx - 10, cy, cx + 10, cy), fill=color, width=4)

    def _draw_section_badge(
        self,
        *,
        image: Image.Image,
        box: tuple[int, int, int, int],
        text: str,
        fill: tuple[int, int, int],
        outline: tuple[int, int, int],
        text_fill: tuple[int, int, int],
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        self._draw_pill(image=image, box=box, radius=(box[3] - box[1]) // 2, fill=fill, outline=outline, shadow=(4, 8, 16, 14))
        draw = ImageDraw.Draw(image)
        self._draw_text_block(draw, box=box, text=text, font=font, fill=text_fill, align="center", max_lines=1)

    def _draw_summary_callout(
        self,
        *,
        image: Image.Image,
        box: tuple[int, int, int, int],
        title: str,
        body: str,
        palette: dict[str, tuple[int, int, int] | str],
        title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        self._draw_shadowed_card(image=image, box=box, radius=18, fill=palette["surface"], outline=palette["card_outline"], shadow=(6, 12, 20, 18))
        draw = ImageDraw.Draw(image)
        title_box = (box[0] + 14, box[1] + 10, box[0] + 132, box[1] + 38)
        self._draw_section_badge(
            image=image,
            box=title_box,
            text=title,
            fill=palette["eyebrow_bg"],
            outline=palette["eyebrow_outline"],
            text_fill=palette["eyebrow_text"],
            font=title_font,
        )
        self._draw_text_block(draw, box=(box[0] + 144, box[1] + 8, box[2] - 14, box[3] - 10), text=body, font=body_font, fill=palette["text"], align="left", max_lines=2)

    @staticmethod
    def _looks_corrupted_visual_text(text: str) -> bool:
        raw = str(text or "").strip()
        if not raw:
            return False
        if "\ufffd" in raw:
            return True
        normalized = re.sub(r"\s+", "", raw)
        qmarks = normalized.count("?") + normalized.count("？")
        if qmarks == 0:
            return False
        if qmarks >= 3:
            return True
        if qmarks / max(len(normalized), 1) >= 0.18:
            return True
        cleaned = re.sub(r"[?？]", "", normalized)
        return len(cleaned) < 2

    @staticmethod
    def _sanitize_visual_text(text: str, fallback: str = "") -> str:
        def _clean(value: str) -> str:
            cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
            cleaned = cleaned.replace("\ufffd", "")
            cleaned = re.sub(r"(?<=[\u4e00-\u9fffA-Za-z0-9])[???]+(?=[\u4e00-\u9fffA-Za-z0-9])", "", cleaned)
            cleaned = re.sub(r"[???]{2,}", " ", cleaned)
            cleaned = re.sub(r"^[???]+|[???]+$", "", cleaned).strip()
            cleaned = re.sub(r"^[\[\](){}<>:;,.\/|`~!@#$%^&*_+=-]+", "", cleaned)
            cleaned = re.sub(r"[\[\](){}<>:;,.\/|`~!@#$%^&*_+=-]+$", "", cleaned)
            cleaned = re.sub(r"\b[a-z]{1,3}\)$", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            return cleaned

        primary = _clean(text)
        if primary and not ProgrammaticVisualService._looks_corrupted_visual_text(primary):
            return primary
        secondary = _clean(fallback)
        if secondary and not ProgrammaticVisualService._looks_corrupted_visual_text(secondary):
            return secondary
        return primary or secondary

    @staticmethod
    def _infer_icon_kind(text: str) -> str:
        raw = str(text or "").lower()
        if any(token in raw for token in ["数据库", "存储", "向量", "memory", "cache", "store"]):
            return "database"
        if any(token in raw for token in ["前端", "界面", "react", "ui", "客户端", "页面组件"]):
            return "frontend"
        if any(token in raw for token in ["后端", "fastapi", "backend", "handler", "service", "服务端"]):
            return "backend"
        if any(token in raw for token in ["浏览器", "browser", "dom", "网页", "webview"]):
            return "browser"
        if any(token in raw for token in ["权限", "安全", "鉴权", "hook", "sandbox", "沙箱"]):
            return "security"
        if any(token in raw for token in ["规划", "计划", "planner", "plan", "任务拆解"]):
            return "planner"
        if any(token in raw for token in ["api", "接口", "tool", "插件", "集成"]):
            return "api"
        if any(token in raw for token in ["搜索", "检索", "query", "search"]):
            return "search"
        if any(token in raw for token in ["用户", "指令", "目标", "输入", "question"]):
            return "user"
        if any(token in raw for token in ["文件", "文档", "上传", "repo", "readme"]):
            return "file"
        if any(token in raw for token in ["模型", "embedding", "推理", "reason", "brain"]):
            return "model"
        if any(token in raw for token in ["agent", "llm", "智能体", "模型", "brain"]):
            return "agent"
        if any(token in raw for token in ["runtime", "执行", "流程", "调用", "server", "服务"]):
            return "runtime"
        return "generic"

    def _draw_mesh_pattern(
        self,
        *,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        line_color: tuple[int, int, int] | str,
        dot_color: tuple[int, int, int] | str,
    ) -> None:
        line = line_color if isinstance(line_color, tuple) else (76, 116, 170)
        dot = dot_color if isinstance(dot_color, tuple) else (39, 108, 228)
        nodes = [
            (int(width * 0.08), int(height * 0.18)),
            (int(width * 0.18), int(height * 0.11)),
            (int(width * 0.28), int(height * 0.18)),
            (int(width * 0.72), int(height * 0.14)),
            (int(width * 0.84), int(height * 0.10)),
            (int(width * 0.90), int(height * 0.22)),
            (int(width * 0.12), int(height * 0.86)),
            (int(width * 0.24), int(height * 0.92)),
            (int(width * 0.80), int(height * 0.88)),
            (int(width * 0.92), int(height * 0.80)),
        ]
        links = [(0, 1), (1, 2), (3, 4), (4, 5), (6, 7), (8, 9)]
        for a, b in links:
            draw.line((*nodes[a], *nodes[b]), fill=line + (46,), width=2)
        for x, y in nodes:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=dot + (86,), outline=line + (80,))

    def _draw_gradient(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        color_a: tuple[int, int, int],
        color_b: tuple[int, int, int],
    ) -> None:
        steps = max(width, height)
        for i in range(steps):
            ratio = i / max(steps - 1, 1)
            color = tuple(int(color_a[c] * (1 - ratio) + color_b[c] * ratio) for c in range(3))
            draw.line((0, i, width, i), fill=color)

    def _draw_centered_text(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: tuple[int, int, int],
    ) -> None:
        font, lines = self._fit_text_lines(
            draw=draw,
            text=text,
            font=font,
            max_width=box[2] - box[0] - 24,
            max_lines=4,
            max_height=max(20, box[3] - box[1] - 8),
            min_size=12,
        )
        total_h = len(lines) * (font.size + 4)
        y = box[1] + ((box[3] - box[1] - total_h) // 2)
        for line in lines:
            w = int(draw.textlength(line, font=font))
            x = box[0] + ((box[2] - box[0] - w) // 2)
            draw.text((x, y), line, fill=fill, font=font)
            y += font.size + 4

    def _fit_text_lines(
        self,
        *,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        max_lines: int,
        max_height: int,
        min_size: int,
    ) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, list[str]]:
        current_font = font
        current_size = max(1, int(getattr(font, "size", min_size)))
        while current_size >= min_size:
            lines, truncated = self._wrap_text_state(
                draw=draw,
                text=text,
                font=current_font,
                max_width=max_width,
                max_lines=max_lines,
            )
            total_h = len(lines) * (current_font.size + 6) - 6 if lines else 0
            if not truncated and total_h <= max_height:
                return current_font, lines
            next_size = current_size - 2
            if next_size < min_size:
                break
            current_size = next_size
            current_font = self._font_from_existing(font=current_font, size=current_size)
        lines, _ = self._wrap_text_state(
            draw=draw,
            text=text,
            font=current_font,
            max_width=max_width,
            max_lines=max_lines,
        )
        return current_font, lines

    def _font_from_existing(
        self,
        *,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        path = getattr(font, "path", "") or ""
        if path:
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
        bold_hint = "bold" in str(path).lower() or "bd" in str(path).lower()
        return self._font(size, bold=bold_hint)

    def _wrap_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        max_lines: int,
    ) -> list[str]:
        lines, _ = self._wrap_text_state(
            draw=draw,
            text=text,
            font=font,
            max_width=max_width,
            max_lines=max_lines,
        )
        return lines

    def _wrap_text_state(
        self,
        *,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        max_lines: int,
    ) -> tuple[list[str], bool]:
        source = str(text or "").strip()
        if not source:
            return [""], False
        words = source.split(" ")
        if len(words) == 1 and len(source) > 10:
            words = list(source)
        tokens: list[tuple[str, bool]] = []
        for word in words:
            if not word:
                continue
            if draw.textlength(word, font=font) <= max_width:
                tokens.append((word, False))
                continue
            parts = self._split_long_token(draw=draw, token=word, font=font, max_width=max_width)
            for idx, part in enumerate(parts):
                tokens.append((part, idx > 0))
        lines: list[str] = []
        current = ""
        consumed = 0
        for token, join_without_space in tokens:
            candidate = self._join_wrapped_piece(current=current, token=token, join_without_space=join_without_space)
            if candidate and draw.textlength(candidate, font=font) <= max_width:
                current = candidate
                consumed += 1
            else:
                if current:
                    lines.append(current)
                current = token
                consumed += 1
                if len(lines) >= max_lines - 1:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        truncated = consumed < len(tokens)
        return lines or [source[: max(1, max_lines)]], truncated

    @staticmethod
    def _join_wrapped_piece(current: str, token: str, join_without_space: bool) -> str:
        if not current:
            return token
        if join_without_space:
            return f"{current}{token}"
        return f"{current} {token}".strip()

    @staticmethod
    def _split_long_token(
        *,
        draw: ImageDraw.ImageDraw,
        token: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        pieces: list[str] = []
        current = ""
        for char in str(token):
            candidate = f"{current}{char}"
            if candidate and draw.textlength(candidate, font=font) <= max_width:
                current = candidate
                continue
            if current:
                pieces.append(current)
            current = char
        if current:
            pieces.append(current)
        return pieces or [token]

    def _rounded_rect(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        radius: int,
        fill: tuple[int, int, int],
        *,
        outline: tuple[int, int, int],
    ) -> None:
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3)

    @staticmethod
    def _palette_for_family(family: str) -> dict[str, tuple[int, int, int]]:
        if family == "comparison":
            return {
                "background": (248, 242, 233),
                "background_alt": (231, 221, 208),
                "surface": (255, 249, 242),
                "surface_alt": (232, 244, 244),
                "stage": (255, 251, 246),
                "stage_outline": (220, 207, 193),
                "card": (255, 255, 255),
                "node_a": (246, 233, 214),
                "node_b": (224, 236, 247),
                "node_c": (233, 242, 229),
                "core": (209, 96, 52),
                "core_card": (255, 245, 234),
                "core_outline": (212, 161, 127),
                "title": (49, 33, 21),
                "text": (101, 74, 55),
                "border": (210, 192, 175),
                "card_outline": (215, 198, 182),
                "chip_bg": (255, 248, 238),
                "chip_outline": (223, 204, 186),
                "chip_text": (104, 60, 27),
                "eyebrow_bg": (255, 244, 228),
                "eyebrow_outline": (217, 184, 154),
                "eyebrow_text": (123, 71, 31),
                "metric_bg": (255, 251, 245),
                "metric_outline": (224, 204, 186),
                "metric_label": (128, 97, 74),
                "metric_value": (45, 31, 23),
                "line": (141, 103, 81),
                "accent": (204, 96, 61),
                "glow": (240, 150, 102),
                "terminal_bg": (31, 26, 25),
                "terminal_outline": (93, 74, 67),
                "terminal_top": (57, 43, 40),
                "terminal_text": (247, 242, 236),
            }
        if family == "command":
            return {
                "background": (9, 16, 28),
                "background_alt": (22, 32, 50),
                "surface": (15, 27, 42),
                "surface_alt": (20, 46, 60),
                "stage": (14, 22, 35),
                "stage_outline": (56, 82, 110),
                "card": (19, 29, 49),
                "node_a": (22, 39, 60),
                "node_b": (28, 56, 68),
                "node_c": (38, 63, 91),
                "core": (47, 209, 173),
                "core_card": (20, 42, 53),
                "core_outline": (72, 156, 143),
                "title": (242, 247, 252),
                "text": (191, 208, 226),
                "border": (63, 88, 118),
                "card_outline": (69, 95, 123),
                "chip_bg": (28, 43, 70),
                "chip_outline": (66, 94, 133),
                "chip_text": (228, 241, 252),
                "eyebrow_bg": (22, 46, 60),
                "eyebrow_outline": (62, 126, 133),
                "eyebrow_text": (195, 238, 232),
                "metric_bg": (17, 28, 43),
                "metric_outline": (57, 84, 111),
                "metric_label": (138, 170, 198),
                "metric_value": (243, 248, 252),
                "line": (114, 177, 223),
                "accent": (44, 204, 160),
                "glow": (67, 194, 215),
                "terminal_bg": (10, 18, 30),
                "terminal_outline": (63, 90, 122),
                "terminal_top": (20, 31, 46),
                "terminal_text": (214, 242, 238),
            }
        if family == "thesis":
            return {
                "background": (243, 240, 234),
                "background_alt": (225, 222, 214),
                "surface": (255, 248, 241),
                "surface_alt": (231, 236, 245),
                "stage": (251, 247, 241),
                "stage_outline": (214, 208, 199),
                "card": (255, 255, 255),
                "node_a": (255, 247, 238),
                "node_b": (240, 246, 255),
                "node_c": (238, 246, 239),
                "core": (187, 87, 61),
                "core_card": (253, 244, 236),
                "core_outline": (208, 166, 146),
                "title": (42, 34, 30),
                "text": (98, 83, 74),
                "border": (211, 204, 194),
                "card_outline": (214, 206, 198),
                "chip_bg": (254, 248, 241),
                "chip_outline": (221, 211, 199),
                "chip_text": (90, 64, 51),
                "eyebrow_bg": (252, 241, 232),
                "eyebrow_outline": (220, 194, 175),
                "eyebrow_text": (121, 79, 57),
                "metric_bg": (255, 250, 245),
                "metric_outline": (223, 212, 201),
                "metric_label": (134, 111, 94),
                "metric_value": (54, 42, 36),
                "line": (154, 118, 95),
                "accent": (189, 96, 72),
                "glow": (233, 156, 111),
                "terminal_bg": (33, 29, 28),
                "terminal_outline": (87, 72, 67),
                "terminal_top": (54, 43, 40),
                "terminal_text": (247, 242, 237),
            }
        return {
            "background": (238, 244, 251),
            "background_alt": (220, 231, 245),
            "surface": (255, 255, 255),
            "surface_alt": (231, 240, 252),
            "stage": (248, 251, 255),
            "stage_outline": (199, 214, 232),
            "card": (255, 255, 255),
            "node_a": (230, 240, 255),
            "node_b": (233, 246, 240),
            "node_c": (243, 236, 255),
            "core": (43, 111, 224),
            "core_card": (240, 246, 255),
            "core_outline": (147, 182, 228),
            "title": (21, 44, 75),
            "text": (71, 92, 116),
            "border": (196, 213, 232),
            "card_outline": (201, 216, 232),
            "chip_bg": (243, 248, 255),
            "chip_outline": (203, 219, 236),
            "chip_text": (33, 73, 128),
            "eyebrow_bg": (233, 242, 255),
            "eyebrow_outline": (176, 203, 236),
            "eyebrow_text": (34, 79, 143),
            "metric_bg": (248, 251, 255),
            "metric_outline": (204, 218, 234),
            "metric_label": (103, 124, 151),
            "metric_value": (22, 43, 74),
            "line": (87, 129, 183),
            "accent": (39, 111, 228),
            "glow": (118, 177, 255),
            "terminal_bg": (18, 28, 42),
            "terminal_outline": (69, 94, 122),
            "terminal_top": (28, 41, 57),
            "terminal_text": (236, 243, 251),
        }

    @staticmethod
    def _palette_for_diagram(diagram_type: str) -> dict[str, tuple[int, int, int]]:
        if diagram_type == "comparison_infographic":
            return {
                "background": (236, 244, 255),
                "background_alt": (208, 225, 248),
                "surface": (255, 255, 255),
                "surface_alt": (228, 240, 255),
                "node_a": (241, 248, 255),
                "node_b": (238, 247, 242),
                "node_c": (234, 242, 255),
                "card": (255, 255, 255),
                "title": (14, 35, 65),
                "text": (62, 86, 112),
                "border": (182, 205, 232),
                "card_outline": (182, 205, 232),
                "core_card": (241, 247, 255),
                "core_outline": (168, 194, 228),
                "chip_bg": (244, 249, 255),
                "chip_outline": (200, 216, 234),
                "chip_text": (34, 80, 146),
                "eyebrow_bg": (221, 236, 255),
                "eyebrow_outline": (170, 198, 235),
                "eyebrow_text": (34, 78, 145),
                "line": (48, 114, 192),
                "accent": (24, 104, 224),
                "glow": (98, 170, 255),
            }
        if diagram_type == "system_layers_infographic":
            return {
                "background": (238, 246, 255),
                "background_alt": (213, 227, 247),
                "surface": (255, 255, 255),
                "surface_alt": (230, 242, 255),
                "node_a": (235, 245, 255),
                "node_b": (230, 243, 239),
                "node_c": (239, 234, 255),
                "card": (255, 255, 255),
                "title": (18, 42, 74),
                "text": (67, 91, 117),
                "border": (186, 207, 230),
                "card_outline": (186, 207, 230),
                "core_card": (239, 246, 255),
                "core_outline": (160, 190, 228),
                "chip_bg": (242, 247, 255),
                "chip_outline": (201, 217, 235),
                "chip_text": (38, 82, 148),
                "eyebrow_bg": (224, 238, 255),
                "eyebrow_outline": (174, 201, 235),
                "eyebrow_text": (35, 83, 149),
                "line": (68, 116, 188),
                "accent": (34, 104, 226),
                "glow": (126, 180, 255),
            }
        if diagram_type == "process_explainer_infographic":
            return {
                "background": (239, 249, 245),
                "background_alt": (214, 235, 226),
                "surface": (249, 255, 251),
                "surface_alt": (232, 245, 239),
                "node_a": (255, 255, 255),
                "node_b": (234, 247, 240),
                "node_c": (226, 241, 252),
                "card": (255, 255, 255),
                "title": (16, 56, 45),
                "text": (67, 93, 85),
                "border": (185, 214, 200),
                "card_outline": (185, 214, 200),
                "core_card": (242, 250, 245),
                "core_outline": (181, 211, 195),
                "chip_bg": (241, 249, 244),
                "chip_outline": (199, 220, 208),
                "chip_text": (49, 102, 82),
                "eyebrow_bg": (220, 242, 231),
                "eyebrow_outline": (175, 212, 192),
                "eyebrow_text": (35, 106, 80),
                "line": (36, 124, 90),
                "accent": (0, 118, 84),
                "glow": (82, 189, 141),
            }
        if diagram_type == "comparison_card":
            return {
                "background": (248, 244, 238),
                "background_alt": (238, 231, 221),
                "surface": (255, 250, 244),
                "surface_alt": (236, 242, 249),
                "node_a": (255, 248, 239),
                "node_b": (242, 247, 255),
                "node_c": (235, 242, 234),
                "card": (255, 255, 255),
                "title": (38, 27, 19),
                "text": (92, 73, 60),
                "border": (214, 198, 182),
                "card_outline": (214, 198, 182),
                "core_card": (255, 248, 239),
                "core_outline": (210, 185, 163),
                "chip_bg": (255, 250, 244),
                "chip_outline": (220, 205, 190),
                "chip_text": (112, 82, 60),
                "eyebrow_bg": (255, 241, 231),
                "eyebrow_outline": (223, 191, 164),
                "eyebrow_text": (133, 83, 48),
                "line": (118, 94, 81),
                "accent": (182, 73, 37),
                "glow": (226, 150, 118),
            }
        if diagram_type == "workflow_diagram":
            return {
                "background": (244, 251, 247),
                "background_alt": (230, 242, 236),
                "surface": (249, 255, 251),
                "surface_alt": (231, 243, 249),
                "node_a": (255, 255, 255),
                "node_b": (236, 247, 241),
                "node_c": (228, 240, 252),
                "card": (255, 255, 255),
                "title": (17, 56, 44),
                "text": (71, 95, 86),
                "border": (194, 218, 205),
                "card_outline": (194, 218, 205),
                "core_card": (242, 250, 245),
                "core_outline": (182, 211, 195),
                "chip_bg": (241, 249, 244),
                "chip_outline": (199, 220, 207),
                "chip_text": (50, 102, 82),
                "eyebrow_bg": (229, 245, 236),
                "eyebrow_outline": (183, 215, 197),
                "eyebrow_text": (35, 106, 80),
                "line": (48, 129, 93),
                "accent": (3, 120, 87),
                "glow": (86, 191, 144),
            }
        return {
            "background": (244, 247, 252),
            "background_alt": (232, 237, 245),
            "surface": (250, 252, 255),
            "surface_alt": (234, 241, 250),
            "node_a": (255, 255, 255),
            "node_b": (235, 243, 255),
            "node_c": (236, 248, 242),
            "card": (255, 255, 255),
            "title": (24, 41, 68),
            "text": (83, 98, 120),
            "border": (200, 213, 230),
            "card_outline": (200, 213, 230),
            "core_card": (240, 246, 255),
            "core_outline": (164, 190, 226),
            "chip_bg": (243, 248, 255),
            "chip_outline": (204, 218, 234),
            "chip_text": (46, 84, 142),
            "eyebrow_bg": (232, 241, 255),
            "eyebrow_outline": (184, 205, 233),
            "eyebrow_text": (35, 84, 149),
            "line": (76, 116, 170),
            "accent": (39, 108, 228),
            "glow": (135, 180, 255),
        }

    @staticmethod
    @lru_cache(maxsize=32)
    def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        ordered = ProgrammaticVisualService._font_candidates(bold=bold)
        for path in ordered:
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _font_candidates(*, bold: bool) -> list[str]:
        bundled_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
        candidates = [
            bundled_dir / ("NotoSansSC-Bold.otf" if bold else "NotoSansSC-Regular.otf"),
            bundled_dir / ("NotoSansCJKsc-Bold.otf" if bold else "NotoSansCJKsc-Regular.otf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        normalized: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            value = str(candidate)
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        if bold:
            normalized = sorted(normalized, key=lambda path: 0 if ("Bold" in path or "bd" in path.lower()) else 1)
        return normalized
