from __future__ import annotations

from typing import Any

from app.policies.base_policy import BasePolicy, SectionRoleTemplate, SubtypeProfile


class NewsPolicy(BasePolicy):
    pool = "news"
    label = "AI News"
    title_preferences = ("subject + event + impact", "preserve strong original titles", "avoid template phrasing")
    visual_preferences = ("news_photo", "comparison_infographic")
    subtype_profiles = {
        "breaking_news": SubtypeProfile(
            subtype="breaking_news",
            label="Breaking News",
            default_audience="ai_product_manager",
            title_mode="news_breaking",
            visual_mode="news_photo",
            layout_name="news_feature",
            is_news=True,
        ),
        "industry_news": SubtypeProfile(
            subtype="industry_news",
            label="Industry News",
            default_audience="ai_product_manager",
            title_mode="news_analysis",
            visual_mode="news_analysis",
            layout_name="editorial_analysis",
            is_news=True,
        ),
        "capital_signal": SubtypeProfile(
            subtype="capital_signal",
            label="Capital Signal",
            default_audience="ai_product_manager",
            title_mode="news_capital",
            visual_mode="news_photo",
            layout_name="news_feature",
            is_news=True,
        ),
        "controversy_risk": SubtypeProfile(
            subtype="controversy_risk",
            label="Controversy Risk",
            default_audience="ai_product_manager",
            title_mode="news_risk",
            visual_mode="news_analysis",
            layout_name="news_feature",
            is_news=True,
        ),
    }
    default_subtype = "industry_news"
    banned_heading_phrases = (
        "发生了什么",
        "真正重要的变化",
        "对谁有影响",
        "对产品经理的影响",
        "现在该关注什么",
    )

    def section_templates(self, fact_pack: dict[str, Any]) -> list[SectionRoleTemplate]:
        return [
            SectionRoleTemplate(
                role="event_frame",
                goal="Explain the core event and the primary conflict.",
                default_heading="Event frame",
                must_cover=("who", "what happened", "why it matters now"),
                must_avoid=("career advice",),
            ),
            SectionRoleTemplate(
                role="change_focus",
                goal="Surface the most important change behind the news.",
                default_heading="What changed",
                must_cover=("key change", "trigger", "evidence"),
                must_avoid=("generic summary",),
            ),
            SectionRoleTemplate(
                role="meaning_or_risk",
                goal="Explain the broader meaning, risk, or externality of the event.",
                default_heading="Why it matters",
                must_cover=("meaning", "risk", "signal"),
                must_avoid=("product manager advice",),
            ),
            SectionRoleTemplate(
                role="watch_signals",
                goal="Show what to watch next and which signals may confirm the trend.",
                default_heading="What to watch next",
                must_cover=("watch items", "next signals"),
                must_avoid=("empty outlook",),
            ),
        ]

    def subtype(self, *, topic: dict[str, Any], fact_pack: dict[str, Any]) -> str:
        text = " ".join(
            [
                str(topic.get("title", "") or ""),
                str(topic.get("summary", "") or ""),
                " ".join(str(item).strip() for item in (fact_pack.get("key_points") or [])[:5]),
            ]
        ).lower()
        if any(token in text for token in ("ipo", "funding", "capital", "valuation", "loan", "betting billions")):
            return "capital_signal"
        if any(token in text for token in ("attack", "controversy", "backlash", "new yorker", "trust", "safety")):
            return "controversy_risk"
        if any(token in text for token in ("breaking", "announced", "launch", "launches", "introduces", "unveils", "发布", "上线", "更新")):
            return "breaking_news"
        return "industry_news"
