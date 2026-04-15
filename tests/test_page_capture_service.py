import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.page_capture_service import PageCaptureService


class PageCaptureServiceTests(unittest.TestCase):
    def test_capture_returns_captured_asset_when_target_succeeds(self) -> None:
        service = PageCaptureService()
        with tempfile.TemporaryDirectory() as tmpdir:
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            with patch("app.services.page_capture_service.CONFIG", config):
                with patch.object(
                    service,
                    "_capture_url",
                    side_effect=lambda **kwargs: (Path(kwargs["output_path"]).write_bytes(b"png"), {"title": "Demo"})[1],
                ):
                    assets = service.capture(
                        run_id="run-1",
                        visual_blueprint={
                            "items": [
                                {
                                    "placement_key": "section_1",
                                    "anchor_heading": "使用界面",
                                    "section_role": "overview",
                                    "purpose": "product_screenshot",
                                    "mode": "capture",
                                    "brief": {"type": "product_screenshot", "title": "控制台截图", "caption": "产品界面"},
                                    "constraints": {
                                        "capture_targets": [
                                            {"url": "https://agent-runtime.dev/demo", "origin_type": "official", "query_source": "demo"}
                                        ]
                                    },
                                }
                            ]
                        },
                    )

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["status"], "captured")
        self.assertEqual(assets[0]["mode"], "capture")
        self.assertEqual(assets[0]["source_page"], "https://agent-runtime.dev/demo")


if __name__ == "__main__":
    unittest.main()
