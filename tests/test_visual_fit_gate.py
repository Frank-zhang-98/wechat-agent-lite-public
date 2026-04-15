import unittest

from app.services.visual_fit_gate import VisualFitGate


class VisualFitGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = VisualFitGate()

    def test_prepare_blueprint_prefers_qualified_acquire_candidate(self) -> None:
        blueprint = {
            "body_policy": {"max_allowed": 1},
            "items": [
                {
                    "placement_key": "section_1",
                    "anchor_heading": "事件脉络",
                    "section_role": "event_frame",
                    "intent_kind": "reference",
                    "preferred_mode": "acquire",
                    "subject_ref": {"kind": "event", "name": "定价调整"},
                    "visual_goal": "提供事件现场参考",
                    "visual_claim": "定价策略调整",
                    "constraints": {},
                }
            ],
        }
        prepared = self.gate.prepare_blueprint(
            visual_blueprint=blueprint,
            image_candidates=[
                {
                    "url": "https://images.example.com/photo.jpg",
                    "source_page": "https://news.example.com/post",
                    "origin_type": "official",
                    "query_source": "official",
                    "image_kind": "photo",
                    "caption": "事件现场与定价策略调整",
                    "context_snippet": "展示定价策略调整的相关新闻现场。",
                    "score": 32,
                    "provenance_score": 78,
                }
            ],
        )
        item = prepared["items"][0]
        self.assertEqual(item["mode"], "crawl")
        self.assertEqual(item["constraints"]["candidate_image_urls"][0], "https://images.example.com/photo.jpg")

    def test_prepare_blueprint_does_not_auto_switch_to_generate_when_no_candidate(self) -> None:
        blueprint = {
            "body_policy": {"max_allowed": 1},
            "items": [
                {
                    "placement_key": "section_1",
                    "anchor_heading": "架构概览",
                    "section_role": "architecture",
                    "intent_kind": "reference",
                    "preferred_mode": "acquire",
                    "subject_ref": {"kind": "project", "name": "Agent Runtime"},
                    "visual_goal": "先寻找真实参考图",
                    "visual_claim": "如果没有合格图就不要硬转生成",
                    "constraints": {},
                }
            ],
        }
        prepared = self.gate.prepare_blueprint(visual_blueprint=blueprint, image_candidates=[])
        self.assertEqual(prepared["items"][0]["mode"], "crawl")
        self.assertEqual(prepared["items"][0]["constraints"], {})

    def test_prepare_blueprint_allows_logo_for_reference_company_subject(self) -> None:
        blueprint = {
            "body_policy": {"max_allowed": 1},
            "items": [
                {
                    "placement_key": "section_1",
                    "anchor_heading": "公司介绍",
                    "section_role": "overview",
                    "intent_kind": "reference",
                    "preferred_mode": "acquire",
                    "subject_ref": {"kind": "company", "name": "Nextie"},
                    "visual_goal": "建立公司识别",
                    "visual_claim": "用品牌识别帮助读者认知对象",
                    "constraints": {},
                }
            ],
        }
        prepared = self.gate.prepare_blueprint(
            visual_blueprint=blueprint,
            image_candidates=[
                {
                    "url": "https://images.example.com/logo.png",
                    "source_page": "https://nextie.ai",
                    "origin_type": "official",
                    "query_source": "official",
                    "image_kind": "logo",
                    "caption": "Nextie logo",
                    "context_snippet": "Nextie official logo",
                    "score": 12,
                    "provenance_score": 86,
                }
            ],
        )
        self.assertEqual(prepared["items"][0]["constraints"]["candidate_image_urls"][0], "https://images.example.com/logo.png")

    def test_filter_body_assets_rejects_generate_when_not_explanatory(self) -> None:
        accepted, failures = self.gate.filter_body_assets(
            visual_blueprint={"items": [{"placement_key": "section_1", "intent_kind": "reference"}]},
            body_assets=[
                {
                    "placement_key": "section_1",
                    "anchor_heading": "公司介绍",
                    "section_role": "overview",
                    "mode": "generate",
                    "type": "comparison_card",
                    "title": "Loose image",
                    "visual_goal": "解释差异",
                }
            ],
        )
        self.assertEqual(accepted, [])
        self.assertEqual(failures[0]["reason"], "generate_not_allowed")


if __name__ == "__main__":
    unittest.main()
