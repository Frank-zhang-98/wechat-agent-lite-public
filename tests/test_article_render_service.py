import tempfile
import unittest
from pathlib import Path

from app.services.article_render_service import ArticleRenderService


class ArticleRenderServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ArticleRenderService()

    def test_resolve_layout_prefers_subtype_mapping(self) -> None:
        layout = self.service.resolve_layout(pool="deep_dive", subtype="tutorial")
        self.assertEqual(layout["name"], "practical_tutorial")
        self.assertEqual(layout["source"], "subtype_rule")

    def test_render_skips_duplicate_h1_and_outputs_html(self) -> None:
        rendered = self.service.render(
            "# 测试标题\n\n第一段导语。\n\n## 小节\n- 要点一\n- 要点二",
            article_title="测试标题",
            pool="deep_dive",
            subtype="tutorial",
            target_audience="ai_builder",
        )
        self.assertEqual(rendered.layout_name, "practical_tutorial")
        self.assertIn("<h2", rendered.html)
        self.assertNotIn(">测试标题</h1>", rendered.html)

    def test_render_uses_run_asset_url_for_run_scoped_illustrations(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "run-123" / "illustrations"
            runs_dir.mkdir(parents=True)
            image_path = runs_dir / "news.webp"
            image_path.write_bytes(
                b"RIFF\x1a\x00\x00\x00WEBPVP8 "
                b"\x0e\x00\x00\x00\xd0\x01\x00\x9d\x01*\x01\x00\x01\x00\x01@&%\xa0"
            )
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            with patch("app.services.article_render_service.CONFIG", config):
                rendered = self.service.render(
                    "## 事件脉络\n\n正文段落",
                    article_title="测试",
                    pool="news",
                    subtype="breaking_news",
                    illustrations=[
                        {
                            "type": "news_photo",
                            "anchor_heading": "事件脉络",
                            "section_role": "event_frame",
                            "caption": "说明文字",
                            "path": str(image_path),
                        }
                    ],
                    run_id="run-123",
                )

        self.assertIn("/api/runs/run-123/assets/illustrations/news.webp", rendered.html)
        self.assertEqual(rendered.inserted_illustration_count, rendered.html.count("<figure"))

    def test_render_does_not_count_missing_illustration_path_as_inserted(self) -> None:
        rendered = self.service.render(
            "## 事件脉络\n\n正文段落",
            article_title="测试",
            pool="news",
            subtype="breaking_news",
            illustrations=[
                {
                    "type": "news_photo",
                    "anchor_heading": "事件脉络",
                    "section_role": "event_frame",
                    "caption": "说明文字",
                    "path": "",
                }
            ],
            run_id="run-missing",
        )

        self.assertEqual(rendered.inserted_illustration_count, 0)
        self.assertEqual(rendered.html.count("<figure"), 0)

    def test_render_prefers_anchor_heading_and_does_not_dump_unmatched_illustrations_at_end(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "run-321" / "illustrations"
            runs_dir.mkdir(parents=True)
            image_path = runs_dir / "diagram.png"
            image_path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x17\x9b"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            with patch("app.services.article_render_service.CONFIG", config):
                rendered = self.service.render(
                    "## 核心机制\n\n这里解释机制。\n\n## 结论\n\n这里给出结论。",
                    article_title="测试",
                    pool="deep_dive",
                    subtype="technical_walkthrough",
                    illustrations=[
                        {
                            "type": "system_layers_infographic",
                            "anchor_heading": "核心机制",
                            "section_role": "architecture",
                            "title": "机制图",
                            "caption": "解释结构关系",
                            "visual_goal": "解释模块关系",
                            "visual_claim": "核心模块之间如何协作",
                            "path": str(image_path),
                        },
                        {
                            "type": "comparison_card",
                            "anchor_heading": "不存在的小节",
                            "section_role": "impact",
                            "title": "错误图",
                            "caption": "不应该被堆到文末",
                            "visual_goal": "解释错误内容",
                            "path": str(image_path),
                        },
                    ],
                    run_id="run-321",
                )

        self.assertEqual(rendered.inserted_illustration_count, 1)
        self.assertEqual(len(rendered.render_anchor_failures or []), 1)
        self.assertIn("核心机制", rendered.html)
        self.assertNotIn("错误图", rendered.html)

    def test_render_matches_h4_h5_h6_sections(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "run-deep-headings" / "illustrations"
            runs_dir.mkdir(parents=True)
            image_path = runs_dir / "diagram.png"
            image_path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x17\x9b"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            with patch("app.services.article_render_service.CONFIG", config):
                rendered = self.service.render(
                    "## 一级\n\n介绍\n\n#### 更深标题\n\n这里是细分说明。",
                    article_title="测试",
                    pool="deep_dive",
                    subtype="technical_walkthrough",
                    illustrations=[
                        {
                            "type": "system_layers_infographic",
                            "anchor_heading": "更深标题",
                            "section_role": "architecture",
                            "title": "深层结构图",
                            "caption": "对应 h4 锚点",
                            "visual_goal": "解释深层结构",
                            "visual_claim": "说明 h4 下的模块关系",
                            "path": str(image_path),
                        }
                    ],
                    run_id="run-deep-headings",
                )

        self.assertEqual(rendered.inserted_illustration_count, 1)
        self.assertEqual(rendered.html.count("<figure"), 1)
        self.assertEqual(rendered.render_anchor_failures, [])

    def test_render_does_not_output_dedicated_bridge_paragraph_for_illustrations(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "run-bridge" / "illustrations"
            runs_dir.mkdir(parents=True)
            image_path = runs_dir / "diagram.png"
            image_path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x17\x9b"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            with patch("app.services.article_render_service.CONFIG", config):
                rendered = self.service.render(
                    "## 核心机制\n\n这里解释系统机制。",
                    article_title="测试",
                    pool="deep_dive",
                    subtype="technical_walkthrough",
                    illustrations=[
                        {
                            "type": "system_layers_infographic",
                            "intent_kind": "explanatory",
                            "anchor_heading": "核心机制",
                            "section_role": "architecture",
                            "title": "结构图",
                            "caption": "解释模块关系",
                            "visual_goal": "解释系统机制",
                            "visual_claim": "说明关键模块如何协作",
                            "path": str(image_path),
                        }
                    ],
                    run_id="run-bridge",
                )

        self.assertNotIn("这一节里最值得配合图来看的是", rendered.html)
        self.assertNotIn("下面这张图主要", rendered.html)


    def test_render_spreads_multiple_illustrations_across_section_blocks(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "run-spread" / "illustrations"
            runs_dir.mkdir(parents=True)
            image_path = runs_dir / "diagram.png"
            image_path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x17\x9b"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            markdown = "## 鏍稿績鏈哄埗\n\n绗竴娈?\n\n绗簩娈?\n\n绗笁娈?"
            with patch("app.services.article_render_service.CONFIG", config):
                rendered = self.service.render(
                    markdown,
                    article_title="娴嬭瘯",
                    pool="deep_dive",
                    subtype="technical_walkthrough",
                    illustrations=[
                        {
                            "type": "reference_image",
                            "anchor_heading": "鏍稿績鏈哄埗",
                            "section_role": "overview",
                            "title": "鍥句竴",
                            "caption": "鍥句竴",
                            "path": str(image_path),
                        },
                        {
                            "type": "reference_image",
                            "anchor_heading": "鏍稿績鏈哄埗",
                            "section_role": "overview",
                            "title": "鍥句簩",
                            "caption": "鍥句簩",
                            "path": str(image_path),
                        },
                    ],
                    run_id="run-spread",
                )

        self.assertEqual(rendered.inserted_illustration_count, 2)
        self.assertEqual(rendered.html.count("<figure"), 2)
        compact_html = rendered.html.replace("\n", "").replace(" ", "")
        self.assertNotIn("</figure><figure", compact_html)
        first_paragraph = rendered.html.find("绗竴娈")
        second_paragraph = rendered.html.find("绗簩娈")
        first_figure = rendered.html.find("<figure")
        second_figure = rendered.html.find("<figure", first_figure + 1)
        self.assertLess(first_paragraph, first_figure)
        self.assertLess(second_paragraph, second_figure)

    def test_render_uses_middle_anchor_for_single_illustration_when_section_has_multiple_blocks(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "run-middle" / "illustrations"
            runs_dir.mkdir(parents=True)
            image_path = runs_dir / "diagram.png"
            image_path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x17\x9b"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            config = type("Cfg", (), {"data_dir": Path(tmpdir)})()
            markdown = "## 鏍稿績鏈哄埗\n\n绗竴娈?\n\n绗簩娈?\n\n绗笁娈?"
            with patch("app.services.article_render_service.CONFIG", config):
                rendered = self.service.render(
                    markdown,
                    article_title="娴嬭瘯",
                    pool="deep_dive",
                    subtype="technical_walkthrough",
                    illustrations=[
                        {
                            "type": "reference_image",
                            "anchor_heading": "鏍稿績鏈哄埗",
                            "section_role": "overview",
                            "title": "鍥句竴",
                            "caption": "鍥句竴",
                            "path": str(image_path),
                        }
                    ],
                    run_id="run-middle",
                )

        first_paragraph = rendered.html.find("绗竴娈")
        second_paragraph = rendered.html.find("绗簩娈")
        figure_index = rendered.html.find("<figure")
        self.assertLess(first_paragraph, second_paragraph)
        self.assertLess(second_paragraph, figure_index)


if __name__ == "__main__":
    unittest.main()
