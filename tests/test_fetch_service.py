import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services.fetch_service import FetchService


class FakeResponse:
    def __init__(self, *, status_code: int, text: str, content_type: str, url: str):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http_{self.status_code}")


class FakeJsonResponse:
    def __init__(self, *, payload: dict, status_code: int = 200):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http_{self.status_code}")

    def json(self) -> dict:
        return self._payload


class FetchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fetch = FetchService()

    def test_clean_text_strips_html_attribute_residue(self) -> None:
        raw = '下面这张图来自原文页面，配合 target="_blank" title="面壁智能" src="https://cdn.example.com/a.png" 一起看会更直观。'

        cleaned = self.fetch._clean_text(raw)

        self.assertNotIn('target="_blank"', cleaned)
        self.assertNotIn('title="面壁智能"', cleaned)
        self.assertNotIn('src="https://cdn.example.com/a.png"', cleaned)
        self.assertIn('下面这张图来自原文页面', cleaned)

    def test_clean_text_strips_dangling_img_fragment(self) -> None:
        raw = '面壁智能 OpenClaw “龙虾” 面壁智能获新一轮融资 <img'

        cleaned = self.fetch._clean_text(raw)

        self.assertNotIn('<img', cleaned)
        self.assertEqual(cleaned, '面壁智能 OpenClaw “龙虾” 面壁智能获新一轮融资')

    def test_extract_article_content_collects_article_images(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:title" content="News title" />
            <meta property="og:image" content="https://cdn.example.com/hero.jpg" />
            <meta property="og:image:alt" content="主视觉" />
          </head>
          <body>
            <article>
              <p>这是一段足够长的新闻正文内容，用于确保正文提取成功并返回图片候选。</p>
              <img src="/images/body-photo.png" alt="现场照片" width="1200" height="800" />
              <img src="/assets/logo.svg" alt="logo" />
            </article>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=html,
                content_type="text/html; charset=utf-8",
                url="https://news.example.com/post",
            ),
        ):
            result = self.fetch.extract_article_content("https://news.example.com/post")

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["images"])
        urls = [item["url"] for item in result["images"]]
        self.assertIn("https://cdn.example.com/hero.jpg", urls)
        self.assertIn("https://news.example.com/images/body-photo.png", urls)
        self.assertNotIn("https://news.example.com/assets/logo.svg", urls)

    def test_extract_article_content_can_skip_image_extraction(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:title" content="News title" />
            <meta property="og:image" content="https://cdn.example.com/hero.jpg" />
          </head>
          <body>
            <article>
              <p>这是一段足够长的正文内容，用于验证纯文本抽取仍然保留正文和段落。</p>
              <img src="/images/body-photo.png" alt="现场照片" width="1200" height="800" />
            </article>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=html,
                content_type="text/html; charset=utf-8",
                url="https://news.example.com/post",
            ),
        ):
            with patch.object(self.fetch, "_extract_html_images") as images_mock:
                result = self.fetch.extract_article_content("https://news.example.com/post", include_images=False)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["paragraphs"])
        self.assertEqual(result["images"], [])
        images_mock.assert_not_called()

    def test_extract_lightweight_image_candidates_prefers_meta_and_hero_sources(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:image" content="https://cdn.example.com/hero.jpg" />
            <meta property="og:image:alt" content="Headline hero image" />
            <link rel="image_src" href="https://cdn.example.com/alt-hero.jpg" />
          </head>
          <body>
            <article>
              <img src="/images/lead-photo.png" alt="Lead photo" width="1200" height="800" />
              <p>Long enough article content to keep extraction realistic.</p>
            </article>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=html,
                content_type="text/html; charset=utf-8",
                url="https://news.example.com/post",
            ),
        ):
            result = self.fetch.extract_lightweight_image_candidates("https://news.example.com/post")

        urls = [item["url"] for item in result]
        self.assertIn("https://cdn.example.com/hero.jpg", urls)
        self.assertIn("https://cdn.example.com/alt-hero.jpg", urls)
        self.assertIn("https://news.example.com/images/lead-photo.png", urls)

    def test_extract_article_content_skips_editorial_promo_blocks(self) -> None:
        html = """
        <html>
          <body>
            <article>
              <p>THIS WEEK ONLY: Save close to $500 on your Disrupt pass. Offer ends April 10.</p>
              <p>Image Credits: Getty Images</p>
              <p>Anthropic said Claude Code subscribers will need to pay extra for OpenClaw usage starting today, moving third-party harness usage to separate billing.</p>
            </article>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=html,
                content_type="text/html; charset=utf-8",
                url="https://news.example.com/post",
            ),
        ):
            result = self.fetch.extract_article_content("https://news.example.com/post")

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["paragraphs"])
        self.assertIn("Anthropic said Claude Code subscribers", result["paragraphs"][0])

    def test_extract_article_content_uses_browser_render_for_spa_shell(self) -> None:
        raw_html = """
        <html>
          <head>
            <title>GLM-5.1: Towards Long-Horizon Tasks</title>
            <script type="module" src="/blog/assets/glm-5.1.js"></script>
          </head>
          <body>
            <div id="root"></div>
          </body>
        </html>
        """
        rendered_html = """
        <html>
          <head><title>GLM-5.1: Towards Long-Horizon Tasks</title></head>
          <body>
            <main>
              <article>
                <p>GLM-5.1 is our next-generation flagship model for agentic engineering, with significantly stronger coding capabilities than its predecessor.</p>
                <p>It achieves state-of-the-art performance on SWE-Bench Pro and leads GLM-5 by a wide margin on NL2Repo and Terminal-Bench 2.0.</p>
              </article>
            </main>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=raw_html,
                content_type="text/html; charset=utf-8",
                url="https://z.ai/blog/glm-5.1",
            ),
        ):
            with patch.object(
                self.fetch,
                "_render_page_html",
                return_value={
                    "url": "https://z.ai/blog/glm-5.1",
                    "status": "ok",
                    "reason": "",
                    "html_text": rendered_html,
                    "title": "GLM-5.1: Towards Long-Horizon Tasks",
                    "fetch_mode": "browser_rendered",
                },
            ):
                result = self.fetch.extract_article_content("https://z.ai/blog/glm-5.1")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["fetch_mode"], "browser_rendered")
        self.assertIn("next-generation flagship model", result["content_text"])

    def test_extract_rerank_excerpt_light_avoids_browser_render_and_uses_cache(self) -> None:
        html = """
        <html>
          <head>
            <title>Agent Runtime</title>
            <meta name="description" content="A lightweight runtime for tool-using coding agents." />
          </head>
          <body>
            <article>
              <p>Agent Runtime focuses on stable execution, retry control, and deployment simplicity.</p>
              <p>It provides a narrow but practical abstraction over agent sessions and tool orchestration.</p>
            </article>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=html,
                content_type="text/html; charset=utf-8",
                url="https://example.com/runtime",
            ),
        ) as request_mock:
            with patch.object(self.fetch, "_render_page_html") as render_mock:
                first = self.fetch.extract_rerank_excerpt_light("https://example.com/runtime", max_chars=300, timeout=5)
                second = self.fetch.extract_rerank_excerpt_light("https://example.com/runtime", max_chars=300, timeout=5)

        self.assertEqual(first["status"], "ok")
        self.assertIn("lightweight runtime", first["excerpt"])
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(request_mock.call_count, 1)
        render_mock.assert_not_called()

    def test_github_repo_file_score_prefers_runtime_files_over_tests(self) -> None:
        runtime_score = self.fetch._github_repo_file_score("browser_use/agent/service.py")
        test_score = self.fetch._github_repo_file_score("tests/ci/test_agent_planning.py")

        self.assertGreater(runtime_score, test_score)

    def test_extract_repo_file_snippet_prefers_fenced_code_inside_markdown_docs(self) -> None:
        text = (
            "# Quick Start\n\n"
            "Use the following command:\n\n"
            "```bash\n"
            "claude /spec create\n"
            "```\n\n"
            "Then continue with the workflow.\n"
        )

        snippet = self.fetch._extract_repo_file_snippet(text, path="docs/commands.md", max_chars=200, max_lines=20)

        self.assertEqual(snippet, "claude /spec create")

    def test_extract_article_structure_marks_spa_shell_without_rendered_content_as_failed(self) -> None:
        raw_html = """
        <html>
          <head>
            <title>GLM-5.1: Towards Long-Horizon Tasks</title>
            <script type="module" src="/blog/assets/glm-5.1.js"></script>
          </head>
          <body>
            <div id="root"></div>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=raw_html,
                content_type="text/html; charset=utf-8",
                url="https://z.ai/blog/glm-5.1",
            ),
        ):
            with patch.object(
                self.fetch,
                "_render_page_html",
                return_value={
                    "url": "https://z.ai/blog/glm-5.1",
                    "status": "failed",
                    "reason": "browser_render_failed: timeout",
                    "html_text": "",
                    "title": "",
                    "fetch_mode": "browser_rendered",
                },
            ):
                result = self.fetch.extract_article_structure("https://z.ai/blog/glm-5.1")

        self.assertEqual(result["status"], "failed")
        self.assertIn("browser_render_failed", result["reason"])

    def test_build_article_structure_filters_recommendation_headings_from_news_body(self) -> None:
        html = """
        <html>
          <body>
            <article>
              <h2>Meet your next investor or portfolio startup at Disrupt</h2>
              <p>Apply now to meet the right people.</p>
              <h2>What happened</h2>
              <p>OpenAI published a response after Sam Altman addressed the New Yorker article and the attack on his home.</p>
            </article>
          </body>
        </html>
        """

        result = self.fetch._build_article_structure(html, title="Sam Altman response")

        headings = [section.get("heading", "") for section in result["sections"]]
        self.assertNotIn("Meet your next investor or portfolio startup at Disrupt", headings)
        self.assertIn("What happened", headings)

    def test_extract_article_structure_enriches_github_repo_with_real_source_snippets(self) -> None:
        repo_html = """
        <html>
          <head><title>acme/agent-runtime</title></head>
          <body>
            <article>
              <h2>Quick Start</h2>
              <p>Install dependencies and run the local agent runtime.</p>
              <pre class="language-bash"><code>npm install\nnpm run dev</code></pre>
            </article>
          </body>
        </html>
        """

        def fake_request(url: str, timeout: int = 15):
            if url == "https://github.com/acme/agent-runtime":
                return FakeResponse(
                    status_code=200,
                    text=repo_html,
                    content_type="text/html; charset=utf-8",
                    url=url,
                )
            if url == "https://raw.githubusercontent.com/acme/agent-runtime/main/src/server/app.ts":
                return FakeResponse(
                    status_code=200,
                    text="export async function startServer() {\n  return createServer(app)\n}\n",
                    content_type="text/plain; charset=utf-8",
                    url=url,
                )
            if url == "https://raw.githubusercontent.com/acme/agent-runtime/main/package.json":
                return FakeResponse(
                    status_code=200,
                    text='{"name":"agent-runtime","scripts":{"dev":"tsx src/server/app.ts"}}',
                    content_type="application/json",
                    url=url,
                )
            if url == "https://raw.githubusercontent.com/acme/agent-runtime/main/Dockerfile":
                return FakeResponse(
                    status_code=200,
                    text="FROM node:20-alpine\nWORKDIR /app\nCOPY . .\nRUN npm install\nCMD [\"npm\",\"run\",\"dev\"]\n",
                    content_type="text/plain; charset=utf-8",
                    url=url,
                )
            raise AssertionError(f"unexpected url: {url}")

        def fake_github_api(url: str, *, timeout: int = 15):
            if url == "https://api.github.com/repos/acme/agent-runtime":
                return {"default_branch": "main"}
            if url == "https://api.github.com/repos/acme/agent-runtime/git/trees/main?recursive=1":
                return {
                    "tree": [
                        {"path": "README.md", "type": "blob"},
                        {"path": "src/server/app.ts", "type": "blob"},
                        {"path": "package.json", "type": "blob"},
                        {"path": "Dockerfile", "type": "blob"},
                    ]
                }
            raise AssertionError(f"unexpected api url: {url}")

        with patch.object(self.fetch, "_request", side_effect=fake_request):
            with patch.object(self.fetch, "_github_api_get_json", side_effect=fake_github_api):
                result = self.fetch.extract_article_structure("https://github.com/acme/agent-runtime")

        self.assertEqual(result["status"], "ok")
        self.assertIn("github_repo_context", result)
        self.assertEqual(result["github_repo_context"]["repo_slug"], "acme/agent-runtime")
        self.assertTrue(result["code_blocks"])
        self.assertEqual(result["code_blocks"][0]["origin"], "repo_file")
        self.assertEqual(result["code_blocks"][0]["source_path"], "src/server/app.ts")
        self.assertIn("startServer", result["code_blocks"][0]["code_text"])
        self.assertTrue(any("仓库源码" in str(section.get("heading", "")) for section in result["sections"]))

    def test_extract_article_structure_focuses_collection_repo_on_single_subproject(self) -> None:
        repo_html = """
        <html>
          <head><title>awesome-llm-apps</title></head>
          <body>
            <article>
              <h2>Featured AI Projects</h2>
              <p>A curated collection of runnable LLM apps.</p>
            </article>
          </body>
        </html>
        """

        raw_files = {
            "advanced_llm_apps/multimodal_video_moment_finder/backend/server.py": "app = FastAPI()\napp.mount('/frames', StaticFiles(directory='frames'))\n",
            "advanced_llm_apps/multimodal_video_moment_finder/backend/requirements.txt": "fastapi>=0.115.0\nchromadb>=0.5.0\n",
            "awesome_agent_skills/self-improving-agent-skills/backend/app.py": "sessions = {}\nclass AnalyzeRequest(BaseModel):\n    session_id: str\n",
            "advanced_ai_agents/multi_agent_apps/ai_negotiation_battle_simulator/backend/agent.py": "class NegotiationState:\n    pass\n",
        }

        def fake_request(url: str, timeout: int = 15):
            if url == "https://github.com/example/awesome-llm-apps":
                return FakeResponse(
                    status_code=200,
                    text=repo_html,
                    content_type="text/html; charset=utf-8",
                    url=url,
                )
            prefix = "https://raw.githubusercontent.com/example/awesome-llm-apps/main/"
            if url.startswith(prefix):
                path = url[len(prefix) :]
                if path in raw_files:
                    return FakeResponse(
                        status_code=200,
                        text=raw_files[path],
                        content_type="text/plain; charset=utf-8",
                        url=url,
                    )
            raise AssertionError(f"unexpected url: {url}")

        def fake_github_api(url: str, *, timeout: int = 15):
            if url == "https://api.github.com/repos/example/awesome-llm-apps":
                return {
                    "default_branch": "main",
                    "name": "awesome-llm-apps",
                    "description": "A curated collection of runnable LLM app examples.",
                }
            if url == "https://api.github.com/repos/example/awesome-llm-apps/git/trees/main?recursive=1":
                return {
                    "tree": [
                        {"path": "advanced_llm_apps/multimodal_video_moment_finder/backend/server.py", "type": "blob"},
                        {"path": "advanced_llm_apps/multimodal_video_moment_finder/backend/requirements.txt", "type": "blob"},
                        {"path": "awesome_agent_skills/self-improving-agent-skills/backend/app.py", "type": "blob"},
                        {"path": "advanced_ai_agents/multi_agent_apps/ai_negotiation_battle_simulator/backend/agent.py", "type": "blob"},
                    ]
                }
            raise AssertionError(f"unexpected api url: {url}")

        with patch.object(self.fetch, "_request", side_effect=fake_request):
            with patch.object(self.fetch, "_github_api_get_json", side_effect=fake_github_api):
                result = self.fetch.extract_article_structure("https://github.com/example/awesome-llm-apps")

        repo_context = result.get("github_repo_context") or {}
        self.assertEqual(result["status"], "ok")
        self.assertTrue(repo_context.get("is_collection_repo"))
        self.assertEqual(
            repo_context.get("focus_root"),
            "advanced_llm_apps/multimodal_video_moment_finder",
        )
        selected_paths = [item.get("path") for item in repo_context.get("files") or []]
        self.assertTrue(selected_paths)
        self.assertTrue(
            all(path.startswith("advanced_llm_apps/multimodal_video_moment_finder/") for path in selected_paths)
        )

    def test_extract_article_structure_deprioritizes_lockfiles_for_tooling_repo(self) -> None:
        repo_html = """
        <html>
          <head><title>CopilotKit</title></head>
          <body>
            <article>
              <h2>Frontend SDK for Agents</h2>
              <p>React + Angular SDK with AG-UI protocol.</p>
            </article>
          </body>
        </html>
        """

        raw_files = {
            "sdk-python/poetry.lock": "[[package]]\nname = \"ag-ui-langgraph\"\nversion = \"0.0.5\"\n",
            "package.json": '{"name":"copilotkit","scripts":{"dev":"turbo dev"}}',
            ".env.example": "AGENT_URL=http://localhost:8000\nOPENAI_API_KEY=\n",
            "src/runtime.ts": "export async function startRuntime() {\n  return createRuntime();\n}\n",
        }

        def fake_request(url: str, timeout: int = 15):
            if url == "https://github.com/example/copilotkit":
                return FakeResponse(
                    status_code=200,
                    text=repo_html,
                    content_type="text/html; charset=utf-8",
                    url=url,
                )
            prefix = "https://raw.githubusercontent.com/example/copilotkit/main/"
            if url.startswith(prefix):
                path = url[len(prefix) :]
                if path in raw_files:
                    return FakeResponse(
                        status_code=200,
                        text=raw_files[path],
                        content_type="text/plain; charset=utf-8",
                        url=url,
                    )
            raise AssertionError(f"unexpected url: {url}")

        def fake_github_api(url: str, *, timeout: int = 15):
            if url == "https://api.github.com/repos/example/copilotkit":
                return {
                    "default_branch": "main",
                    "name": "copilotkit",
                    "description": "Frontend SDK and runtime for agent-native UI.",
                }
            if url == "https://api.github.com/repos/example/copilotkit/git/trees/main?recursive=1":
                return {
                    "tree": [
                        {"path": "sdk-python/poetry.lock", "type": "blob"},
                        {"path": "package.json", "type": "blob"},
                        {"path": ".env.example", "type": "blob"},
                        {"path": "src/runtime.ts", "type": "blob"},
                    ]
                }
            raise AssertionError(f"unexpected api url: {url}")

        with patch.object(self.fetch, "_request", side_effect=fake_request):
            with patch.object(self.fetch, "_github_api_get_json", side_effect=fake_github_api):
                result = self.fetch.extract_article_structure("https://github.com/example/copilotkit")

        selected_paths = [item.get("path") for item in (result.get("github_repo_context") or {}).get("files") or []]
        self.assertEqual(result["status"], "ok")
        self.assertIn("src/runtime.ts", selected_paths[:2])
        self.assertIn("package.json", selected_paths)
        self.assertNotEqual(selected_paths[0], "sdk-python/poetry.lock")

    def test_extract_repo_file_snippet_skips_low_signal_barrel_files(self) -> None:
        snippet = self.fetch._extract_repo_file_snippet(
            "// place files you want to import through the `$lib` alias in this folder.\n",
            path="src/lib/index.ts",
        )

        self.assertEqual(snippet, "")

    def test_extract_article_structure_prefers_dominant_service_root_for_monorepo(self) -> None:
        repo_html = """
        <html>
          <head><title>Firecrawl</title></head>
          <body>
            <article>
              <h2>Apps for API and SDK usage</h2>
              <p>Monorepo with API service, Java SDK, and deployment assets.</p>
            </article>
          </body>
        </html>
        """

        raw_files = {
            "apps/java-sdk/settings.gradle.kts": 'rootProject.name = "firecrawl-java"\n',
            "apps/api/src/index.ts": "export async function bootstrapApi() {\n  return createServer(app)\n}\n",
            "apps/api/src/lib/clickhouse-client.ts": "export async function writeBatch() {\n  return clickhouse.insert({})\n}\n",
            "apps/api/Dockerfile": "FROM node:22-slim\nRUN corepack enable\n",
            "apps/api/package.json": '{"name":"api","scripts":{"dev":"tsx src/index.ts"}}',
        }

        def fake_request(url: str, timeout: int = 15):
            if url == "https://github.com/firecrawl/firecrawl":
                return FakeResponse(
                    status_code=200,
                    text=repo_html,
                    content_type="text/html; charset=utf-8",
                    url=url,
                )
            prefix = "https://raw.githubusercontent.com/firecrawl/firecrawl/main/"
            if url.startswith(prefix):
                path = url[len(prefix) :]
                if path in raw_files:
                    return FakeResponse(
                        status_code=200,
                        text=raw_files[path],
                        content_type="text/plain; charset=utf-8",
                        url=url,
                    )
            raise AssertionError(f"unexpected url: {url}")

        def fake_github_api(url: str, *, timeout: int = 15):
            if url == "https://api.github.com/repos/firecrawl/firecrawl":
                return {
                    "default_branch": "main",
                    "name": "firecrawl",
                    "description": "Web data API for AI apps.",
                }
            if url == "https://api.github.com/repos/firecrawl/firecrawl/git/trees/main?recursive=1":
                return {
                    "tree": [
                        {"path": "apps/java-sdk/settings.gradle.kts", "type": "blob"},
                        {"path": "apps/api/src/index.ts", "type": "blob"},
                        {"path": "apps/api/src/lib/clickhouse-client.ts", "type": "blob"},
                        {"path": "apps/api/Dockerfile", "type": "blob"},
                        {"path": "apps/api/package.json", "type": "blob"},
                    ]
                }
            raise AssertionError(f"unexpected api url: {url}")

        with patch.object(self.fetch, "_request", side_effect=fake_request):
            with patch.object(self.fetch, "_github_api_get_json", side_effect=fake_github_api):
                result = self.fetch.extract_article_structure("https://github.com/firecrawl/firecrawl")

        repo_context = result.get("github_repo_context") or {}
        selected_paths = [item.get("path") for item in repo_context.get("files") or []]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(repo_context.get("focus_root"), "apps/api")
        self.assertTrue(selected_paths)
        self.assertTrue(all(path.startswith("apps/api/") for path in selected_paths))

    def test_fetch_github_supports_query_groups_and_deduplicates(self) -> None:
        captured_queries: list[str] = []

        def fake_get(url: str, *, params: dict, **kwargs):
            self.assertEqual(url, "https://api.github.com/search/repositories")
            captured_queries.append(str(params.get("q", "")))
            if "language:python topic:agent llm stars:>=40" == params.get("q"):
                return FakeJsonResponse(
                    payload={
                        "items": [
                            {
                                "name": "agent-runtime",
                                "html_url": "https://github.com/acme/agent-runtime",
                                "description": "Python agent runtime",
                                "updated_at": "2026-04-09T02:00:00Z",
                                "stargazers_count": 4200,
                            }
                        ]
                    }
                )
            if "mcp llm stars:>=20" == params.get("q"):
                return FakeJsonResponse(
                    payload={
                        "items": [
                            {
                                "name": "agent-runtime",
                                "html_url": "https://github.com/acme/agent-runtime",
                                "description": "Python agent runtime with MCP support",
                                "updated_at": "2026-04-09T03:00:00Z",
                                "stargazers_count": 4200,
                            },
                            {
                                "name": "mcp-inspector",
                                "html_url": "https://github.com/acme/mcp-inspector",
                                "description": "Inspect MCP traffic",
                                "updated_at": "2026-04-08T18:00:00Z",
                                "stargazers_count": 950,
                            },
                        ]
                    }
                )
            raise AssertionError(f"unexpected query: {params.get('q')}")

        with patch("app.services.fetch_service.requests.get", side_effect=fake_get):
            result = self.fetch.fetch_github(
                {
                    "enabled": True,
                    "min_stars": 40,
                    "max_results": 10,
                    "query_groups": [
                        {"name": "agents-python", "q": "language:python topic:agent llm"},
                        {"name": "mcp-tooling", "q": "mcp llm", "min_stars": 20},
                    ],
                },
                max_age_hours=168,
            )

        self.assertEqual(
            captured_queries,
            [
                "language:python topic:agent llm stars:>=40",
                "mcp llm stars:>=20",
            ],
        )
        self.assertEqual([item["title"] for item in result], ["agent-runtime", "mcp-inspector"])
        self.assertEqual(
            result[0]["github_query_groups"],
            ["agents-python", "mcp-tooling"],
        )
        self.assertEqual(result[0]["published"], "2026-04-09T03:00:00+00:00")

    def test_fetch_github_uses_legacy_query_when_query_groups_absent(self) -> None:
        captured_queries: list[str] = []

        def fake_get(url: str, *, params: dict, **kwargs):
            captured_queries.append(str(params.get("q", "")))
            return FakeJsonResponse(
                payload={
                    "items": [
                        {
                            "name": "deep-repo",
                            "html_url": "https://github.com/acme/deep-repo",
                            "description": "A solid repository",
                            "updated_at": "2026-04-09T01:00:00Z",
                            "stargazers_count": 88,
                        }
                    ]
                }
            )

        with patch("app.services.fetch_service.requests.get", side_effect=fake_get):
            result = self.fetch.fetch_github(
                {
                    "enabled": True,
                    "languages": ["python"],
                    "topics": ["llm"],
                    "min_stars": 10,
                    "max_results": 5,
                },
                max_age_hours=168,
            )

        self.assertEqual(captured_queries, ["language:python topic:llm stars:>=10"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "deep-repo")

    def test_fetch_rss_missing_publish_time_stays_unknown_instead_of_now(self) -> None:
        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text="<rss></rss>",
                content_type="application/rss+xml",
                url="https://example.com/feed.xml",
            ),
        ):
            with patch("app.services.fetch_service.feedparser.parse", return_value=SimpleNamespace(entries=[{
                "title": "Breaking update",
                "link": "https://example.com/post",
                "summary": "Important release details.",
            }])):
                with patch.object(
                    self.fetch,
                    "extract_article_metadata",
                    return_value={"title": "", "published": "", "published_source": "", "published_confidence": "low", "summary": ""},
                ):
                    result = self.fetch.fetch_rss(
                        {"url": "https://example.com/feed.xml", "name": "Example Feed", "weight": 1.0},
                        max_age_hours=168,
                        max_items=5,
                    )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["published"], "")
        self.assertEqual(result[0]["published_status"], "unknown")
        self.assertEqual(result[0]["published_confidence"], "low")

    def test_fetch_rss_backfills_publish_time_from_article_metadata(self) -> None:
        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text="<rss></rss>",
                content_type="application/rss+xml",
                url="https://example.com/feed.xml",
            ),
        ):
            with patch("app.services.fetch_service.feedparser.parse", return_value=SimpleNamespace(entries=[{
                "title": "Launch update",
                "link": "https://example.com/launch-post",
                "summary": "Launch details.",
            }])):
                with patch.object(
                    self.fetch,
                    "extract_article_metadata",
                    return_value={
                        "title": "Launch update",
                        "published": "2026-04-10T12:00:00+00:00",
                        "published_source": "meta_article_published_time",
                        "published_confidence": "high",
                        "summary": "Launch details.",
                    },
                ):
                    result = self.fetch.fetch_rss(
                        {"url": "https://example.com/feed.xml", "name": "Example Feed", "weight": 1.0},
                        max_age_hours=168,
                        max_items=5,
                    )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["published"], "2026-04-10T12:00:00+00:00")
        self.assertEqual(result[0]["published_source"], "meta_article_published_time")
        self.assertEqual(result[0]["published_confidence"], "high")
        self.assertEqual(result[0]["published_status"], "fresh")

    def test_normalize_published_text_accepts_single_digit_date_components(self) -> None:
        self.assertEqual(
            self.fetch._normalize_published_text("2025.8.7"),
            "2025-08-07T00:00:00+00:00",
        )
        self.assertEqual(
            self.fetch._normalize_published_text("2025/8/7"),
            "2025-08-07T00:00:00+00:00",
        )
        self.assertEqual(
            self.fetch._normalize_published_text("2025-8-7"),
            "2025-08-07T00:00:00+00:00",
        )
        self.assertEqual(
            self.fetch._normalize_published_text("2025年8月7日"),
            "2025-08-07T00:00:00+00:00",
        )

    def test_extract_article_metadata_prefers_visible_single_digit_date_over_dynamic_jsonld_now(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        jsonld_now = now.isoformat().replace("+00:00", "Z")
        html = f"""
        <html>
          <head>
            <title>MiniMax Speech 2.5</title>
            <script type="application/ld+json">
              {{"@type":"NewsArticle","datePublished":"{jsonld_now}","dateModified":"{jsonld_now}"}}
            </script>
          </head>
          <body>
            <article>
              <div>2025.8.7</div>
              <h1>MiniMax Speech 2.5</h1>
              <p>MiniMax Speech 2.5 updates multilingual voice generation.</p>
            </article>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=html,
                content_type="text/html; charset=utf-8",
                url="https://www.minimaxi.com/news/minimax-speech-25",
            ),
        ):
            result = self.fetch.extract_article_metadata("https://www.minimaxi.com/news/minimax-speech-25")

        self.assertEqual(result["published"], "2025-08-07T00:00:00+00:00")
        self.assertEqual(result["published_source"], "visible_header_date")

    def test_extract_article_metadata_prefers_serialized_article_date_over_dynamic_jsonld_now(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        old_day = (now - timedelta(days=164)).date()
        jsonld_now = now.isoformat().replace("+00:00", "Z")
        serialized_day = old_day.strftime("%Y.%m.%d")
        html = f"""
        <html>
          <head>
            <script type="application/ld+json">
              {{"@type":"NewsArticle","datePublished":"{jsonld_now}","dateModified":"{jsonld_now}"}}
            </script>
          </head>
          <body>
            <article>
              <script>
                self.__next_f.push([1,"{{\\"type\\":\\"ArticleTitle\\",\\"props\\":{{\\"date\\":\\"{serialized_day}\\",\\"title\\":\\"MiniMax Speech 2.6\\"}}}}"])
              </script>
              <h1>MiniMax Speech 2.6</h1>
              <p>MiniMax Speech 2.6 keeps latency low for voice agents.</p>
            </article>
          </body>
        </html>
        """

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=html,
                content_type="text/html; charset=utf-8",
                url="https://www.minimaxi.com/news/minimax-speech-26",
            ),
        ):
            result = self.fetch.extract_article_metadata("https://www.minimaxi.com/news/minimax-speech-26")

        self.assertEqual(result["published"], f"{old_day.isoformat()}T00:00:00+00:00")
        self.assertIn(result["published_source"], {"serialized_article_title_date", "visible_header_date"})
        self.assertNotEqual(result["published_source"], "jsonld_datePublished")

    def test_fetch_html_list_filters_stale_item_when_jsonld_now_conflicts_with_serialized_article_date(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        old_day = (now - timedelta(days=164)).date()
        jsonld_now = now.isoformat().replace("+00:00", "Z")
        serialized_day = old_day.strftime("%Y.%m.%d")
        html = f"""
        <html>
          <head>
            <script type="application/ld+json">
              {{"@type":"NewsArticle","datePublished":"{jsonld_now}","dateModified":"{jsonld_now}"}}
            </script>
          </head>
          <body>
            <article>
              <script>
                self.__next_f.push([1,"{{\\"type\\":\\"ArticleTitle\\",\\"props\\":{{\\"date\\":\\"{serialized_day}\\",\\"title\\":\\"MiniMax Speech 2.6\\"}}}}"])
              </script>
              <h1>MiniMax Speech 2.6</h1>
              <p>MiniMax Speech 2.6 keeps latency low for voice agents.</p>
            </article>
          </body>
        </html>
        """
        scrapling = SimpleNamespace(
            build_html_list_items=lambda **kwargs: [
                {
                    "title": "https://www.minimaxi.com/news/minimax-speech-26",
                    "url": "https://www.minimaxi.com/news/minimax-speech-26",
                    "summary": "",
                }
            ]
        )

        with patch.object(
            self.fetch,
            "_request",
            return_value=FakeResponse(
                status_code=200,
                text=html,
                content_type="text/html; charset=utf-8",
                url="https://www.minimaxi.com/news/minimax-speech-26",
            ),
        ):
            result = self.fetch.fetch_html_list(
                {
                    "url": "https://www.minimaxi.com/news",
                    "name": "MiniMax News",
                    "weight": 0.9,
                },
                max_age_hours=168,
                max_items=5,
                scrapling=scrapling,
            )

        self.assertEqual(result, [])
