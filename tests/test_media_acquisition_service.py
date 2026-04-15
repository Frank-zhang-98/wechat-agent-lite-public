import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.media_acquisition_service import MediaAcquisitionService


class _FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "image/png") -> None:
        self.content = payload
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


class MediaAcquisitionServiceTests(unittest.TestCase):
    def test_acquire_only_processes_crawl_items(self) -> None:
        service = MediaAcquisitionService()
        png = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x17\x9b"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        blueprint = {
            "items": [
                {
                    "placement_key": "section_1",
                    "anchor_heading": "事件脉络",
                    "section_role": "event_frame",
                    "purpose": "news_photo",
                    "placement": "after_section",
                    "mode": "crawl",
                    "visual_goal": "提供事件现场参考",
                    "visual_claim": "现场人物与事件相关",
                    "brief": {"type": "news_photo", "title": "Need source image", "caption": "现场图"},
                    "constraints": {
                        "candidate_image_urls": ["https://example.com/hero.png"],
                        "candidate_metadata": [
                            {
                                "url": "https://example.com/hero.png",
                                "source_page": "https://news.example.com/post",
                                "origin_type": "official",
                                "query_source": "official",
                                "image_kind": "photo",
                                "provenance_score": 88,
                                "relevance_features": {"tokens": ["event"]},
                            }
                        ],
                    },
                },
                {
                    "placement_key": "section_2",
                    "section_role": "how_it_works",
                    "purpose": "architecture_diagram",
                    "placement": "after_section",
                    "mode": "generate",
                    "brief": {"title": "Need generated diagram"},
                    "constraints": {},
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            with patch("app.services.media_acquisition_service.CONFIG", config):
                with patch("app.services.media_acquisition_service.requests.get", return_value=_FakeResponse(png)):
                    assets = service.acquire(run_id="run-media", visual_blueprint=blueprint)

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["mode"], "crawl")
        self.assertEqual(assets[0]["status"], "acquired")
        self.assertTrue(str(assets[0]["path"]).endswith(".png"))
        self.assertEqual(assets[0]["anchor_heading"], "事件脉络")
        self.assertEqual(assets[0]["type"], "news_photo")
        self.assertEqual(assets[0]["origin_type"], "official")

    def test_acquire_returns_failed_result_for_required_news_crawl_item(self) -> None:
        service = MediaAcquisitionService()
        blueprint = {
            "items": [
                {
                    "placement_key": "section_1",
                    "anchor_heading": "事件脉络",
                    "section_role": "event_frame",
                    "purpose": "news_photo",
                    "placement": "after_section",
                    "mode": "crawl",
                    "required": True,
                    "visual_goal": "提供事件现场参考",
                    "visual_claim": "现场人物与事件相关",
                    "brief": {"type": "news_photo", "title": "Need source image", "caption": "现场图"},
                    "constraints": {"candidate_image_urls": ["https://example.com/hero.png"]},
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            with patch("app.services.media_acquisition_service.CONFIG", config):
                with patch("app.services.media_acquisition_service.requests.get", side_effect=RuntimeError("network down")):
                    assets = service.acquire(run_id="run-media", visual_blueprint=blueprint)

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["mode"], "crawl")
        self.assertEqual(assets[0]["status"], "failed")
        self.assertEqual(assets[0]["placement_key"], "section_1")
        self.assertEqual(assets[0]["anchor_heading"], "事件脉络")
        self.assertTrue(assets[0]["errors"])


if __name__ == "__main__":
    unittest.main()
