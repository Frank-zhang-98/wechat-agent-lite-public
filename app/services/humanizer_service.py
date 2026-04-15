from __future__ import annotations

import re
from statistics import pstdev
from typing import Any


class HumanizerService:
    AI_BUZZWORDS = (
        "此外",
        "至关重要",
        "深入探讨",
        "强调",
        "持久",
        "增强",
        "培养",
        "突出",
        "复杂性",
        "格局",
        "展示",
        "证明",
        "充满活力",
        "赋能",
        "颠覆",
        "革命性",
    )
    FILLER_PHRASES = (
        "值得注意的是",
        "为了实现这一目标",
        "在这个时间点",
        "在这一背景下",
        "某种程度上",
        "从某种意义上说",
        "需要指出的是",
    )
    COLLABORATION_TRACES = (
        "希望这对你有帮助",
        "如果你想让我",
        "请告诉我",
        "当然",
        "你说得对",
        "这是一个很好的问题",
    )
    PROMO_PHRASES = (
        "不仅仅是",
        "不只是",
        "而是",
        "标志着",
        "证明了",
        "象征着",
        "未来看起来光明",
        "激动人心的时代",
        "重要一步",
        "持续追求卓越",
    )
    CONNECTOR_OPENERS = (
        "此外",
        "与此同时",
        "然而",
        "值得注意的是",
        "在这一背景下",
        "为了实现这一目标",
    )
    EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF]")
    NEGATION_CONTRAST_RE = re.compile(r"不(?:仅|只是|只)\s*[^。！？!?]{0,24}?(?:而是|更是)")
    BOLD_LIST_RE = re.compile(r"^\s*[-*]\s+\*\*[^*\n]{1,40}(?:：|:)\*\*", flags=re.MULTILINE)
    CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", flags=re.MULTILINE)
    INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

    def analyze(self, article_markdown: str) -> dict[str, Any]:
        raw_text = str(article_markdown or "")
        text = self._plain_text(raw_text)
        issues: list[dict[str, Any]] = []

        ai_hits = self._phrase_hits(text, self.AI_BUZZWORDS)
        self._maybe_add_issue(
            issues,
            key="ai_buzzwords",
            label="AI 高频词偏多",
            hits=ai_hits,
            severity="medium" if len(ai_hits) >= 3 else "low",
        )
        filler_hits = self._phrase_hits(text, self.FILLER_PHRASES)
        self._maybe_add_issue(
            issues,
            key="filler_phrases",
            label="填充短语偏多",
            hits=filler_hits,
            severity="medium" if len(filler_hits) >= 2 else "low",
        )
        collab_hits = self._phrase_hits(text, self.COLLABORATION_TRACES)
        self._maybe_add_issue(
            issues,
            key="collaboration_trace",
            label="带有助手对话痕迹",
            hits=collab_hits,
            severity="high",
        )
        promo_hits = self._phrase_hits(text, self.PROMO_PHRASES)
        self._maybe_add_issue(
            issues,
            key="promo_language",
            label="意义放大或宣传腔偏重",
            hits=promo_hits,
            severity="high" if len(promo_hits) >= 3 else "medium",
        )

        negation_hits = self.NEGATION_CONTRAST_RE.findall(text)
        self._maybe_add_issue(
            issues,
            key="negation_contrast",
            label="“不仅…而是…”类公式句式偏多",
            hits=negation_hits,
            severity="medium",
        )

        em_dash_count = text.count("——")
        if em_dash_count >= 2:
            issues.append(
                {
                    "key": "dash_overuse",
                    "label": "破折号使用偏多",
                    "count": em_dash_count,
                    "examples": ["——"] * min(em_dash_count, 3),
                    "severity": "low",
                }
            )

        bold_list_count = len(self.BOLD_LIST_RE.findall(raw_text))
        if bold_list_count >= 2:
            issues.append(
                {
                    "key": "bold_list_markers",
                    "label": "粗体标题式列表偏多",
                    "count": bold_list_count,
                    "examples": ["- **小标题：**"] * min(bold_list_count, 3),
                    "severity": "low",
                }
            )

        emoji_hits = self.EMOJI_RE.findall(raw_text)
        self._maybe_add_issue(
            issues,
            key="emoji_markers",
            label="表情符号会放大 AI 排版感",
            hits=emoji_hits,
            severity="low",
        )

        flat_rhythm = self._flat_rhythm_issue(text)
        if flat_rhythm:
            issues.append(flat_rhythm)

        repeated_openers = self._repeated_connector_openers(text)
        if repeated_openers:
            issues.append(repeated_openers)

        dimension_scores = self._dimension_scores(
            ai_hits=ai_hits,
            filler_hits=filler_hits,
            collab_hits=collab_hits,
            promo_hits=promo_hits,
            negation_count=len(negation_hits),
            em_dash_count=em_dash_count,
            bold_list_count=bold_list_count,
            flat_rhythm=bool(flat_rhythm),
            repeated_connector_count=int(repeated_openers.get("count", 0) if repeated_openers else 0),
        )
        total_50 = round(sum(dimension_scores.values()), 2)
        score = round(total_50 * 2, 2)
        issue_keys = {str(item.get("key", "") or "") for item in issues if isinstance(item, dict)}
        blocking_patterns = [
            issue["key"]
            for issue in issues
            if issue["key"] in {"collaboration_trace"} and issue["severity"] == "high"
        ]
        rewrite_required = (
            bool(blocking_patterns)
            or score < 74
            or len(issues) >= 4
            or "promo_language" in issue_keys
            or "filler_phrases" in issue_keys
        )
        return {
            "score": score,
            "score_50": total_50,
            "dimension_scores": dimension_scores,
            "issues": issues,
            "blocking_patterns": blocking_patterns,
            "rewrite_required": rewrite_required,
            "summary": self._summary_text(issues=issues, score=score),
        }

    def preventive_guidance(self, *, pool: str = "", subtype: str = "") -> list[str]:
        normalized_pool = str(pool or "").strip().lower()
        normalized_subtype = str(subtype or "").strip().lower()
        semantic_mode = "generic"
        if normalized_pool == "news":
            semantic_mode = "news"
        elif normalized_pool == "github":
            semantic_mode = "technical" if normalized_subtype in {"code_explainer", "stack_analysis"} else "product"
        elif normalized_subtype == "tutorial":
            semantic_mode = "tutorial"
        elif normalized_subtype == "technical_walkthrough":
            semantic_mode = "technical"
        elif normalized_subtype == "tool_review":
            semantic_mode = "product"
        guidance = [
            "优先用事实、动作和边界来推进文章，不要靠“标志着、证明了、未来看起来光明”这类意义放大句硬抬结论。",
            "少用“值得注意的是、为了实现这一目标、在这一背景下”这类填充短语，能直接说结论就直接说。",
            "避免“这不仅仅是……而是……”这类公式句式；如果要对比，直接把前后差异写清楚。",
            "不要出现助手式客套、提问引导或服务话术，例如“希望这对你有帮助”“如果你想让我继续”。",
            "段落节奏尽量自然，少用重复连接词开头，也不要把所有小节都写成整齐模板。",
        ]
        if semantic_mode in {"news", "product"}:
            guidance.append("新闻和产品判断可以保留，但必须先给事实再下结论，语气保持克制，不要写成宣传文案。")
        elif semantic_mode in {"technical", "tutorial"}:
            guidance.append("技术稿优先解释实现链路、步骤和代码职责，不要用宏大判断替代技术说明。")
        return guidance

    def rewrite_guidance(self, analysis: dict[str, Any]) -> list[str]:
        issue_keys = {str(item.get("key", "") or "") for item in (analysis.get("issues") or []) if isinstance(item, dict)}
        guidance: list[str] = []
        if "ai_buzzwords" in issue_keys:
            guidance.append("删掉“此外、至关重要、格局、展示、证明”这类 AI 高频词，改成更直接的事实或动作。")
        if "filler_phrases" in issue_keys:
            guidance.append("减少“值得注意的是、为了实现这一目标、在这一背景下”这类填充短语。")
        if "negation_contrast" in issue_keys or "promo_language" in issue_keys:
            guidance.append("少用“这不仅仅是…而是…”和夸大意义的判断，优先给具体结论。")
        if "collaboration_trace" in issue_keys:
            guidance.append("删掉助手式客套、提问引导和‘希望这对你有帮助’这类对话痕迹。")
        if "dash_overuse" in issue_keys:
            guidance.append("减少破折号，直接把句子写完整。")
        if "bold_list_markers" in issue_keys:
            guidance.append("少用“粗体小标题 + 冒号”的整齐列表，多用自然段承接。")
        if "flat_rhythm" in issue_keys or "repeated_connector_openers" in issue_keys:
            guidance.append("把句子长短打散，避免连续几句都用同一节奏或同一连接词开头。")
        if "emoji_markers" in issue_keys:
            guidance.append("去掉表情符号，保持技术文章的自然节奏。")
        return guidance or ["把抽象套话换成更具体的事实、动作、边界和判断。"]

    def _plain_text(self, text: str) -> str:
        value = self.CODE_BLOCK_RE.sub("\n", str(text or ""))
        value = self.INLINE_CODE_RE.sub(" ", value)
        value = re.sub(r"^\s{0,3}#{1,6}\s+", "", value, flags=re.MULTILINE)
        value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
        value = re.sub(r"[*_>`~-]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    def _phrase_hits(self, text: str, phrases: tuple[str, ...]) -> list[str]:
        hits: list[str] = []
        for phrase in phrases:
            count = text.count(phrase)
            if count <= 0:
                continue
            hits.extend([phrase] * count)
        return hits

    @staticmethod
    def _maybe_add_issue(
        issues: list[dict[str, Any]],
        *,
        key: str,
        label: str,
        hits: list[str],
        severity: str,
    ) -> None:
        if not hits:
            return
        examples = []
        for item in hits:
            if item not in examples:
                examples.append(item)
            if len(examples) >= 4:
                break
        issues.append(
            {
                "key": key,
                "label": label,
                "count": len(hits),
                "examples": examples,
                "severity": severity,
            }
        )

    def _flat_rhythm_issue(self, text: str) -> dict[str, Any] | None:
        sentences = [item.strip() for item in re.split(r"[。！？!?]+", text) if item.strip()]
        lengths = [len(item) for item in sentences if item]
        if len(lengths) < 4:
            return None
        spread = max(lengths) - min(lengths)
        variance = pstdev(lengths)
        if variance >= 8 or spread >= 24:
            return None
        return {
            "key": "flat_rhythm",
            "label": "句长和节奏过于整齐",
            "count": len(lengths),
            "examples": [f"{value}字" for value in lengths[:4]],
            "severity": "medium",
        }

    def _repeated_connector_openers(self, text: str) -> dict[str, Any] | None:
        sentences = [item.strip() for item in re.split(r"[。！？!?]+", text) if item.strip()]
        if len(sentences) < 4:
            return None
        hits: list[str] = []
        for sentence in sentences:
            for opener in self.CONNECTOR_OPENERS:
                if sentence.startswith(opener):
                    hits.append(opener)
                    break
        if len(hits) < 2:
            return None
        return {
            "key": "repeated_connector_openers",
            "label": "过多用连接词开头",
            "count": len(hits),
            "examples": hits[:4],
            "severity": "low",
        }

    @staticmethod
    def _dimension_scores(
        *,
        ai_hits: list[str],
        filler_hits: list[str],
        collab_hits: list[str],
        promo_hits: list[str],
        negation_count: int,
        em_dash_count: int,
        bold_list_count: int,
        flat_rhythm: bool,
        repeated_connector_count: int,
    ) -> dict[str, float]:
        directness = 10.0 - min(7.0, len(filler_hits) * 1.3 + negation_count * 1.0 + len(promo_hits) * 0.7)
        rhythm = 10.0 - min(6.5, (3.5 if flat_rhythm else 0.0) + repeated_connector_count * 0.9 + em_dash_count * 0.4)
        trust = 10.0 - min(8.0, len(collab_hits) * 2.8 + len(promo_hits) * 0.9)
        realism = 10.0 - min(7.5, max(0, len(ai_hits) - 1) * 0.8 + len(promo_hits) * 1.1 + len(collab_hits) * 0.6)
        concision = 10.0 - min(7.0, len(filler_hits) * 1.1 + bold_list_count * 0.9 + em_dash_count * 0.4)
        return {
            "directness": round(max(1.0, directness), 2),
            "rhythm": round(max(1.0, rhythm), 2),
            "trust": round(max(1.0, trust), 2),
            "realism": round(max(1.0, realism), 2),
            "concision": round(max(1.0, concision), 2),
        }

    @staticmethod
    def _summary_text(*, issues: list[dict[str, Any]], score: float) -> str:
        if not issues:
            return f"humanizer score {score}，未发现明显 AI 痕迹"
        labels = "、".join(str(item.get("label", "") or "") for item in issues[:4] if str(item.get("label", "") or ""))
        return f"humanizer score {score}，主要问题：{labels}"
