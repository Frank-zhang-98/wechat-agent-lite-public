from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.config import CONFIG
from app.services.image_utils import detect_image_mime


@dataclass
class RenderedArticle:
    layout_name: str
    layout_label: str
    html: str
    block_count: int
    inserted_illustration_count: int = 0
    render_anchor_failures: list[dict[str, Any]] = None
    description: str = ""
    source: str = "rule"


class ArticleRenderService:
    SUBTYPE_LAYOUT_MAP = {
        "breaking_news": "news_feature",
        "industry_news": "editorial_analysis",
        "capital_signal": "news_feature",
        "controversy_risk": "news_feature",
        "repo_recommendation": "product_review",
        "code_explainer": "practical_tutorial",
        "stack_analysis": "practical_tutorial",
        "collection_repo": "product_review",
        "tutorial": "practical_tutorial",
        "technical_walkthrough": "practical_tutorial",
        "tool_review": "product_review",
    }

    def __init__(self) -> None:
        self.config = self._load_layouts()

    def _load_layouts(self) -> dict[str, Any]:
        path = Path(CONFIG.data_dir).parents[0] / "config" / "article_layouts.yaml"
        if not path.exists():
            path = Path(__file__).resolve().parents[2] / "config" / "article_layouts.yaml"
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def resolve_layout(self, *, pool: str = "", subtype: str = "", explicit_layout: str = "") -> dict[str, Any]:
        layouts = dict(self.config.get("layouts") or {})
        default_layout = str(self.config.get("default_layout", "clean_reading") or "clean_reading")
        if explicit_layout and explicit_layout in layouts:
            name = explicit_layout
            source = "explicit"
        else:
            mapped = str(self.SUBTYPE_LAYOUT_MAP.get(str(subtype or "").strip(), "") or "").strip()
            if mapped and mapped in layouts:
                name = mapped
                source = "subtype_rule"
            elif str(pool or "").strip() == "news" and "news_feature" in layouts:
                name = "news_feature"
                source = "pool_rule"
            else:
                if default_layout in layouts:
                    name = default_layout
                    source = "default"
                elif layouts:
                    name = next(iter(layouts))
                    source = "fallback"
                else:
                    name = "clean_reading"
                    source = "fallback"
        layout = dict(layouts.get(name) or {})
        layout["name"] = name
        layout["source"] = source
        layout["label"] = str(layout.get("label", name) or name)
        layout["description"] = str(layout.get("description", "") or "")
        return layout

    def render(
        self,
        markdown_text: str,
        *,
        article_title: str,
        pool: str = "",
        subtype: str = "",
        target_audience: str = "",
        layout_name: str = "",
        illustrations: list[dict[str, Any]] | None = None,
        run_id: str = "",
    ) -> RenderedArticle:
        layout = self.resolve_layout(pool=pool, subtype=subtype, explicit_layout=layout_name)
        blocks = self._parse_blocks(markdown_text=markdown_text, article_title=article_title)
        html_blocks, inserted_illustration_count, render_anchor_failures = self._render_blocks(
            blocks=blocks,
            layout=layout,
            target_audience=target_audience,
            illustrations=illustrations or [],
            run_id=run_id,
        )
        html_output = (
            f'<div style="{self._page_style(layout)}">'
            f'<div style="{self._card_style(layout)}">'
            f'{self._card_accent(layout)}'
            f'{"".join(html_blocks)}'
            f"</div>"
            f"</div>"
        )
        return RenderedArticle(
            layout_name=layout["name"],
            layout_label=layout["label"],
            html=html_output,
            block_count=len(blocks),
            inserted_illustration_count=inserted_illustration_count,
            render_anchor_failures=render_anchor_failures,
            description=layout["description"],
            source=layout["source"],
        )

    @staticmethod
    def save_html(rendered: RenderedArticle, run_id: str) -> str:
        target = CONFIG.data_dir / "runs" / run_id
        target.mkdir(parents=True, exist_ok=True)
        path = target / "article.html"
        path.write_text(rendered.html, encoding="utf-8")
        return str(path)

    def _parse_blocks(self, *, markdown_text: str, article_title: str) -> list[dict[str, Any]]:
        lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        blocks: list[dict[str, Any]] = []
        i = 0
        first_heading_skipped = False
        while i < len(lines):
            raw = lines[i].rstrip()
            stripped = raw.strip()
            if not stripped:
                i += 1
                continue

            if not first_heading_skipped and stripped.startswith("# "):
                heading_text = stripped[2:].strip()
                if self._normalized_title(heading_text) == self._normalized_title(article_title):
                    first_heading_skipped = True
                    i += 1
                    continue
            first_heading_skipped = True

            if stripped.startswith("```"):
                fence = stripped[:3]
                language = stripped[3:].strip()
                code_lines: list[str] = []
                i += 1
                while i < len(lines):
                    candidate = lines[i].rstrip("\n")
                    if candidate.strip().startswith(fence):
                        break
                    code_lines.append(candidate)
                    i += 1
                blocks.append({"type": "code", "language": language, "text": "\n".join(code_lines).strip("\n")})
                i += 1
                continue

            if stripped in {"---", "***", "___"}:
                blocks.append({"type": "hr"})
                i += 1
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                level = min(6, len(heading_match.group(1)))
                blocks.append({"type": f"h{level}", "text": heading_match.group(2).strip()})
                i += 1
                continue

            if stripped.startswith(">"):
                quote_lines: list[str] = []
                while i < len(lines) and lines[i].strip().startswith(">"):
                    quote_lines.append(lines[i].strip()[1:].lstrip())
                    i += 1
                callout_type = ""
                if quote_lines and re.match(r"^\[![A-Za-z]+\]", quote_lines[0]):
                    marker = quote_lines.pop(0)
                    callout_type = marker[3:].strip("]!").lower()
                quote_text = "\n".join(line for line in quote_lines if line).strip()
                blocks.append({"type": "callout" if callout_type else "blockquote", "callout_type": callout_type or "", "text": quote_text})
                continue

            if self._looks_like_table(lines, i):
                header = self._split_table_row(lines[i])
                i += 2  # skip separator
                rows: list[list[str]] = []
                while i < len(lines):
                    candidate = lines[i].strip()
                    if not candidate or "|" not in candidate:
                        break
                    rows.append(self._split_table_row(lines[i]))
                    i += 1
                blocks.append({"type": "table", "header": header, "rows": rows})
                continue

            if re.match(r"^[-*]\s+", stripped):
                items: list[str] = []
                while i < len(lines):
                    candidate = lines[i].strip()
                    if not re.match(r"^[-*]\s+", candidate):
                        break
                    items.append(re.sub(r"^[-*]\s+", "", candidate).strip())
                    i += 1
                blocks.append({"type": "ul", "items": items})
                continue

            if re.match(r"^\d+\.\s+", stripped):
                items = []
                while i < len(lines):
                    candidate = lines[i].strip()
                    if not re.match(r"^\d+\.\s+", candidate):
                        break
                    items.append(re.sub(r"^\d+\.\s+", "", candidate).strip())
                    i += 1
                blocks.append({"type": "ol", "items": items})
                continue

            paragraph_lines = [stripped]
            i += 1
            while i < len(lines):
                candidate = lines[i].strip()
                if not candidate:
                    break
                if self._starts_new_block(candidate, lines, i):
                    break
                paragraph_lines.append(candidate)
                i += 1
            blocks.append({"type": "p", "text": " ".join(paragraph_lines).strip()})

        return blocks

    def _render_blocks(
        self,
        *,
        blocks: list[dict[str, Any]],
        layout: dict[str, Any],
        target_audience: str,
        illustrations: list[dict[str, Any]],
        run_id: str,
    ) -> tuple[list[str], int, list[dict[str, Any]]]:
        rendered: list[str] = []
        pending = [item for item in illustrations if isinstance(item, dict)]
        inserted_indexes: set[int] = set()
        inserted_count = 0
        block_plan, anchor_failures = self._plan_illustration_sections(blocks=blocks, illustrations=pending)

        lede_used = False
        for block_idx, block in enumerate(blocks):
            block_type = block["type"]
            if block_type == "p" and not lede_used and layout.get("use_lede", False):
                rendered.append(f'<p style="{self._lede_style(layout)}">{self._inline(block["text"], layout)}</p>')
                lede_used = True
            elif block_type == "p":
                rendered.append(f'<p style="{self._paragraph_style(layout)}">{self._inline(block["text"], layout)}</p>')
            elif block_type in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                level = int(block_type[1])
                rendered.append(f'<{block_type} style="{self._heading_style(layout, level)}">{self._inline(block["text"], layout)}</{block_type}>')
            elif block_type == "blockquote":
                rendered.append(f'<blockquote style="{self._quote_style(layout)}">{self._inline(block["text"], layout)}</blockquote>')
            elif block_type == "callout":
                rendered.append(
                    f'<div style="{self._callout_style(layout, block.get("callout_type", ""))}">'
                    f'{self._inline(block["text"], layout)}'
                    f"</div>"
                )
            elif block_type == "ul":
                items = "".join(f'<li style="{self._li_style(layout)}">{self._inline(item, layout)}</li>' for item in block["items"])
                rendered.append(f'<ul style="{self._list_style(layout)}">{items}</ul>')
            elif block_type == "ol":
                items = "".join(f'<li style="{self._li_style(layout)}">{self._inline(item, layout)}</li>' for item in block["items"])
                rendered.append(f'<ol style="{self._list_style(layout)}">{items}</ol>')
            elif block_type == "code":
                rendered.append(self._render_code_block(block=block, layout=layout))
            elif block_type == "table":
                rendered.append(self._render_table(block=block, layout=layout))
            elif block_type == "hr":
                rendered.append(f'<hr style="{self._hr_style(layout)}" />')

            if self._is_illustration_anchor_block(block_type):
                section_indexes = [idx for idx in block_plan.get(block_idx, []) if idx not in inserted_indexes]
                section_illustrations = [pending[idx] for idx in section_indexes]
                if not section_illustrations:
                    continue
                illustration_blocks, rendered_group_count = self._render_illustration_group(
                    items=section_illustrations,
                    layout=layout,
                    run_id=run_id,
                )
                rendered.extend(illustration_blocks)
                inserted_indexes.update(section_indexes)
                inserted_count += rendered_group_count
        return rendered, inserted_count, anchor_failures

    def _render_code_block(self, *, block: dict[str, Any], layout: dict[str, Any]) -> str:
        language = str(block.get("language", "") or "").strip().lower()
        code_text = str(block.get("text", "") or "")
        lines = code_text.split("\n")
        if not lines:
            lines = [""]
        language_badge = ""
        if language:
            language_badge = (
                f'<div style="margin:0 0 10px;color:{layout["muted_color"]};font-size:11px;line-height:1.2;'
                f'text-transform:uppercase;letter-spacing:0.08em;font-family:Consolas,Monaco,monospace;">'
                f"{html.escape(language)}"
                f"</div>"
            )
        code_html = "<br/>".join(self._render_code_line(line) for line in lines)
        return (
            f'<section style="{self._code_style(layout)}">'
            f"{language_badge}"
            f'<code style="display:block;margin:0;white-space:normal;word-break:break-word;overflow-wrap:anywhere;'
            f'font-family:Consolas,Monaco,monospace;">{code_html}</code>'
            f"</section>"
        )

    @staticmethod
    def _render_code_line(line: str) -> str:
        expanded = str(line or "").replace("\t", "    ")
        match = re.match(r"^( +)", expanded)
        if not expanded:
            return "&nbsp;"
        leading = match.group(1) if match else ""
        body = expanded[len(leading) :]
        prefix = "&nbsp;" * len(leading)
        escaped_body = html.escape(body)
        return f"{prefix}{escaped_body}" if (prefix or escaped_body) else "&nbsp;"

    @staticmethod
    def _clean_illustration_text(value: str) -> str:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(
            r"\b(?:target|title|href|src|alt|class|style|rel|id|width|height|loading|decoding|referrerpolicy|data-[A-Za-z0-9_:-]+)\s*=\s*\"[^\"]*\"?",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?:target|title|href|src|alt|class|style|rel|id|width|height|loading|decoding|referrerpolicy|data-[A-Za-z0-9_:-]+)\s*=\s*'[^']*'?",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?:target|title|href|src|alt|class|style|rel|id|width|height|loading|decoding|referrerpolicy|data-[A-Za-z0-9_:-]+)\s*=\s*[^\s>]+",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"https?://\S+\.(?:png|jpe?g|gif|webp)\S*", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\S+\.(?:png|jpe?g|gif|webp|bmp)\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d{2,4}w\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:credit|credits?)\s*:\s*[^.。!?！？]{0,80}", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:senior editor|editor|reporter|staff writer|gaming editor)\b[^.。!?！？]{0,60}", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _render_illustration(self, *, item: dict[str, Any], layout: dict[str, Any], run_id: str) -> str:
        src = self._resolve_illustration_src(str(item.get("path", "") or "").strip(), run_id=run_id)
        if not src:
            return ""
        illustration_type = str(item.get("type", "") or "").strip().lower()
        intent_kind = str(item.get("intent_kind", "") or "").strip().lower()
        title = html.escape(self._clean_illustration_text(str(item.get("title", "") or "").strip()))
        caption = html.escape(self._clean_illustration_text(str(item.get("caption", "") or "").strip()))
        caption_html = ""
        if title or caption:
            title_html = ""
            if title:
                title_prefix = "" if illustration_type == "news_photo" else "图解："
                title_html = (
                    f'<div style="margin-bottom:4px;color:{layout["heading_color"]};font-size:15px;line-height:1.5;font-weight:700;">'
                    f"{title_prefix}{title}"
                    f"</div>"
                )
            caption_html = (
                f'<figcaption style="margin-top:12px;padding:0 4px;color:{layout["muted_color"]};font-size:13px;line-height:1.75;">'
                f"{title_html}"
                f"{caption}"
                f"</figcaption>"
            )
        return (
            f'<figure style="margin:22px auto 30px;max-width:960px;">'
            f'<img src="{src}" alt="{title or "illustration"}" style="display:block;width:100%;height:auto;border-radius:18px;border:1px solid {layout["border_color"]};background:{layout["card_background"]};box-shadow:0 10px 30px rgba(15,23,42,0.08);" />'
            f"{caption_html}"
            f"</figure>"
        )

    def _render_illustration_group(self, *, items: list[dict[str, Any]], layout: dict[str, Any], run_id: str) -> tuple[list[str], int]:
        rendered: list[str] = []
        inserted_count = 0
        for item in items:
            block = self._render_illustration(item=item, layout=layout, run_id=run_id)
            if block:
                rendered.append(block)
                inserted_count += 1
        return rendered, inserted_count

    def _render_illustration_bridge(self, *, items: list[dict[str, Any]], layout: dict[str, Any]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            text = self._single_illustration_bridge(items[0])
        else:
            text = self._multi_illustration_bridge(items)
        if not text:
            return ""
        return f'<p style="{self._paragraph_style(layout)}margin-top:8px;">{text}</p>'

    def _single_illustration_bridge(self, item: dict[str, Any]) -> str:
        illustration_type = str(item.get("type", "") or "").strip().lower()
        intent_kind = str(item.get("intent_kind", "") or "").strip().lower()
        if illustration_type == "news_photo" or intent_kind == "reference":
            return ""
        goal = self._clean_illustration_text(str(item.get("visual_goal", "") or "").strip())
        claim = self._clean_illustration_text(str(item.get("visual_claim", "") or "").strip())
        anchor = self._clean_illustration_text(str(item.get("anchor_heading", "") or "").strip())
        if not goal:
            return ""
        if claim:
            return f"下面这张图主要帮助你看清“{html.escape(anchor or claim)}”：{html.escape(claim)}。"
        return f"下面这张图主要服务于“{html.escape(anchor or goal)}”这一节，重点是把 {html.escape(goal)} 讲清楚。"

    def _multi_illustration_bridge(self, items: list[dict[str, Any]]) -> str:
        if items and all(str(item.get("type", "") or "").strip().lower() == "news_photo" for item in items):
            return ""
        focuses = [
            self._clean_illustration_text(str(item.get("visual_goal", "") or item.get("visual_claim", "") or "").strip())
            for item in items
            if str(item.get("visual_goal", "") or item.get("visual_claim", "") or "").strip()
        ]
        if len(focuses) >= 2:
            pair = "、".join(html.escape(text) for text in focuses[:2])
            return f"这一节里最值得配合图来看的是：{pair}。顺着下面几张图往下看，会更容易把关系串起来。"
        return ""

    @staticmethod
    def _bridge_focus_text(item: dict[str, Any]) -> str:
        for key in ("visual_goal", "visual_claim", "anchor_heading", "title", "section", "caption"):
            value = str(item.get(key, "") or "").strip()
            if value:
                cleaned = ArticleRenderService._clean_illustration_text(value)
                if "：" in cleaned and re.search(r"(对比|差异|vs|VS)\s*$", cleaned, flags=re.IGNORECASE):
                    cleaned = cleaned.split("：", 1)[0].strip()
                cleaned = re.sub(r"\s*(对比|差异|图解|示意图|结构图|流程图)\s*$", "", cleaned, flags=re.IGNORECASE)
                cleaned = cleaned.replace(" 与 ", "与")
                return cleaned[:22] if len(cleaned) > 22 else cleaned
        return "这部分内容"

    @staticmethod
    def _stable_variant_index(text: str, count: int) -> int:
        if count <= 0:
            return 0
        total = sum(ord(ch) for ch in str(text or ""))
        return total % count

    @staticmethod
    def _is_illustration_anchor_block(block_type: str) -> bool:
        return block_type in {"p", "ul", "ol", "blockquote", "callout", "table", "code"}

    def _plan_illustration_sections(
        self,
        *,
        blocks: list[dict[str, Any]],
        illustrations: list[dict[str, Any]],
    ) -> tuple[dict[int, list[int]], list[dict[str, Any]]]:
        sections = self._build_sections(blocks)
        section_assignments: dict[int, list[int]] = {}
        block_plan: dict[int, list[int]] = {}
        failures: list[dict[str, Any]] = []
        for idx, item in enumerate(illustrations):
            explicit_match = self._match_anchor_heading(item=item, sections=sections)
            if explicit_match is not None:
                section_assignments.setdefault(int(explicit_match), []).append(idx)
                continue
            best_heading_idx = None
            best_score = 0
            for section in sections:
                score = self._score_illustration_to_section(item=item, section=section)
                if score > best_score:
                    best_score = score
                    best_heading_idx = section.get("heading_idx")
            if best_heading_idx is None or best_score < 18:
                failures.append(
                    {
                        "placement_key": str(item.get("placement_key", "") or "").strip(),
                        "anchor_heading": str(item.get("anchor_heading", "") or "").strip(),
                        "section_role": str(item.get("section_role", "") or "").strip(),
                        "reason": "anchor_not_found",
                    }
                )
                continue
            section_assignments.setdefault(int(best_heading_idx), []).append(idx)

        sections_by_heading = {
            int(section.get("heading_idx", 0) or 0): section for section in sections if section.get("heading_idx") is not None
        }
        for heading_idx, illustration_indexes in section_assignments.items():
            section = sections_by_heading.get(int(heading_idx))
            if not section:
                for idx in illustration_indexes:
                    item = illustrations[idx]
                    failures.append(
                        {
                            "placement_key": str(item.get("placement_key", "") or "").strip(),
                            "anchor_heading": str(item.get("anchor_heading", "") or "").strip(),
                            "section_role": str(item.get("section_role", "") or "").strip(),
                            "reason": "section_missing",
                        }
                    )
                continue
            anchor_slots = list(section.get("anchor_blocks") or [])
            slot_indexes = self._distribute_illustrations_to_anchor_slots(
                slot_count=len(anchor_slots),
                illustration_count=len(illustration_indexes),
            )
            for position, slot_idx in enumerate(slot_indexes):
                illustration_idx = illustration_indexes[position]
                block_idx = anchor_slots[slot_idx]
                block_plan.setdefault(int(block_idx), []).append(int(illustration_idx))
            if len(slot_indexes) < len(illustration_indexes):
                for illustration_idx in illustration_indexes[len(slot_indexes) :]:
                    item = illustrations[illustration_idx]
                    failures.append(
                        {
                            "placement_key": str(item.get("placement_key", "") or "").strip(),
                            "anchor_heading": str(item.get("anchor_heading", "") or "").strip(),
                            "section_role": str(item.get("section_role", "") or "").strip(),
                            "reason": "no_non_adjacent_slot",
                        }
                    )
        return block_plan, failures

    def _build_sections(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for idx, block in enumerate(blocks):
            if block.get("type") in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                if current:
                    sections.append(current)
                heading_text = str(block.get("text", "") or "").strip()
                heading_norm = self._normalized_title(heading_text)
                current = {
                    "heading_idx": idx,
                    "heading_text": heading_text,
                    "section_role": self._section_role_from_heading_text(heading_text),
                    "search_text": heading_text,
                    "section_id": f"{block.get('type', 'h')}-{idx}-{heading_norm or 'section'}",
                    "anchor_blocks": [],
                }
                continue
            if not current:
                continue
            block_text = self._block_search_text(block)
            if block_text:
                current["search_text"] = f"{current['search_text']} {block_text}".strip()
            if self._is_illustration_anchor_block(str(block.get("type", "") or "")):
                current.setdefault("anchor_blocks", []).append(idx)
        if current:
            sections.append(current)
        return sections

    @staticmethod
    def _distribute_illustrations_to_anchor_slots(*, slot_count: int, illustration_count: int) -> list[int]:
        if slot_count <= 0 or illustration_count <= 0:
            return []
        if illustration_count == 1:
            return [slot_count // 2]
        usable = min(slot_count, illustration_count)
        if usable == 1:
            return [slot_count // 2]
        positions: list[int] = []
        for order in range(usable):
            raw = round(order * (slot_count - 1) / max(usable - 1, 1))
            if positions and raw <= positions[-1]:
                raw = min(slot_count - 1, positions[-1] + 1)
            positions.append(raw)
        return positions

    def _match_anchor_heading(self, *, item: dict[str, Any], sections: list[dict[str, Any]]) -> int | None:
        anchor_heading = self._normalized_title(str(item.get("anchor_heading", "") or ""))
        section_role = str(item.get("section_role", "") or "").strip().lower()
        subject_name = self._normalized_title(str((item.get("subject_ref") or {}).get("name", "") or ""))
        if anchor_heading:
            for section in sections:
                heading_norm = self._normalized_title(str(section.get("heading_text", "") or ""))
                if heading_norm and heading_norm == anchor_heading:
                    return int(section.get("heading_idx", 0) or 0)
            for section in sections:
                heading_norm = self._normalized_title(str(section.get("heading_text", "") or ""))
                if heading_norm and (anchor_heading in heading_norm or heading_norm in anchor_heading):
                    return int(section.get("heading_idx", 0) or 0)
        if section_role:
            for section in sections:
                if str(section.get("section_role", "") or "").strip().lower() == section_role:
                    return int(section.get("heading_idx", 0) or 0)
        if subject_name:
            for section in sections:
                search_norm = self._normalized_title(str(section.get("search_text", "") or ""))
                if search_norm and subject_name in search_norm:
                    return int(section.get("heading_idx", 0) or 0)
        return None

    def _score_illustration_to_section(self, *, item: dict[str, Any], section: dict[str, Any]) -> int:
        heading_text = str(section.get("heading_text", "") or "")
        search_text = str(section.get("search_text", "") or "")
        heading_norm = self._normalized_title(heading_text)
        section_norm = self._normalized_title(str(item.get("anchor_heading", "") or item.get("section", "") or ""))
        title_norm = self._normalized_title(str(item.get("title", "") or ""))
        caption_norm = self._normalized_title(str(item.get("caption", "") or ""))
        subject_norm = self._normalized_title(str((item.get("subject_ref") or {}).get("name", "") or ""))
        intent_kind = str(item.get("intent_kind", "") or "").strip().lower()
        score = 0
        for candidate in (section_norm, subject_norm, title_norm):
            if candidate and heading_norm:
                if candidate == heading_norm:
                    score += 120
                elif len(candidate) >= 4 and (candidate in heading_norm or heading_norm in candidate):
                    score += 72
        search_norm = self._normalized_title(search_text)
        for candidate in (section_norm, subject_norm, title_norm, caption_norm):
            if candidate and search_norm and candidate in search_norm:
                score += 38
        item_tokens = self._match_tokens(
            " ".join(
                [
                    str(item.get("anchor_heading", "") or item.get("section", "") or ""),
                    str((item.get("subject_ref") or {}).get("name", "") or ""),
                    str(item.get("title", "") or ""),
                    str(item.get("caption", "") or ""),
                    str(item.get("visual_goal", "") or ""),
                    str(item.get("visual_claim", "") or ""),
                ]
            )
        )
        section_tokens = self._match_tokens(search_text)
        score += len(item_tokens & section_tokens) * 8
        if intent_kind == "reference" and subject_norm and subject_norm in search_norm:
            score += 28
        return score

    @staticmethod
    def _section_role_from_heading_text(heading: str) -> str:
        value = str(heading or "").strip().lower()
        if not value:
            return "overview"
        if any(token in value for token in ("event", "what changed", "事件", "脉络")):
            return "event_frame"
        if any(token in value for token in ("impact", "meaning", "影响", "意义")):
            return "impact"
        if any(token in value for token in ("risk", "watch", "观察", "风险")):
            return "watch_signals"
        if any(token in value for token in ("capital", "融资", "估值")):
            return "capital_signal"
        if any(token in value for token in ("overview", "概览", "背景")):
            return "overview"
        if any(token in value for token in ("architecture", "架构", "模块", "分层")):
            return "architecture"
        if any(token in value for token in ("workflow", "pipeline", "process", "流程", "步骤")):
            return "workflow"
        return "overview"

    @staticmethod
    def _block_search_text(block: dict[str, Any]) -> str:
        block_type = str(block.get("type", "") or "")
        if block_type in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "callout"}:
            return str(block.get("text", "") or "").strip()
        if block_type in {"ul", "ol"}:
            return " ".join(str(item).strip() for item in (block.get("items") or []) if str(item).strip())
        if block_type == "table":
            values = list(block.get("header") or [])
            for row in (block.get("rows") or []):
                values.extend(row)
            return " ".join(str(item).strip() for item in values if str(item).strip())
        if block_type == "code":
            return str(block.get("text", "") or "")[:300]
        return ""

    @staticmethod
    def _match_tokens(text: str) -> set[str]:
        stopwords = {
            "图解", "这一节", "这一部分", "关键", "结构", "流程", "系统", "模块", "说明", "建议",
            "实现", "完整", "链路", "部分", "用于", "相关", "统一", "技术", "方案",
        }
        tokens = re.findall(r"[A-Za-z0-9@._/-]{2,}|[\u4e00-\u9fff]{2,8}", str(text or ""))
        return {token.lower() for token in tokens if token.lower() not in stopwords}

    @staticmethod
    def _resolve_illustration_src(path: str, *, run_id: str = "") -> str:
        raw = str(path or "").strip().replace("\\", "/")
        if not raw:
            return ""
        if raw.startswith("data:image/") or raw.startswith("http://") or raw.startswith("https://"):
            return raw
        candidate = Path(raw)
        if not candidate.exists() or not candidate.is_file():
            return raw
        asset_url = ArticleRenderService._resolve_run_asset_url(candidate=candidate, raw=raw, run_id=run_id)
        if asset_url:
            return asset_url
        payload = candidate.read_bytes()
        mime_type = detect_image_mime(payload, fallback=(mimetypes.guess_type(candidate.name)[0] or "image/png"))
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _resolve_run_asset_url(*, candidate: Path, raw: str, run_id: str) -> str:
        runs_dir = (CONFIG.data_dir / "runs").resolve()
        normalized = str(raw or "").replace("\\", "/").strip()
        if run_id:
            expected_root = (runs_dir / run_id).resolve()
            try:
                relative = candidate.resolve().relative_to(expected_root)
                return f"/api/runs/{run_id}/assets/{relative.as_posix()}"
            except Exception:
                pass
        marker = "data/runs/"
        if marker in normalized:
            tail = normalized.split(marker, 1)[1]
            parts = [part for part in tail.split("/") if part]
            if len(parts) >= 2:
                return f"/api/runs/{parts[0]}/assets/{'/'.join(parts[1:])}"
        try:
            relative = candidate.resolve().relative_to(runs_dir)
            parts = list(relative.parts)
            if len(parts) >= 2:
                return f"/api/runs/{parts[0]}/assets/{Path(*parts[1:]).as_posix()}"
        except Exception:
            return ""
        return ""

    def _render_table(self, *, block: dict[str, Any], layout: dict[str, Any]) -> str:
        header_cells = "".join(
            f'<th style="{self._th_style(layout)}">{self._inline(cell, layout)}</th>' for cell in block.get("header", [])
        )
        row_html = []
        for row_idx, row in enumerate(block.get("rows", [])):
            cells = "".join(f'<td style="{self._td_style(layout)}">{self._inline(cell, layout)}</td>' for cell in row)
            row_html.append(f'<tr style="{self._table_row_style(layout, row_idx)}">{cells}</tr>')
        return (
            f'<div style="{self._table_wrap_style(layout)}">'
            f'<table style="{self._table_style(layout)}">'
            f"<thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{''.join(row_html)}</tbody>"
            f"</table>"
            f"</div>"
        )

    @staticmethod
    def _normalized_title(value: str) -> str:
        return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").lower())

    @staticmethod
    def _starts_new_block(candidate: str, lines: list[str], index: int) -> bool:
        if candidate.startswith(("# ", "## ", "### ", "```", ">")):
            return True
        if candidate in {"---", "***", "___"}:
            return True
        if re.match(r"^[-*]\s+", candidate):
            return True
        if re.match(r"^\d+\.\s+", candidate):
            return True
        return ArticleRenderService._looks_like_table(lines, index)

    @staticmethod
    def _looks_like_table(lines: list[str], index: int) -> bool:
        if index + 1 >= len(lines):
            return False
        current = lines[index].strip()
        next_line = lines[index + 1].strip()
        if "|" not in current or "|" not in next_line:
            return False
        return bool(re.match(r"^\|?[\s:-]+\|[\s|:-]*$", next_line))

    @staticmethod
    def _split_table_row(line: str) -> list[str]:
        text = line.strip().strip("|")
        return [cell.strip() for cell in text.split("|")]

    def _inline(self, value: str, layout: dict[str, Any]) -> str:
        tokens: list[str] = []

        def store_token(text: str) -> str:
            tokens.append(text)
            return f"__TOKEN_{len(tokens) - 1}__"

        text = str(value or "")
        text = re.sub(
            r"`([^`]+)`",
            lambda match: store_token(
                f'<code style="background:rgba(15,23,42,0.06);padding:2px 6px;border-radius:6px;color:{layout["heading_color"]};font-family:Consolas,Monaco,monospace;font-size:0.92em;">{html.escape(match.group(1))}</code>'
            ),
            text,
        )
        text = re.sub(
            r"\[([^\]]+)\]\((https?://[^)]+)\)",
            lambda match: store_token(
                f'<a href="{html.escape(match.group(2), quote=True)}" style="color:{layout["accent_color"]};text-decoration:none;border-bottom:1px solid {layout["accent_color"]};">{html.escape(match.group(1))}</a>'
            ),
            text,
        )
        text = html.escape(text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)

        for idx, token in enumerate(tokens):
            text = text.replace(f"__TOKEN_{idx}__", token)
        return text

    @staticmethod
    def _page_style(layout: dict[str, Any]) -> str:
        padding = str(layout.get("page_padding", "32px 18px 42px") or "32px 18px 42px")
        return (
            f"margin:0;padding:{padding};background:{layout['page_background']};"
            f"font-family:{layout['font_family']};color:{layout['text_color']};"
        )

    @staticmethod
    def _card_style(layout: dict[str, Any]) -> str:
        radius = str(layout.get("card_radius", "30px") or "30px")
        padding = str(layout.get("card_padding", "38px 34px 40px") or "38px 34px 40px")
        shadow = str(layout.get("card_shadow", "0 22px 60px rgba(15,23,42,0.10)") or "0 22px 60px rgba(15,23,42,0.10)")
        return (
            f"max-width:{layout['max_width']};margin:0 auto;background:{layout['card_background']};"
            f"border:1px solid {layout['border_color']};border-radius:{radius};padding:{padding};"
            f"box-shadow:{shadow};box-sizing:border-box;"
        )

    @staticmethod
    def _lede_style(layout: dict[str, Any]) -> str:
        font_size = str(layout.get("lede_size", "20px") or "20px")
        return (
            f"margin:0 0 24px;color:{layout['heading_color']};font-size:{font_size};line-height:1.95;"
            f"font-weight:500;letter-spacing:0.01em;"
        )

    @staticmethod
    def _paragraph_style(layout: dict[str, Any]) -> str:
        font_size = str(layout.get("paragraph_size", "16px") or "16px")
        spacing = str(layout.get("paragraph_spacing", "18px") or "18px")
        return (
            f"margin:0 0 {spacing};color:{layout['text_color']};font-size:{font_size};line-height:2;"
            f"letter-spacing:0.01em;"
        )

    @staticmethod
    def _heading_style(layout: dict[str, Any], level: int) -> str:
        size_map = {1: "34px", 2: "25px", 3: "20px", 4: "18px", 5: "16px", 6: "15px"}
        margin_map = {1: "0 0 18px", 2: "40px 0 16px", 3: "28px 0 14px", 4: "22px 0 12px", 5: "18px 0 10px", 6: "16px 0 8px"}
        weight_map = {1: "800", 2: "750", 3: "700", 4: "680", 5: "650", 6: "630"}
        border = f"padding-bottom:10px;border-bottom:1px solid {layout['border_color']};" if level == 2 else ""
        return (
            f"margin:{margin_map[level]};color:{layout['heading_color']};font-size:{size_map[level]};"
            f"line-height:1.35;font-weight:{weight_map[level]};font-family:{layout['heading_font_family']};"
            f"letter-spacing:-0.02em;{border}"
        )

    @staticmethod
    def _quote_style(layout: dict[str, Any]) -> str:
        return (
            f"margin:22px 0;padding:16px 18px;background:{layout['quote_background']};"
            f"border-left:4px solid {layout['quote_border']};border-radius:0 18px 18px 0;"
            f"color:{layout['text_color']};font-size:15px;line-height:1.95;"
        )

    @staticmethod
    def _callout_style(layout: dict[str, Any], callout_type: str) -> str:
        accent = layout["accent_color"]
        if callout_type in {"warning", "warn"}:
            accent = "#d97706"
        elif callout_type in {"danger", "error"}:
            accent = "#dc2626"
        elif callout_type in {"tip", "success"}:
            accent = "#059669"
        return (
            f"margin:22px 0;padding:16px 18px;background:{layout['quote_background']};"
            f"border:1px solid {accent};border-radius:18px;color:{layout['text_color']};"
            f"box-shadow:0 10px 24px rgba(15,23,42,0.05);font-size:15px;line-height:1.95;"
        )

    @staticmethod
    def _list_style(layout: dict[str, Any]) -> str:
        return (
            f"margin:0 0 20px;padding-left:24px;color:{layout['text_color']};font-size:16px;line-height:2;"
        )

    @staticmethod
    def _li_style(layout: dict[str, Any]) -> str:
        return f"margin:0 0 10px;color:{layout['text_color']};"

    @staticmethod
    def _code_style(layout: dict[str, Any]) -> str:
        return (
            f"margin:22px 0;padding:18px;background:{layout['code_background']};color:{layout['code_color']};"
            f"border-radius:18px;overflow:auto;font-size:13px;line-height:1.8;font-family:Consolas,Monaco,monospace;"
            f"border:1px solid {layout['border_color']};box-sizing:border-box;"
        )

    @staticmethod
    def _hr_style(layout: dict[str, Any]) -> str:
        return f"margin:30px 0;border:none;border-top:1px solid {layout['border_color']};"

    @staticmethod
    def _table_wrap_style(layout: dict[str, Any]) -> str:
        return "margin:22px 0;overflow:auto;border-radius:18px;"

    @staticmethod
    def _table_style(layout: dict[str, Any]) -> str:
        return (
            f"width:100%;border-collapse:collapse;border:1px solid {layout['border_color']};"
            f"border-radius:18px;overflow:hidden;background:{layout['card_background']};"
        )

    @staticmethod
    def _th_style(layout: dict[str, Any]) -> str:
        return (
            f"padding:12px 14px;background:{layout['table_header_background']};color:{layout['heading_color']};"
            f"border-bottom:1px solid {layout['border_color']};font-size:13px;text-align:left;"
            f"text-transform:none;letter-spacing:0.01em;"
        )

    @staticmethod
    def _td_style(layout: dict[str, Any]) -> str:
        return (
            f"padding:12px 14px;color:{layout['text_color']};border-bottom:1px solid {layout['border_color']};"
            f"font-size:14px;line-height:1.85;vertical-align:top;"
        )

    @staticmethod
    def _card_accent(layout: dict[str, Any]) -> str:
        accent = str(layout.get("accent_color", "#2563eb") or "#2563eb")
        quote_border = str(layout.get("quote_border", accent) or accent)
        return (
            '<div style="width:88px;height:4px;border-radius:999px;'
            f'background:linear-gradient(90deg,{accent} 0%, {quote_border} 100%);margin:0 0 24px;"></div>'
        )

    @staticmethod
    def _table_row_style(layout: dict[str, Any], row_idx: int) -> str:
        row_background = layout.get("table_row_background_even" if row_idx % 2 else "table_row_background_odd", "")
        if not row_background:
            return ""
        return f"background:{row_background};"
