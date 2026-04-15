import unittest

from app.runtime.facade import RuntimeFacade


class RuntimeFacadeMarkdownCleanupTests(unittest.TestCase):
    def test_prepare_article_markdown_strips_html_attribute_noise_outside_code(self) -> None:
        runtime = RuntimeFacade.__new__(RuntimeFacade)

        article = """#### 关键变化：从玩具到生产力工具

下面这张图来自原文，配合 target="_blank" title="noise" 一起看会更直观。
```html
<a target="_blank" title="keep">inside code block</a>
```
"""
        cleaned = runtime._prepare_article_markdown(article)

        self.assertIn("#### 关键变化：从玩具到生产力工具", cleaned)
        self.assertNotIn('target="_blank" title="noise"', cleaned)
        self.assertIn('<a target="_blank" title="keep">inside code block</a>', cleaned)

    def test_prepare_article_markdown_merges_short_list_heading_continuations(self) -> None:
        runtime = RuntimeFacade.__new__(RuntimeFacade)

        article = """## 给开发者的可执行建议
1. **评估必要性**
   ：如果你的代理只运行在严格沙箱环境或处理完全无害的任务，可能无须此类重型安全层。
2. **集成路径**
   首先将其用于监控和审计模式，观察代理在测试环境中的行为模式。"""
        cleaned = runtime._prepare_article_markdown(article)

        self.assertIn("1. **评估必要性**：如果你的代理只运行在严格沙箱环境或处理完全无害的任务", cleaned)
        self.assertIn("2. **集成路径**首先将其用于监控和审计模式", cleaned)
        self.assertNotIn("**评估必要性**\n   ：", cleaned)
        self.assertNotIn("**集成路径**\n   首先", cleaned)


if __name__ == "__main__":
    unittest.main()
