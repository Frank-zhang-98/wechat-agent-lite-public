import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.services.programmatic_visual_service import ProgrammaticVisualService


class ProgrammaticVisualServiceTests(unittest.TestCase):
    def test_overlay_cover_title_outputs_expected_size(self) -> None:
        service = ProgrammaticVisualService()

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "cover-base.png"
            output_path = Path(tmpdir) / "cover-final.png"
            Image.new("RGB", (1280, 720), (240, 240, 240)).save(base_path, format="PNG")

            asset = service.overlay_cover_title(
                base_image_path=base_path,
                article_title="李开复陆奇重仓 Harness 智能体公司明日新程：李笛带队，四个月完成两轮融资",
                output_path=output_path,
                size="1280*720",
                title_safe_zone="left_bottom",
            )

            self.assertEqual(asset["status"], "generated")
            self.assertTrue(output_path.exists())
            with Image.open(output_path) as rendered:
                self.assertEqual(rendered.size, (1280, 720))

    def test_sanitize_visual_text_prefers_clean_fallback_for_question_mark_noise(self) -> None:
        self.assertEqual(
            ProgrammaticVisualService._sanitize_visual_text("核心模块？？？？", fallback="核心模块"),
            "核心模块",
        )

    def test_sanitize_visual_text_removes_short_trailing_ascii_fragment(self) -> None:
        self.assertEqual(
            ProgrammaticVisualService._sanitize_visual_text("benchmark) ", fallback=""),
            "benchmark",
        )

    def test_infer_icon_kind_supports_more_product_module_shapes(self) -> None:
        self.assertEqual(ProgrammaticVisualService._infer_icon_kind("React 前端界面"), "frontend")
        self.assertEqual(ProgrammaticVisualService._infer_icon_kind("FastAPI 后端服务"), "backend")
        self.assertEqual(ProgrammaticVisualService._infer_icon_kind("浏览器自动化"), "browser")
        self.assertEqual(ProgrammaticVisualService._infer_icon_kind("权限沙箱"), "security")

    def test_comparison_dimension_rows_avoid_repeating_titles(self) -> None:
        service = ProgrammaticVisualService()
        rows = service._comparison_dimension_rows(
            left_title="开源版",
            right_title="云版",
            title="开源版与云版能力对比",
            details=["隐身浏览", "代理轮换", "验证码识别", "Gmail", "云版支持 1000+ 应用"],
            desired=4,
        )
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["dimension"] not in {row["left"], row["right"]} for row in rows))
        self.assertTrue(any(row["left"] == "开源版" or row["right"] == "云版" for row in rows))

    def test_render_body_illustration_supports_infographic_types(self) -> None:
        service = ProgrammaticVisualService()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "infographic.png"
            asset = service.render_body_illustration(
                article_title="AI Agent 记忆系统",
                brief={
                    "type": "comparison_infographic",
                    "title": "短期记忆与长期记忆协同",
                    "caption": "对比两类记忆在容量、检索与决策中的不同作用",
                    "must_show": ["短期记忆", "长期记忆", "上下文窗口", "向量数据库"],
                },
                output_path=output_path,
                size="1024*1024",
            )

            self.assertEqual(asset["diagram_type"], "comparison_infographic")
            self.assertTrue(output_path.exists())
            with Image.open(output_path) as rendered:
                self.assertEqual(rendered.size, (1024, 1024))


if __name__ == "__main__":
    unittest.main()
