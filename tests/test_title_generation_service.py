import unittest

from app.agents.title_agent import TitleAgent
from app.runtime.state_models import ArticleDraft, ArticleIntent
from app.services.title_generation_service import TitleGenerationService
from app.services.wechat_service import WeChatService


class FakeLLMResult:
    def __init__(self, text: str):
        self.text = text


class FakeLLM:
    def __init__(self, text: str):
        self.text = text

    def call(self, run_id: str, step_name: str, role: str, prompt: str, temperature: float = 0.35):
        return FakeLLMResult(self.text)


class TitleGenerationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TitleGenerationService()

    def test_generate_falls_back_when_llm_payload_is_invalid(self) -> None:
        plan = self.service.generate(
            run_id="run-1",
            topic={
                "title": "Anthropic updates Claude Code pricing for OpenClaw usage",
                "summary": "Pricing change for Claude Code users.",
            },
            fact_pack={"primary_pool": "news", "key_points": ["pricing change", "subscriber impact"]},
            fact_compress={"one_sentence_summary": "Pricing rules changed for Claude Code users.", "numbers": []},
            pool="news",
            subtype="industry_news",
            llm=FakeLLM("not-json"),
        )

        self.assertTrue(plan.article_title)
        self.assertTrue(plan.wechat_title)
        self.assertLessEqual(len(plan.wechat_title), self.service.WECHAT_TITLE_MAX_CHARS)
        self.assertEqual(plan.source, "heuristic")

    def test_generate_uses_llm_when_payload_is_valid(self) -> None:
        plan = self.service.generate(
            run_id="run-2",
            topic={
                "title": "Seedance 2.0 API launched",
                "summary": "Volcano Engine opens the video generation API.",
            },
            fact_pack={"primary_pool": "news", "key_points": ["API release", "video generation"]},
            fact_compress={"one_sentence_summary": "Seedance 2.0 API is now available.", "numbers": []},
            pool="news",
            subtype="industry_news",
            llm=FakeLLM(
                '{"article_title":"Seedance 2.0 API 全面开放：火山引擎如何推进视频生成 SOTA","wechat_title":"Seedance 2.0 API 全面开放","reason":"clear"}'
            ),
        )

        self.assertEqual(plan.source, "llm")
        self.assertIn("Seedance 2.0 API", plan.article_title)
        self.assertEqual(plan.wechat_title, "Seedance 2.0 API 全面开放")

    def test_generate_rejects_weak_news_headline_and_uses_fallback(self) -> None:
        plan = self.service.generate(
            run_id="run-3",
            topic={
                "title": "OpenAI launches a safety bug bounty program",
                "summary": "The program covers prompt injection and agent safety issues.",
            },
            fact_pack={"primary_pool": "news", "key_points": ["bug bounty", "safety coverage"]},
            fact_compress={"one_sentence_summary": "OpenAI launched a new safety bug bounty program.", "numbers": []},
            pool="news",
            subtype="breaking_news",
            llm=FakeLLM(
                '{"article_title":"OpenAI：核心能力分析","wechat_title":"OpenAI：核心能力分析","reason":"generic"}'
            ),
        )

        self.assertEqual(plan.source, "heuristic")
        self.assertNotIn("核心能力分析", plan.article_title)

    def test_validate_title_plan_rejects_analysis_style_news_headline(self) -> None:
        validation = self.service.validate_title_plan(
            article_title="Seedance：核心能力分析",
            wechat_title="Seedance：核心能力分析",
            topic={"title": "Seedance 2.0 API 上线"},
            pool="news",
            subtype="industry_news",
        )

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["headline_reject_reason"], "analysis_style_headline")

    def test_validate_title_plan_rejects_broken_surface(self) -> None:
        validation = self.service.validate_title_plan(
            article_title="Seedance 2.0 A PI 上线",
            wechat_title="Seedance 2.0 A PI 上线",
            topic={"title": "Seedance 2.0 API 上线"},
            pool="news",
            subtype="industry_news",
        )

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["surface_reject_reason"], "split_api")

    def test_wechat_title_limit_matches_publish_service_limit(self) -> None:
        self.assertEqual(self.service.WECHAT_TITLE_MAX_CHARS, 64)
        self.assertEqual(self.service.WECHAT_TITLE_MAX_CHARS, WeChatService.TITLE_MAX_CHARS)

    def test_markdown_h1_sync_no_longer_overrides_titles(self) -> None:
        temp_ctx = {
            "article_title": "Seedance 2.0 API 全面开放：火山引擎如何推进视频生成 SOTA",
            "wechat_title": "Seedance 2.0 API 全面开放",
            "selected_topic": {"title": "Seedance 2.0 API 上线"},
            "title_plan": {
                "article_title": "Seedance 2.0 API 全面开放：火山引擎如何推进视频生成 SOTA",
                "wechat_title": "Seedance 2.0 API 全面开放",
                "source": "llm",
            },
        }
        draft = ArticleDraft(article_markdown="# Seedance：核心能力分析", h1_title="Seedance：核心能力分析")
        intent = ArticleIntent(pool="news", subtype="industry_news", core_angle="release", audience="pm")
        support = type("Support", (), {"title_generator": self.service})()

        TitleAgent._sync_titles_from_draft(temp_ctx=temp_ctx, draft=draft, intent=intent, support=support)

        self.assertEqual(temp_ctx["article_title"], "Seedance 2.0 API 全面开放：火山引擎如何推进视频生成 SOTA")
        self.assertEqual(temp_ctx["title_plan"]["source"], "llm")

    def test_polish_title_surface_keeps_all_caps_acronym_attached_to_chinese(self) -> None:
        title = "火山引擎 Seedance 2.0 API 上线：视频生成SOTA模型开放，企业可调用多模态能力"
        polished = self.service._polish_title_surface(title)

        self.assertIn("SOTA", polished)
        self.assertNotIn("S OTA", polished)


if __name__ == "__main__":
    unittest.main()
