import unittest

from app.services.localization_service import LocalizationService


class LocalizationServiceTests(unittest.TestCase):
    def test_localize_heading_text_supports_direct_and_mixed_headings(self) -> None:
        self.assertEqual(LocalizationService.localize_heading_text("Introduction"), "引言")
        self.assertEqual(LocalizationService.localize_heading_text("Core Features 实现拆解"), "核心能力实现拆解")
        self.assertEqual(LocalizationService.localize_heading_text("What's new in v3.0.0"), "v3.0.0 更新了什么")
        self.assertEqual(LocalizationService.localize_heading_text("Use Case Setup"), "用例设置")
        self.assertEqual(LocalizationService.localize_heading_text("How does PageIndex work?"), "PageIndex 如何工作？")
        self.assertEqual(
            LocalizationService.localize_heading_text("Phase 1: Indexing (once per document)"),
            "阶段 1：索引（每份文档一次）",
        )
        self.assertEqual(
            LocalizationService.localize_heading_text("对比 of Vectorless vs Flat Vector RAG"),
            "无向量 RAG 与 扁平向量 RAG 对比",
        )
        self.assertEqual(
            LocalizationService.localize_heading_text("Engineering a Better 检索器 — Proxy-Pointer RAG"),
            "Proxy-Pointer RAG：更好的检索器工程",
        )

    def test_localize_heading_text_supports_glm_walkthrough_headings(self) -> None:
        self.assertEqual(LocalizationService.localize_heading_text("Complex Software Engineering Tasks"), "复杂软件工程任务")
        self.assertEqual(LocalizationService.localize_heading_text("SWE-Bench Pro"), "SWE-Bench Pro 基准测试")
        self.assertEqual(
            LocalizationService.localize_heading_text("Scenario 1: Optimizing a Vector Database Over 600 Iterations"),
            "场景 1：优化向量数据库：持续 600 轮迭代",
        )
        self.assertEqual(
            LocalizationService.localize_heading_text("Scenario 2: Optimizing Machine Learning Workload Over 1,000+ Turns"),
            "场景 2：优化机器学习负载：持续 1,000+ 轮",
        )
        self.assertEqual(
            LocalizationService.localize_heading_text("Scenario 3: Building a Linux Desktop Over 8 Hours"),
            "场景 3：构建 Linux 桌面：持续 8 小时",
        )
        self.assertEqual(LocalizationService.localize_heading_text("Getting started with GLM-5.1"), "GLM-5.1 快速开始")
        self.assertEqual(
            LocalizationService.localize_heading_text("Use GLM-5.1 with GLM Coding Plan"),
            "通过 GLM Coding Plan 使用 GLM-5.1",
        )
        self.assertEqual(
            LocalizationService.localize_heading_text("Chat with GLM-5.1 on Z.ai"),
            "在 Z.ai 上体验 GLM-5.1",
        )
        self.assertEqual(LocalizationService.localize_heading_text("Serve GLM-5.1 Locally"), "本地部署 GLM-5.1")

    def test_localize_visual_text_preserves_commands_and_translates_labels(self) -> None:
        self.assertEqual(
            LocalizationService.localize_visual_text("Agent Runtime is infrastructure, not a plugin."),
            "智能体运行时不是插件，而是基础设施。",
        )
        self.assertEqual(
            LocalizationService.localize_visual_items(["Agent", "Sandbox", "npx 0nmcp@latest"]),
            ["智能体", "沙箱", "npx 0nmcp@latest"],
        )


if __name__ == "__main__":
    unittest.main()
