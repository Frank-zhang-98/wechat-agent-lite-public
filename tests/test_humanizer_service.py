import unittest

from app.services.humanizer_service import HumanizerService


class HumanizerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HumanizerService()

    def test_analyze_flags_formulaic_ai_patterns(self) -> None:
        article = (
            "## 它是什么\n"
            "此外，这不仅仅是一个系统，而是一个至关重要的平台。值得注意的是，它展示了显著价值。\n\n"
            "## 怎么工作\n"
            "与此同时，系统分成三个阶段来执行任务：先抓取，再分析，最后写作。\n\n"
            "## 结论\n"
            "未来看起来光明。希望这对你有帮助。"
        )
        analysis = self.service.analyze(article)
        self.assertTrue(analysis["rewrite_required"])
        self.assertLess(analysis["score"], 74)

    def test_preventive_guidance_uses_pool_and_subtype_only(self) -> None:
        guidance = self.service.preventive_guidance(pool="news", subtype="industry_news")
        self.assertTrue(any("新闻和产品判断" in item for item in guidance))

    def test_technical_guidance_prefers_explanation_over_grandiose_language(self) -> None:
        guidance = self.service.preventive_guidance(pool="github", subtype="code_explainer")
        self.assertTrue(any("技术稿优先解释实现链路" in item for item in guidance))


if __name__ == "__main__":
    unittest.main()
