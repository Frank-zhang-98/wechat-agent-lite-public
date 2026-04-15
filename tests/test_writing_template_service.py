import unittest

from app.services.writing_template_service import WritingTemplateService


class WritingTemplateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WritingTemplateService()

    def test_build_pool_writing_blueprint_uses_subtype_quality_focus_for_news(self) -> None:
        blueprint = self.service.build_pool_writing_blueprint(
            topic={"title": "OpenAI pricing change", "summary": "A market-facing pricing update."},
            fact_pack={
                "primary_pool": "news",
                "subtype": "industry_news",
                "section_blueprint": [{"heading": "????", "summary": "What changed."}],
            },
            audience_key="ai_builder",
            subtype="industry_news",
        )

        self.assertEqual(blueprint["pool"], "news")
        self.assertEqual(blueprint["subtype"], "industry_news")
        self.assertIn("是否讲清事件、变化和影响", blueprint["quality_focus"])
        self.assertIn("减少新闻复述堆砌，补足变化判断和行动建议", blueprint["rewrite_focus"])

    def test_build_pool_writing_blueprint_uses_subtype_quality_focus_for_github(self) -> None:
        blueprint = self.service.build_pool_writing_blueprint(
            topic={"title": "Agent Armor", "summary": "A governance runtime for AI agents."},
            fact_pack={
                "primary_pool": "github",
                "subtype": "code_explainer",
                "section_blueprint": [{"heading": "Architecture", "summary": "Rule engine and audit path."}],
            },
            audience_key="ai_builder",
            subtype="code_explainer",
        )

        self.assertEqual(blueprint["pool"], "github")
        self.assertEqual(blueprint["subtype"], "code_explainer")
        self.assertIn("结构和实现链路是否完整", blueprint["quality_focus"])
        self.assertIn("补齐实现链路中的关键连接处", blueprint["rewrite_focus"])

    def test_subtype_prompt_profile_preserves_rule_lists_from_existing_templates(self) -> None:
        profile = self.service._subtype_prompt_profile(primary_pool="github", subtype="code_explainer")

        self.assertTrue(profile["opening_rules"])
        self.assertTrue(profile["organization_rules"])
        self.assertTrue(profile["evidence_rules"])
        self.assertTrue(profile["ending_rules"])

    def test_build_write_prompt_pool_first_does_not_require_content_type_inference(self) -> None:
        original = self.service.infer_content_type
        try:
            self.service.infer_content_type = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not infer content type"))
            prompt = self.service.build_write_prompt(
                topic={"title": "Agent Runtime", "summary": "A technical repo walkthrough.", "url": "https://github.com/example/agent-runtime"},
                fact_pack={
                    "primary_pool": "github",
                    "subtype": "code_explainer",
                    "topic_source": "GitHub",
                    "published": "2026-04-14T00:00:00+00:00",
                    "key_points": ["Policy enforcement", "Audit trail"],
                    "section_blueprint": [{"heading": "Architecture", "summary": "Rule engine and command interception."}],
                    "implementation_steps": [{"title": "Execution flow", "summary": "Intercept, evaluate, record.", "details": ["Intercept", "Evaluate"]}],
                    "architecture_points": [{"component": "Policy engine", "responsibility": "Evaluates tool actions"}],
                    "code_artifacts": [{"section": "policy_engine.py", "summary": "Command allow/deny logic", "language": "python"}],
                    "coverage_checklist": ["Policy engine", "Audit trail"],
                    "pool_signal_pack": {},
                    "related_context_signals": [],
                    "numbers": [],
                    "keywords": ["policy", "audit"],
                    "grounded_hard_facts": ["The repo evaluates tool actions before execution."],
                    "grounded_official_facts": [],
                    "grounded_context_facts": [],
                    "industry_context_points": [],
                    "soft_inferences": [],
                    "unknowns": [],
                    "forbidden_claims": [],
                    "deployment_points": ["Docker compose support"],
                    "github_repo_url": "https://github.com/example/agent-runtime",
                    "github_repo_slug": "example/agent-runtime",
                    "github_repo_archetype": "single_repo",
                    "github_repo_archetype_label": "Single Repo",
                    "github_repo_archetype_objective": "Explain repo positioning and implementation chain.",
                    "github_code_depth": "medium",
                    "github_deployment_need": "required",
                    "required_code_block_count": 1,
                    "required_source_code_block_count": 1,
                    "source_lead": "The repo intercepts and governs agent tool execution.",
                },
                audience_key="ai_builder",
                pool="github",
                subtype="code_explainer",
                pool_blueprint={
                    "pool": "github",
                    "pool_label": "GitHub ???",
                    "strategy": "project_recommend_plus_stack",
                    "subtype": "code_explainer",
                    "subtype_label": "Code Explainer",
                },
                outline_plan={
                    "sections": [
                        {
                            "heading": "Architecture",
                            "purpose": "Explain the rule engine.",
                            "evidence_points": ["Policy engine", "Audit trail"],
                        }
                    ]
                },
            )
        finally:
            self.service.infer_content_type = original

        self.assertIn("GitHub ???", prompt)
        self.assertIn("Code Explainer", prompt)
        self.assertNotIn("news_analysis", prompt)

    def test_build_fact_pack_includes_structure_and_preserved_code_blocks(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "Building Sourcing Intel",
                "summary": "A supply chain intelligence platform with LangGraph, MCP, and RAG.",
                "url": "https://example.com/article",
                "source": "dev.to",
                "published": "2026-04-01T00:00:00+00:00",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "lead text",
                    "paragraphs": ["para1", "para2", "para3"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "This system uses LangGraph and MCP to coordinate sourcing.",
                "coverage_checklist": ["LangGraph orchestration", "MCP integration", "RAG layer"],
                "sections": [
                    {
                        "heading": "Step 1: LangGraph orchestration",
                        "summary": "Use LangGraph to control sourcing flow.",
                        "paragraphs": ["State machine design", "Retry behavior"],
                        "code_refs": [0],
                    },
                    {
                        "heading": "MCP integration",
                        "summary": "Expose tools through MCP.",
                        "paragraphs": ["Tool layer", "Agent calls"],
                        "code_refs": [],
                    },
                ],
                "code_blocks": [
                    {
                        "language": "python",
                        "code_excerpt": "graph = StateGraph(State)",
                        "code_text": "graph = StateGraph(State)\ngraph.add_node('fetch', fetch_node)",
                        "kind": "code",
                        "line_count": 2,
                    }
                ],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertTrue(fact_pack["section_blueprint"])
        self.assertTrue(fact_pack["implementation_steps"])
        self.assertTrue(fact_pack["architecture_points"])
        self.assertTrue(fact_pack["code_artifacts"])
        self.assertTrue(fact_pack["preserved_code_blocks"])
        self.assertEqual(fact_pack["coverage_checklist"], ["LangGraph 编排", "MCP 集成", "RAG 层"])
        self.assertEqual(fact_pack["coverage_checklist_source"], ["LangGraph orchestration", "MCP integration", "RAG layer"])
        self.assertEqual(fact_pack["section_blueprint"][0]["source_heading"], "Step 1: LangGraph orchestration")
        self.assertIn("graph.add_node", fact_pack["preserved_code_blocks"][0]["code_text"])

    def test_build_fact_pack_localizes_english_coverage_headings_for_display(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "Stop Manually Chaining Endpoints",
                "summary": "A technical post about MCP and agent swarms.",
                "url": "https://example.com/mcp-swarms",
                "source": "dev.to",
                "published": "2026-04-09T00:00:00+00:00",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "lead text",
                    "paragraphs": ["para1", "para2"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "The article walks through pain points, filtering infrastructure, code, and argument.",
                "coverage_checklist": [
                    "The Pain Point: Drowning in the Noise",
                    "The Infrastructure Shift: SeekAITool as the Filter",
                    "The Geek Reality (Code Snippet)",
                    "Let's Argue",
                ],
                "sections": [
                    {
                        "heading": "The Pain Point: Drowning in the Noise",
                        "summary": "Why isolated wrappers fail in noisy tool ecosystems.",
                        "paragraphs": ["Noise", "Protocol mismatch"],
                        "code_refs": [],
                    },
                    {
                        "heading": "The Infrastructure Shift: SeekAITool as the Filter",
                        "summary": "SeekAITool acts as a registry and filter for MCP-capable tools.",
                        "paragraphs": ["Registry", "Filter"],
                        "code_refs": [],
                    },
                    {
                        "heading": "The Geek Reality (Code Snippet)",
                        "summary": "A Python example mounts a verified MCP endpoint into a local swarm.",
                        "paragraphs": ["OPTIONS handshake", "mount router"],
                        "code_refs": [0],
                    },
                    {
                        "heading": "Let's Argue",
                        "summary": "The article closes with a direct argument about orchestration replacing wrappers.",
                        "paragraphs": ["Argument", "Boundary"],
                        "code_refs": [],
                    },
                ],
                "code_blocks": [
                    {
                        "language": "python",
                        "code_excerpt": "async def inject_context_to_swarm():",
                        "code_text": "async def inject_context_to_swarm():\n    pass",
                        "kind": "code",
                        "line_count": 2,
                    }
                ],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertEqual(
            fact_pack["coverage_checklist"],
            [
                "痛点：淹没在噪音中的困境",
                "基础设施的转变：SeekAITool 作为过滤器",
                "技术现实（代码片段）",
                "核心论证",
            ],
        )
        self.assertEqual(
            fact_pack["coverage_checklist_source"],
            [
                "The Pain Point: Drowning in the Noise",
                "The Infrastructure Shift: SeekAITool as the Filter",
                "The Geek Reality (Code Snippet)",
                "Let's Argue",
            ],
        )

    def test_build_fact_pack_infers_repo_url_for_project_explainer_from_grounded_facts(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "RAG Isn't Enough — I Built the Missing Context Layer That Makes LLM Systems Work",
                "summary": "A technical deep dive into a context-engine project.",
                "url": "https://towardsdatascience.com/example",
                "source": "towardsdatascience.com",
                "published": "2026-04-14T00:00:00+00:00",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "The code is available at https://github.com/Emmimal/context-engine and the article walks through the architecture.",
                    "paragraphs": ["para1", "para2"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "The article explains a repo-backed context engine.",
                "sections": [
                    {"heading": "Architecture", "summary": "Retriever, reranker, and memory modules."},
                    {"heading": "Benchmark and evaluation", "summary": "Latency and relevance tradeoffs."},
                ],
                "coverage_checklist": ["Architecture", "Benchmark and evaluation"],
            },
            "fact_grounding": {
                "hard_facts": [
                    "文章提供了完整的代码实现链接：https://github.com/Emmimal/context-engine/。"
                ],
                "official_facts": [],
                "context_facts": [],
                "soft_inferences": [],
                "unknowns": [],
                "forbidden_claims": [],
            },
            "web_enrich": {},
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertEqual(fact_pack["github_repo_url"], "https://github.com/Emmimal/context-engine")
        self.assertEqual(fact_pack["github_repo_slug"], "Emmimal/context-engine")
        self.assertEqual(fact_pack["project_subject"], "context-engine")

    def test_build_fact_pack_assigns_github_pool_fields(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "Agent Armor",
                "summary": "An open source runtime for governing agent execution.",
                "url": "https://github.com/example/agent-armor",
                "source": "GitHub",
                "source_category": "github",
                "pool": "github",
                "published": "2026-04-09T00:00:00+00:00",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "Agent Armor adds policy enforcement, audit logs, and command interception.",
                    "paragraphs": ["para1", "para2"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "The repository documents policy enforcement, audit mode, and interception flow.",
                "coverage_checklist": ["Policy engine", "Audit logs", "Command interception"],
                "sections": [
                    {
                        "heading": "Policy engine",
                        "summary": "Rules are evaluated before tools execute.",
                        "paragraphs": ["Rule match", "Allow deny"],
                        "code_refs": [0],
                    }
                ],
                "code_blocks": [
                    {
                        "language": "python",
                        "code_excerpt": "class PolicyEngine:",
                        "code_text": "class PolicyEngine:\n    def evaluate(self, action: str) -> bool:\n        return action != 'rm -rf /'\n",
                        "kind": "code",
                        "line_count": 3,
                        "origin": "repo_file",
                        "source_path": "agent_armor/policy_engine.py",
                    }
                ],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertEqual(fact_pack["primary_pool"], "github")
        self.assertEqual(fact_pack["primary_pool_label"], "GitHub 热门项目")
        self.assertEqual(fact_pack["pool_writing_strategy"], "project_recommend_plus_stack")
        self.assertEqual(fact_pack["github_repo_archetype"], "tooling_repo")
        self.assertEqual(fact_pack["github_code_depth"], "medium")
        self.assertEqual(fact_pack["github_deployment_need"], "required")
        self.assertIn("部署方式", fact_pack["pool_must_cover"])
        self.assertIn("recommendation_points", fact_pack["pool_signal_pack"])
        self.assertTrue(fact_pack["pool_signal_pack"]["recommendation_points"])
        self.assertEqual(fact_pack["github_repo_url"], "https://github.com/example/agent-armor")
        self.assertEqual(fact_pack["github_repo_slug"], "example/agent-armor")
        self.assertEqual(fact_pack["available_code_block_count"], 1)
        self.assertEqual(fact_pack["available_source_code_block_count"], 1)
        self.assertEqual(fact_pack["required_code_block_count"], 1)
        self.assertEqual(fact_pack["required_source_code_block_count"], 1)
        self.assertTrue(fact_pack["github_source_code_blocks"])
        self.assertEqual(fact_pack["github_source_code_blocks"][0]["source_path"], "agent_armor/policy_engine.py")

    def test_build_fact_pack_marks_project_explainer_and_keeps_variant_signals(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "RAG isn't enough: I built the missing context layer that makes LLM systems work",
                "summary": "A deep dive into a GitHub project and its context-engine architecture.",
                "url": "https://towardsdatascience.com/example",
                "source": "Towards Data Science",
                "source_category": "deep_dive",
                "pool": "deep_dive",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "This article explains a repo, system components, pipeline, benchmark and tradeoffs.",
                    "paragraphs": ["para1", "para2"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "A project walkthrough for a context layer system.",
                "sections": [
                    {"heading": "Component architecture", "summary": "Core modules and responsibilities.", "paragraphs": ["a"], "code_refs": []},
                    {"heading": "Benchmark and evaluation", "summary": "Latency and retrieval quality.", "paragraphs": ["b"], "code_refs": []},
                ],
                "code_blocks": [
                    {
                        "language": "python",
                        "code_excerpt": "class ContextEngine:",
                        "code_text": "class ContextEngine:\\n    pass",
                        "kind": "code",
                        "line_count": 2,
                    }
                ],
                "github_repo_context": {"repo_slug": "example/context-engine"},
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertEqual(fact_pack["article_variant"], "project_explainer")
        self.assertTrue(fact_pack["variant_match_reasons"])
        self.assertIn("component_points", fact_pack["pool_signal_pack"])
        self.assertIn("benchmark_points", fact_pack["pool_signal_pack"])
        self.assertTrue(fact_pack["project_subject"])

    def test_build_fact_pack_focuses_collection_repo_on_single_representative_subproject(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "awesome-llm-apps",
                "summary": "A curated collection of runnable LLM app examples.",
                "url": "https://github.com/example/awesome-llm-apps",
                "source": "GitHub Trending",
                "source_category": "github",
                "pool": "github",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "Collection of awesome LLM apps with real source files.",
                    "paragraphs": ["para1", "para2"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "A curated repository of runnable LLM apps.",
                "github_repo_context": {
                    "repo_slug": "example/awesome-llm-apps",
                    "is_collection_repo": True,
                    "focus_root": "advanced_llm_apps/multimodal_video_moment_finder",
                    "focus_label": "multimodal_video_moment_finder",
                },
                "sections": [
                    {
                        "heading": "仓库源码：advanced_llm_apps/multimodal_video_moment_finder/backend/server.py",
                        "summary": "真实仓库文件片段，来自 advanced_llm_apps/multimodal_video_moment_finder/backend/server.py",
                        "paragraphs": ["FastAPI server setup"],
                        "code_refs": [0],
                    },
                    {
                        "heading": "仓库源码：awesome_agent_skills/self-improving-agent-skills/backend/app.py",
                        "summary": "真实仓库文件片段，来自 awesome_agent_skills/self-improving-agent-skills/backend/app.py",
                        "paragraphs": ["Session service"],
                        "code_refs": [1],
                    },
                    {
                        "heading": "仓库部署文件：requirements.txt",
                        "summary": "真实仓库文件片段，来自 advanced_llm_apps/multimodal_video_moment_finder/backend/requirements.txt",
                        "paragraphs": ["Dependencies"],
                        "code_refs": [2],
                    },
                ],
                "code_blocks": [
                    {
                        "language": "python",
                        "code_excerpt": "app = FastAPI()",
                        "code_text": "app = FastAPI()\napp.mount('/frames', StaticFiles(directory='frames'))",
                        "kind": "code",
                        "line_count": 2,
                        "origin": "repo_file",
                        "source_path": "advanced_llm_apps/multimodal_video_moment_finder/backend/server.py",
                    },
                    {
                        "language": "python",
                        "code_excerpt": "sessions = {}",
                        "code_text": "sessions = {}\nclass AnalyzeRequest(BaseModel):\n    session_id: str",
                        "kind": "code",
                        "line_count": 3,
                        "origin": "repo_file",
                        "source_path": "awesome_agent_skills/self-improving-agent-skills/backend/app.py",
                    },
                    {
                        "language": "text",
                        "code_excerpt": "fastapi>=0.115.0",
                        "code_text": "fastapi>=0.115.0\nchromadb>=0.5.0",
                        "kind": "code",
                        "line_count": 2,
                        "origin": "repo_file",
                        "source_path": "advanced_llm_apps/multimodal_video_moment_finder/backend/requirements.txt",
                    },
                ],
                "coverage_checklist": ["Featured AI Projects", "AI Agents", "RAG"],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertTrue(fact_pack["github_is_collection_repo"])
        self.assertEqual(
            fact_pack["github_focus_root"],
            "advanced_llm_apps/multimodal_video_moment_finder",
        )
        self.assertEqual(fact_pack["github_focus_label"], "multimodal_video_moment_finder")
        self.assertEqual(fact_pack["github_repo_archetype"], "collection_repo")
        self.assertEqual(fact_pack["required_code_block_count"], 2)
        self.assertEqual(fact_pack["required_source_code_block_count"], 1)
        self.assertTrue(fact_pack["github_source_code_blocks"])
        self.assertTrue(
            all(
                item["source_path"].startswith("advanced_llm_apps/multimodal_video_moment_finder/")
                for item in fact_pack["github_source_code_blocks"]
            )
        )
        self.assertTrue(fact_pack["deployment_points"])
        self.assertTrue(
            all("advanced_llm_apps/multimodal_video_moment_finder" in item for item in fact_pack["deployment_points"])
        )

    def test_build_fact_pack_infers_collection_focus_from_old_run_code_blocks_without_metadata(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "awesome-llm-apps",
                "summary": "A curated collection of runnable LLM app examples.",
                "url": "https://github.com/example/awesome-llm-apps",
                "source": "GitHub Trending",
                "source_category": "github",
                "pool": "github",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "Collection of awesome LLM apps with real source files.",
                    "paragraphs": ["para1", "para2"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "A curated repository of runnable LLM apps.",
                "sections": [],
                "code_blocks": [
                    {
                        "language": "python",
                        "code_excerpt": "app = FastAPI()",
                        "code_text": "app = FastAPI()\napp.mount('/frames', StaticFiles(directory='frames'))",
                        "kind": "code",
                        "line_count": 24,
                        "origin": "repo_file",
                        "source_path": "advanced_llm_apps/multimodal_video_moment_finder/backend/server.py",
                    },
                    {
                        "language": "python",
                        "code_excerpt": "sessions = {}",
                        "code_text": "sessions = {}\nclass AnalyzeRequest(BaseModel):\n    session_id: str",
                        "kind": "code",
                        "line_count": 12,
                        "origin": "repo_file",
                        "source_path": "awesome_agent_skills/self-improving-agent-skills/backend/app.py",
                    },
                    {
                        "language": "text",
                        "code_excerpt": "fastapi>=0.115.0",
                        "code_text": "fastapi>=0.115.0\nchromadb>=0.5.0",
                        "kind": "code",
                        "line_count": 8,
                        "origin": "repo_file",
                        "source_path": "advanced_llm_apps/multimodal_video_moment_finder/backend/requirements.txt",
                    },
                ],
                "coverage_checklist": [],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertTrue(fact_pack["github_is_collection_repo"])
        self.assertEqual(
            fact_pack["github_focus_root"],
            "advanced_llm_apps/multimodal_video_moment_finder",
        )
        self.assertTrue(
            all(
                item["source_path"].startswith("advanced_llm_apps/multimodal_video_moment_finder/")
                for item in fact_pack["github_source_code_blocks"]
            )
        )

    def test_build_fact_pack_detects_tooling_repo_archetype(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "OpenUI CLI Starter",
                "summary": "A CLI starter template for shipping AI web apps quickly.",
                "url": "https://github.com/example/openui-cli-starter",
                "source": "GitHub",
                "source_category": "github",
                "pool": "github",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "This starter provides CLI setup, Docker compose, and template scaffolding.",
                    "paragraphs": ["para1"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "CLI starter template for AI web apps.",
                "sections": [
                    {"heading": "Quick Start", "summary": "Install the CLI and run dev server.", "paragraphs": ["run npm install"], "code_refs": [0]},
                    {"heading": "Template structure", "summary": "Scaffolded frontend, backend, and config folders.", "paragraphs": ["folders"], "code_refs": [1]},
                ],
                "code_blocks": [
                    {
                        "language": "bash",
                        "code_excerpt": "npx openui init",
                        "code_text": "npx openui init\nnpm run dev",
                        "kind": "command",
                        "line_count": 2,
                        "origin": "repo_file",
                        "source_path": "README.md",
                    },
                    {
                        "language": "yaml",
                        "code_excerpt": "services:",
                        "code_text": "services:\n  web:\n    build: .",
                        "kind": "code",
                        "line_count": 3,
                        "origin": "repo_file",
                        "source_path": "docker-compose.yml",
                    },
                ],
                "coverage_checklist": ["Quick Start", "Template structure"],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertEqual(fact_pack["github_repo_archetype"], "tooling_repo")
        self.assertEqual(fact_pack["github_code_depth"], "medium")
        self.assertEqual(fact_pack["github_deployment_need"], "required")
        self.assertEqual(fact_pack["required_source_code_block_count"], 1)

    def test_build_fact_pack_treats_docs_heavy_workflow_repo_as_tooling_and_counts_true_source_only(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "everything-claude-code",
                "summary": "A workflow playbook for Claude Code commands, specs, and automation.",
                "url": "https://github.com/example/everything-claude-code",
                "source": "GitHub Trending",
                "source_category": "github",
                "pool": "github",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "Includes workflows, slash commands, prompts, and automation scripts for Claude Code teams.",
                    "paragraphs": ["workflow", "commands", "automation"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "Workflow repository for Claude Code with prompts, specs, and scripts.",
                "sections": [
                    {"heading": "Quick Start", "summary": "Use the slash commands and scripts.", "paragraphs": ["commands"], "code_refs": [0, 1]},
                ],
                "code_blocks": [
                    {
                        "language": "markdown",
                        "code_excerpt": "```bash",
                        "code_text": "```bash\nclaude /spec create\n```\n",
                        "kind": "command",
                        "line_count": 3,
                        "origin": "repo_file",
                        "source_path": "docs/commands.md",
                    },
                    {
                        "language": "rust",
                        "code_excerpt": "fn main()",
                        "code_text": "fn main() {\n    println!(\"hello\");\n}\n",
                        "kind": "code",
                        "line_count": 3,
                        "origin": "repo_file",
                        "source_path": "src/main.rs",
                    },
                ],
                "coverage_checklist": ["Quick Start"],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertEqual(fact_pack["github_repo_archetype"], "tooling_repo")
        self.assertEqual(fact_pack["available_source_code_block_count"], 1)
        self.assertEqual(fact_pack["required_source_code_block_count"], 1)
        self.assertEqual(len(fact_pack["github_source_code_blocks"]), 1)
        self.assertEqual(fact_pack["github_source_code_blocks"][0]["source_path"], "src/main.rs")
        self.assertTrue(fact_pack["github_documentation_code_blocks"])

    def test_build_fact_pack_keeps_single_repo_when_readme_mentions_examples(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "open-webui",
                "summary": "User-friendly AI Interface for self-hosted model access.",
                "url": "https://github.com/open-webui/open-webui",
                "source": "GitHub",
                "source_category": "github",
                "pool": "github",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "Open WebUI supports Docker, Kubernetes, and multiple model backends.",
                    "paragraphs": ["para1"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "Self-hosted AI platform with docs, examples, and deployment guides.",
                "sections": [
                    {"heading": "Key Features", "summary": "Supports Ollama, OpenAI-compatible APIs, and docs examples.", "paragraphs": ["features"], "code_refs": []},
                    {"heading": "Quick Start", "summary": "Install with Docker or Kubernetes.", "paragraphs": ["quick start"], "code_refs": [0]},
                ],
                "code_blocks": [
                    {
                        "language": "ts",
                        "code_excerpt": "export async function createClient() {}",
                        "code_text": "export async function createClient() {\n  return fetch('/api/models')\n}\n",
                        "kind": "code",
                        "line_count": 3,
                        "origin": "repo_file",
                        "source_path": "src/lib/apis/index.ts",
                    },
                    {
                        "language": "yaml",
                        "code_excerpt": "services:",
                        "code_text": "services:\n  open-webui:\n    image: ghcr.io/open-webui/open-webui:main",
                        "kind": "code",
                        "line_count": 3,
                        "origin": "repo_file",
                        "source_path": "docker-compose.yml",
                    },
                ],
                "coverage_checklist": ["Key Features", "Quick Start"],
                "github_repo_context": {
                    "is_collection_repo": False,
                    "focus_root": "",
                    "focus_label": "",
                    "files": [
                        {"path": "src/lib/apis/index.ts", "language": "ts", "kind": "code", "summary": "API client"},
                        {"path": "docker-compose.yml", "language": "yaml", "kind": "code", "summary": "Deployment"},
                    ],
                },
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertEqual(fact_pack["github_repo_archetype"], "single_repo")

    def test_build_fact_pack_uses_github_outline_style_coverage_for_single_repo(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "browser-use",
                "summary": "Make websites accessible for AI agents.",
                "url": "https://github.com/browser-use/browser-use",
                "source": "GitHub Trending",
                "source_category": "github",
                "pool": "github",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "Python SDK, browser runtime, and cloud mode.",
                    "paragraphs": ["para1", "para2"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "Browser-use bridges LLM planning with browser execution.",
                "sections": [
                    {
                        "heading": "仓库源码：browser_use/agent/service.py",
                        "summary": "真实仓库文件片段，来自 browser_use/agent/service.py",
                        "paragraphs": ["Agent runtime"],
                        "code_refs": [0],
                    },
                    {
                        "heading": "仓库部署文件：pyproject.toml",
                        "summary": "真实仓库文件片段，来自 pyproject.toml",
                        "paragraphs": ["Install"],
                        "code_refs": [1],
                    },
                ],
                "code_blocks": [
                    {
                        "language": "python",
                        "code_excerpt": "class AgentService:",
                        "code_text": "class AgentService:\n    async def run(self):\n        return True\n",
                        "kind": "code",
                        "line_count": 3,
                        "origin": "repo_file",
                        "source_path": "browser_use/agent/service.py",
                    },
                    {
                        "language": "toml",
                        "code_excerpt": "[project]",
                        "code_text": "[project]\nname='browser-use'\n",
                        "kind": "code",
                        "line_count": 2,
                        "origin": "repo_file",
                        "source_path": "pyproject.toml",
                    },
                ],
                "coverage_checklist": [
                    "🤖 LLM Quickstart",
                    "👋 Human Quickstart",
                    "Demos",
                    "🚀 Template Quickstart",
                ],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertEqual(fact_pack["github_repo_archetype"], "single_repo")
        self.assertIn("关键模块与执行链路", fact_pack["coverage_checklist"])
        self.assertIn("整体架构与技术栈", fact_pack["coverage_checklist"])
        self.assertNotIn("🤖 LLM Quickstart", fact_pack["coverage_checklist"])

    def test_build_pool_writing_blueprint_uses_collection_repo_outline(self) -> None:
        fact_pack = {
            "primary_pool": "github",
            "topic_title": "awesome-llm-apps",
            "github_repo_archetype": "collection_repo",
            "github_repo_archetype_label": "案例集合仓库",
            "github_code_depth": "medium",
            "github_deployment_need": "optional",
            "github_is_collection_repo": True,
            "github_focus_root": "advanced_llm_apps/multimodal_video_moment_finder",
            "github_focus_label": "multimodal_video_moment_finder",
            "pool_must_cover": [],
            "pool_must_avoid": [],
            "pool_title_style": [],
        }

        blueprint = self.service.build_pool_writing_blueprint(
            topic={"title": "awesome-llm-apps"},
            fact_pack=fact_pack,
            audience_key="ai_builder",
            subtype="collection_repo",
        )

        headings = [item["heading"] for item in blueprint["outline_sections"]]
        self.assertEqual(
            headings,
            [
                "仓库定位与使用价值",
                "内容地图与范式分类",
                "为什么值得持续关注",
                "代表案例拆解",
                "如何使用这个仓库",
                "适用边界与采用建议",
                "GitHub 项目链接",
            ],
        )

    def test_build_fact_pack_filters_unrelated_context_for_github(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "Firecrawl",
                "summary": "A GitHub repo for web data APIs.",
                "url": "https://github.com/firecrawl/firecrawl",
                "source": "GitHub",
                "source_category": "github",
                "pool": "github",
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "Firecrawl provides search, scrape, and interact endpoints.",
                    "paragraphs": ["para1", "para2"],
                },
                "related": [
                    {
                        "title": "MiniMax News",
                        "source": "MiniMax News",
                        "url": "https://news.minimax.io/post",
                        "content_text": "MiniMax Speech 2.5 launch details.",
                    }
                ],
            },
            "top_k": [
                {
                    "title": "MiniMax Speech 2.5",
                    "summary": "A speech model release update.",
                    "url": "https://example.com/minimax-speech",
                    "source": "MiniMax News",
                },
                {
                    "title": "Firecrawl deployment guide",
                    "summary": "How to self-host Firecrawl with Docker.",
                    "url": "https://docs.firecrawl.dev/self-host",
                    "source": "Firecrawl Docs",
                },
            ],
            "source_structure": {
                "lead": "Firecrawl offers hosted API and self-host options.",
                "coverage_checklist": ["Quick Start", "Search", "Scrape", "Interact"],
                "sections": [
                    {
                        "heading": "Quick Start",
                        "summary": "Sign up at firecrawl.dev to get your API key.",
                        "paragraphs": ["Quick start details"],
                        "code_refs": [0],
                    }
                ],
                "code_blocks": [
                    {
                        "language": "bash",
                        "code_excerpt": "firecrawl scrape https://firecrawl.dev",
                        "code_text": "firecrawl scrape https://firecrawl.dev",
                        "kind": "command",
                        "line_count": 1,
                    }
                ],
            },
            "fact_grounding": {
                "hard_facts": ["Firecrawl 是一个开源的 Web 数据 API 项目。"],
                "official_facts": [],
                "context_facts": ["Firecrawl 文档提供自托管部署入口。"],
                "soft_inferences": [],
                "unknowns": [],
                "forbidden_claims": [],
            },
        }

        fact_pack = self.service.build_fact_pack(ctx, audience_key="ai_builder")

        self.assertTrue(all("MiniMax" not in item for item in fact_pack["related_context_signals"]))
        self.assertTrue(any("部署" in item or "Quick Start" in item for item in fact_pack["deployment_points"]))

    def test_blueprint_and_outline_plan_follow_pool_first_strategy_for_github(self) -> None:
        fact_pack = {
            "primary_pool": "github",
            "primary_pool_label": "GitHub 热门项目",
            "pool_writing_strategy": "project_recommend_plus_stack",
            "pool_must_cover": ["一句话定位", "使用场景与目标读者", "为什么是它：创新点与同类差异", "技术栈分层总览", "部署方式", "适用边界与采用建议", "总结", "GitHub 项目链接"],
            "pool_must_avoid": ["只写项目介绍"],
            "pool_title_style": ["标题更偏项目解析 / 工程观察 / 技术栈拆解。"],
            "pool_signal_pack": {
                "recommendation_points": ["Star 增长快，最近一周持续上涨"],
                "scenario_points": ["适合需要运行时治理的 agent 团队"],
                "differentiation_points": ["同时覆盖策略治理和执行拦截"],
                "tech_stack_points": ["Python + FastAPI + Postgres + Playwright"],
                "execution_flow_points": ["入口 API -> planner -> policy engine -> executor"],
                "deployment_points": ["Docker Compose 可用于本地部署"],
            },
            "topic_source": "github.com",
            "published": "2026-04-09T00:00:00+00:00",
            "source_lead": "An agent runtime with strong policy enforcement.",
            "key_points": ["The repo combines runtime governance with a policy engine."],
            "deployment_points": ["Docker Compose 可用于本地部署"],
            "github_repo_url": "https://github.com/example/agent-armor",
            "github_repo_slug": "example/agent-armor",
            "required_code_block_count": 3,
            "section_blueprint": [
                {"heading": "Architecture", "summary": "Components and responsibilities."},
                {"heading": "Execution flow", "summary": "How requests pass through policy and execution."},
            ],
            "implementation_steps": [
                {
                    "title": "Execution flow",
                    "summary": "Request enters planner and policy engine first.",
                    "details": ["planner", "policy"],
                },
            ],
            "architecture_points": [
                {"component": "Policy engine", "responsibility": "Evaluate allow/deny rules before execution."},
            ],
            "code_artifacts": [],
            "coverage_checklist": ["Architecture", "Execution flow", "Policy engine"],
        }

        topic = {
            "title": "Agent Armor",
            "summary": "A GitHub project for agent runtime governance.",
            "url": "https://github.com/example/agent-armor",
            "pool": "github",
        }
        blueprint = self.service.build_pool_writing_blueprint(
            topic=topic,
            fact_pack=fact_pack,
            audience_key="ai_builder",
            subtype="repo_recommendation",
        )
        outline = self.service.build_outline_plan(
            topic=topic,
            fact_pack=fact_pack,
            pool_blueprint=blueprint,
        )

        self.assertEqual(blueprint["pool"], "github")
        self.assertEqual(blueprint["strategy"], "project_recommend_plus_stack")
        self.assertIn("项目定位", "\n".join(blueprint["must_cover"]))
        self.assertIn("为什么值得关注", "\n".join(blueprint["must_cover"]))
        self.assertEqual(outline["pool"], "github")
        self.assertTrue(outline["sections"])
        self.assertEqual(outline["sections"][0]["heading"], "项目定位与核心问题")
        self.assertEqual(outline["sections"][1]["heading"], "为什么值得关注")
        self.assertEqual(outline["sections"][-1]["heading"], "GitHub 项目链接")
        self.assertIn("GitHub 项目链接", "\n".join(outline["writer_notes"]))

    def test_build_write_prompt_for_github_requires_deployment_repo_link_and_code_blocks(self) -> None:
        fact_pack = {
            "primary_pool": "github",
            "primary_pool_label": "GitHub 热门项目",
            "pool_writing_strategy": "project_recommend_plus_stack",
            "pool_must_cover": ["一句话定位", "使用场景与目标读者", "为什么是它：创新点与同类差异", "技术栈分层总览", "部署方式", "适用边界与采用建议", "总结", "GitHub 项目链接"],
            "pool_must_avoid": ["只写项目介绍"],
            "pool_title_style": ["标题默认是 项目解析 / 技术栈拆解 / 工程观察。"],
            "pool_signal_pack": {
                "scenario_points": ["适合需要给 AI agent 接入网页搜索和抓取能力的团队"],
                "differentiation_points": ["同时提供 Search / Scrape / Interact 三类统一接口"],
                "tech_stack_points": ["Python SDK", "TypeScript SDK", "CLI", "MCP"],
                "execution_flow_points": ["Search -> Scrape -> Interact"],
                "code_points": ["Search：from firecrawl import Firecrawl"],
                "deployment_points": ["Quick Start：注册 firecrawl.dev 获取 API key"],
                "repository_points": ["仓库地址：https://github.com/firecrawl/firecrawl"],
            },
            "topic_source": "github.com",
            "published": "2026-04-09T00:00:00+00:00",
            "source_lead": "Firecrawl provides a hosted service and CLI for web data access.",
            "key_points": ["Firecrawl 提供搜索、抓取和交互能力。"],
            "related_context_signals": [],
            "numbers": ["96%", "3.4"],
            "keywords": ["Firecrawl", "MCP", "CLI"],
            "section_blueprint": [{"heading": "Quick Start", "summary": "Sign up and get an API key."}],
            "implementation_steps": [{"title": "Search", "summary": "Fetch full content from search results.", "details": ["API call", "return markdown"]}],
            "architecture_points": [{"component": "CLI", "responsibility": "Provide a local developer entry point."}],
            "code_artifacts": [
                {"section": "Search", "language": "python", "summary": "Python SDK search example.", "code_text": "from firecrawl import Firecrawl", "kind": "code", "line_count": 1, "origin": "repo_file", "source_path": "apps/sdk/python/firecrawl/client.py"},
                {"section": "Quick Start", "language": "bash", "summary": "CLI scrape command.", "code_text": "firecrawl scrape https://firecrawl.dev", "kind": "command", "line_count": 1},
            ],
            "preserved_command_blocks": [
                {"section": "Quick Start", "language": "bash", "summary": "CLI scrape command.", "code_text": "firecrawl scrape https://firecrawl.dev", "kind": "command", "line_count": 1},
            ],
            "preserved_code_blocks": [
                {"section": "Search", "language": "python", "summary": "Python SDK search example.", "code_text": "from firecrawl import Firecrawl", "kind": "code", "line_count": 1, "origin": "repo_file", "source_path": "apps/sdk/python/firecrawl/client.py"},
            ],
            "github_source_code_blocks": [
                {"section": "Search", "language": "python", "summary": "Python SDK search example.", "code_text": "from firecrawl import Firecrawl", "kind": "code", "line_count": 1, "origin": "repo_file", "source_path": "apps/sdk/python/firecrawl/client.py"},
            ],
            "deployment_points": ["Quick Start：注册 firecrawl.dev 获取 API key"],
            "coverage_checklist": ["Quick Start", "Search", "Scrape"],
            "grounded_hard_facts": ["Firecrawl 是一个开源的 Web 数据 API 项目。"],
            "grounded_official_facts": [],
            "grounded_context_facts": ["该项目的定位是为 AI agent 提供统一的网页数据接入层。"],
            "industry_context_points": ["很多 agent 团队都在寻找更稳定的网页数据接入方式。"],
            "soft_inferences": [],
            "unknowns": [],
            "forbidden_claims": [],
            "evidence_mode": "analysis",
            "github_repo_url": "https://github.com/firecrawl/firecrawl",
            "github_repo_slug": "firecrawl/firecrawl",
            "required_code_block_count": 2,
            "required_source_code_block_count": 1,
        }
        blueprint = self.service.build_pool_writing_blueprint(
            topic={"title": "Firecrawl", "summary": "A GitHub project for web data APIs.", "url": "https://github.com/firecrawl/firecrawl", "pool": "github"},
            fact_pack=fact_pack,
            audience_key="ai_builder",
            subtype="code_explainer",
        )
        outline = self.service.build_outline_plan(
            topic={"title": "Firecrawl", "summary": "A GitHub project for web data APIs.", "url": "https://github.com/firecrawl/firecrawl", "pool": "github"},
            fact_pack=fact_pack,
            pool_blueprint=blueprint,
        )

        prompt = self.service.build_write_prompt(
            topic={"title": "Firecrawl", "summary": "A GitHub project for web data APIs.", "url": "https://github.com/firecrawl/firecrawl", "pool": "github"},
            fact_pack=fact_pack,
            audience_key="ai_builder",
            pool="github",
            subtype="code_explainer",
            pool_blueprint=blueprint,
            outline_plan=outline,
        )

        self.assertIn("[GitHub Special Requirements]", prompt)
        self.assertIn("技术范式、抽象层或工程模式", prompt)
        self.assertIn("技术总结", prompt)
        self.assertIn("Source Path: apps/sdk/python/firecrawl/client.py", prompt)
        self.assertIn("Repo Code Block 1 | File: apps/sdk/python/firecrawl/client.py", prompt)
        self.assertIn("一句话定位", prompt)
        self.assertIn("适用边界与采用建议", prompt)
        self.assertIn("必须单独组织成『部署方式』", prompt)
        self.assertIn("GitHub 项目链接：[firecrawl/firecrawl](https://github.com/firecrawl/firecrawl)", prompt)
        self.assertIn("当前至少要实际整合 2 个代码块或命令块", prompt)

    def test_build_write_prompt_includes_code_preservation_and_verbatim_blocks(self) -> None:
        fact_pack = {
            "topic_source": "realpython.com",
            "published": "2026-04-01T00:00:00+00:00",
            "key_points": ["Ollama runs local models without an API key."],
            "related_topics": [],
            "numbers": [],
            "keywords": ["Ollama", "local models"],
            "source_lead": "This tutorial explains how to install and run Ollama locally.",
            "section_blueprint": [
                {"heading": "Install Ollama", "summary": "Use the install script and verify the version."},
                {"heading": "Run your first model", "summary": "Pull a model and open chat."},
            ],
            "implementation_steps": [
                {"title": "Install Ollama", "summary": "Use the install script.", "details": ["Run curl installer"]},
            ],
            "architecture_points": [],
            "code_artifacts": [
                {
                    "section": "Install Ollama",
                    "language": "bash",
                    "summary": "Install Ollama.",
                    "code_text": "curl -fsSL https://ollama.com/install.sh | sh",
                    "kind": "command",
                    "line_count": 1,
                    "preserve_verbatim": True,
                },
            ],
            "preserved_command_blocks": [
                {
                    "section": "Install Ollama",
                    "language": "bash",
                    "summary": "Install Ollama.",
                    "code_text": "curl -fsSL https://ollama.com/install.sh | sh",
                    "kind": "command",
                    "line_count": 1,
                    "preserve_verbatim": True,
                }
            ],
            "preserved_code_blocks": [
                {
                    "section": "Run your first model",
                    "language": "bash",
                    "summary": "Pull a model and start chat.",
                    "code_text": "ollama pull llama3.2:latest\nollama chat llama3.2:latest",
                    "kind": "command",
                    "line_count": 2,
                    "preserve_verbatim": True,
                }
            ],
            "coverage_checklist": ["Install Ollama", "Run your first model"],
            "grounded_hard_facts": ["Ollama is a local LLM runtime."],
            "grounded_official_facts": [],
            "grounded_context_facts": [],
            "industry_context_points": ["Recent toolchain launches show the same shift toward agent-native workflows."],
            "soft_inferences": [],
            "unknowns": [],
            "forbidden_claims": [],
            "evidence_mode": "tutorial",
        }

        prompt = self.service.build_write_prompt(
            topic={
                "title": "Ollama Tutorial",
                "summary": "How to install Ollama and run a local model.",
                "url": "https://realpython.com/ollama/",
            },
            fact_pack=fact_pack,
            audience_key="ai_builder",
            pool="deep_dive",
            subtype="tutorial",
        )

        self.assertIn("[Code Preservation]", prompt)
        self.assertIn("[Industry Context Integration]", prompt)
        self.assertIn("Do not output a standalone section titled", prompt)
        self.assertIn("Keep command blocks and code blocks verbatim", prompt)
        self.assertIn("Command Block 1 | Section: Install Ollama", prompt)
        self.assertIn("Code Block 1 | Section: Run your first model", prompt)
        self.assertIn("curl -fsSL https://ollama.com/install.sh | sh", prompt)
        self.assertIn("ollama pull llama3.2:latest", prompt)
        self.assertIn("Install Ollama", prompt)
        self.assertIn("Run your first model", prompt)

    def test_build_write_prompt_includes_type_specific_walkthrough_rules(self) -> None:
        fact_pack = {
            "topic_source": "example.com",
            "published": "2026-04-01T00:00:00+00:00",
            "key_points": ["This system coordinates agents through a graph scheduler."],
            "related_topics": [],
            "numbers": ["98.7%"],
            "keywords": ["RAG", "FAISS", "PageIndex"],
            "source_lead": "A technical walkthrough of a hybrid retrieval system.",
            "section_blueprint": [
                {"heading": "System architecture", "summary": "Components and responsibilities."},
                {"heading": "Phase 1: Indexing", "summary": "Build tree and vector anchors."},
            ],
            "implementation_steps": [
                {"title": "Phase 1: Indexing", "summary": "Build a tree and pointer map.", "details": ["Parse headings", "Generate node summaries"]},
            ],
            "architecture_points": [
                {"component": "PageIndex Tree", "responsibility": "Represent document structure."},
            ],
            "code_artifacts": [
                {"section": "Indexing", "language": "python", "summary": "Build the tree", "code_text": "tree = build_tree(doc)", "kind": "code", "line_count": 1},
            ],
            "preserved_command_blocks": [],
            "preserved_code_blocks": [],
            "coverage_checklist": ["System architecture", "Indexing flow", "Pointer mapping"],
            "grounded_hard_facts": ["The system uses a tree plus vector anchors."],
            "grounded_official_facts": [],
            "grounded_context_facts": [],
            "industry_context_points": [],
            "soft_inferences": [],
            "unknowns": [],
            "forbidden_claims": [],
            "evidence_mode": "analysis",
        }

        prompt = self.service.build_write_prompt(
            topic={
                "title": "Proxy-Pointer RAG",
                "summary": "A walkthrough of structure-aware retrieval.",
                "url": "https://example.com/proxy-pointer-rag",
            },
            fact_pack=fact_pack,
            audience_key="ai_builder",
            pool="deep_dive",
            subtype="technical_walkthrough",
        )

        self.assertIn("Proxy-Pointer RAG", prompt)
        self.assertIn("A technical walkthrough of a hybrid retrieval system.", prompt)
        self.assertIn("System architecture", prompt)
        self.assertIn("Phase 1: Indexing", prompt)
        self.assertIn("PageIndex Tree", prompt)
        self.assertIn("Indexing：Build the tree | 代码语言：python", prompt)
        self.assertIn("98.7%", prompt)

    def test_build_write_prompt_prefers_localized_coverage_and_structure_labels(self) -> None:
        fact_pack = {
            "topic_source": "dev.to",
            "published": "2026-04-09T00:00:00+00:00",
            "key_points": ["The article argues MCP-native swarms replace wrapper-style tooling."],
            "related_topics": [],
            "numbers": [],
            "keywords": ["MCP", "SeekAITool", "Agentic Swarms"],
            "source_lead": "A technical post about protocol-native tooling.",
            "section_blueprint": [
                {
                    "heading": "痛点：淹没在噪音中的困境",
                    "source_heading": "The Pain Point: Drowning in the Noise",
                    "summary": "Why isolated wrappers fail in noisy tool ecosystems.",
                },
                {
                    "heading": "核心论证",
                    "source_heading": "Let's Argue",
                    "summary": "Why orchestration becomes the new baseline.",
                },
            ],
            "implementation_steps": [],
            "architecture_points": [],
            "code_artifacts": [],
            "preserved_command_blocks": [],
            "preserved_code_blocks": [],
            "coverage_checklist": ["痛点：淹没在噪音中的困境", "核心论证"],
            "coverage_checklist_source": ["The Pain Point: Drowning in the Noise", "Let's Argue"],
            "coverage_checklist_meta": [
                {
                    "display": "痛点：淹没在噪音中的困境",
                    "source": "The Pain Point: Drowning in the Noise",
                    "summary": "Why isolated wrappers fail in noisy tool ecosystems.",
                },
                {
                    "display": "核心论证",
                    "source": "Let's Argue",
                    "summary": "Why orchestration becomes the new baseline.",
                },
            ],
            "grounded_hard_facts": ["The article frames MCP support as a protocol requirement."],
            "grounded_official_facts": [],
            "grounded_context_facts": [],
            "industry_context_points": [],
            "soft_inferences": [],
            "unknowns": [],
            "forbidden_claims": [],
            "evidence_mode": "analysis",
        }

        prompt = self.service.build_write_prompt(
            topic={
                "title": "Stop Manually Chaining Endpoints",
                "summary": "How MCP and Agentic Swarms are killing wrappers.",
                "url": "https://example.com/mcp-swarms",
            },
            fact_pack=fact_pack,
            audience_key="ai_builder",
            pool="deep_dive",
            subtype="technical_walkthrough",
        )

        self.assertIn("痛点：淹没在噪音中的困境", prompt)
        self.assertIn("核心论证", prompt)
        self.assertNotIn("The Pain Point: Drowning in the Noise", prompt)
        self.assertNotIn("Let's Argue", prompt)

    def test_build_write_prompt_uses_paraphrased_context_signals_instead_of_raw_titles(self) -> None:
        fact_pack = {
            "topic_source": "techcrunch.com",
            "published": "2026-04-07T00:00:00+00:00",
            "key_points": ["Anthropic changed billing for Claude Code third-party harness usage."],
            "related_topics": [
                {
                    "title": "Anthropic is having a month",
                    "summary": "Anthropic recently faced multiple public incidents around pricing and policy changes.",
                    "source": "TechCrunch",
                }
            ],
            "related_context_signals": [
                "来自TechCrunch的相关动态显示：Anthropic近期连续出现多起与价格和策略调整有关的公开事件。"
            ],
            "numbers": [],
            "keywords": ["Anthropic", "Claude Code", "OpenClaw"],
            "source_lead": "Anthropic informed Claude Code subscribers that OpenClaw usage will be billed separately.",
            "section_blueprint": [{"heading": "事件脉络", "summary": "Billing policy changed."}],
            "implementation_steps": [],
            "architecture_points": [],
            "code_artifacts": [],
            "preserved_command_blocks": [],
            "preserved_code_blocks": [],
            "coverage_checklist": ["事件脉络", "变化焦点"],
            "grounded_hard_facts": ["Anthropic changed billing for OpenClaw usage."],
            "grounded_official_facts": [],
            "grounded_context_facts": [],
            "industry_context_points": ["Anthropic近期连续出现多起与价格和策略调整有关的公开事件。"],
            "soft_inferences": [],
            "unknowns": [],
            "forbidden_claims": [],
            "evidence_mode": "analysis",
        }

        prompt = self.service.build_write_prompt(
            topic={
                "title": "Claude Code 与 OpenClaw：调用将单独收费",
                "summary": "Anthropic changed billing for third-party harness usage.",
                "url": "https://techcrunch.com/example",
            },
            fact_pack=fact_pack,
            audience_key="ai_product_manager",
            pool="news",
            subtype="industry_news",
        )

        self.assertIn("Never write external context as 某条目 / 某标题 / 某篇文章指出", prompt)
        self.assertIn("来自TechCrunch的相关动态显示", prompt)
        self.assertNotIn("Anthropic is having a month", prompt)

    def test_build_outline_plan_rewrites_news_headings_into_contentful_titles(self) -> None:
        topic = {
            "title": "Claude Code 与 OpenClaw：调用将单独收费",
            "summary": "Anthropic changed billing for third-party harness usage.",
            "url": "https://techcrunch.com/example",
        }
        fact_pack = {
            "primary_pool": "news",
            "topic_title": topic["title"],
            "source_lead": "Anthropic informed Claude Code subscribers that OpenClaw usage will be billed separately.",
            "pool_signal_pack": {
                "event_points": ["订阅边界被重新划定"],
                "change_points": ["OpenClaw 调用开始单独收费"],
                "impact_points": ["开发者需要重算成本结构"],
                "open_questions": ["后续是否会扩展到更多第三方调用"],
            },
            "key_points": ["Anthropic changed billing for Claude Code third-party harness usage."],
            "grounded_hard_facts": ["OpenClaw usage will be billed separately."],
            "industry_context_points": ["开发者需要重算成本结构"],
            "grounded_context_facts": [],
            "unknowns": ["后续是否会扩展到更多第三方调用"],
            "soft_inferences": [],
        }
        pool_blueprint = {
            "pool": "news",
            "pool_label": "AI 新闻热点",
            "strategy": "news_impact",
            "outline_sections": [
                {"heading": "事件脉络", "purpose": "快速概括事件和关键变化。"},
                {"heading": "变化焦点", "purpose": "提炼最值得关注的变化和信号。"},
                {"heading": "影响判断", "purpose": "解释对开发者、产品或行业的影响。"},
                {"heading": "后续观察", "purpose": "给出验证点、应对动作和观察建议。"},
            ],
        }

        plan = self.service.build_outline_plan(topic=topic, fact_pack=fact_pack, pool_blueprint=pool_blueprint)

        headings = [item["heading"] for item in plan["sections"]]
        self.assertEqual(
            headings,
            [
                "订阅边界被重新划定",
                "OpenClaw 调用开始单独收费",
                "开发者需要重算成本结构",
                "后续是否会扩展到更多第三方调用",
            ],
        )
        self.assertNotIn("事件脉络", headings)
        self.assertNotIn("变化焦点", headings)
        self.assertNotIn("影响判断", headings)
        self.assertNotIn("后续观察", headings)

    def test_build_write_prompt_for_news_uses_rewritten_outline_headings(self) -> None:
        fact_pack = {
            "primary_pool": "news",
            "topic_title": "Claude Code 与 OpenClaw：调用将单独收费",
            "pool_signal_pack": {
                "event_points": ["订阅边界被重新划定"],
                "change_points": ["OpenClaw 调用开始单独收费"],
                "impact_points": ["开发者需要重算成本结构"],
                "open_questions": ["后续是否会扩展到更多第三方调用"],
            },
            "key_points": ["Anthropic changed billing for Claude Code third-party harness usage."],
            "related_context_signals": [],
            "numbers": [],
            "keywords": ["Anthropic", "Claude Code", "OpenClaw"],
            "source_lead": "Anthropic informed Claude Code subscribers that OpenClaw usage will be billed separately.",
            "section_blueprint": [{"heading": "事件脉络", "summary": "Billing policy changed."}],
            "implementation_steps": [],
            "architecture_points": [],
            "code_artifacts": [],
            "preserved_command_blocks": [],
            "preserved_code_blocks": [],
            "coverage_checklist": [],
            "grounded_hard_facts": ["OpenClaw usage will be billed separately."],
            "grounded_official_facts": [],
            "grounded_context_facts": [],
            "industry_context_points": ["开发者需要重算成本结构"],
            "soft_inferences": [],
            "unknowns": ["后续是否会扩展到更多第三方调用"],
            "forbidden_claims": [],
            "evidence_mode": "analysis",
        }

        prompt = self.service.build_write_prompt(
            topic={
                "title": "Claude Code 与 OpenClaw：调用将单独收费",
                "summary": "Anthropic changed billing for third-party harness usage.",
                "url": "https://techcrunch.com/example",
            },
            fact_pack=fact_pack,
            audience_key="ai_product_manager",
            pool="news",
            subtype="industry_news",
        )

        self.assertIn("订阅边界被重新划定", prompt)
        self.assertIn("OpenClaw 调用开始单独收费", prompt)
        self.assertIn("开发者需要重算成本结构", prompt)
        self.assertIn("后续是否会扩展到更多第三方调用", prompt)
        self.assertNotIn("- 事件脉络：先用最短篇幅交代事件、主角和变化点。", prompt)
        self.assertNotIn("- 变化焦点：提炼最值得关注的 2 到 4 个变化，不要平铺原文。", prompt)
        self.assertNotIn("- 影响判断：明确对开发者、产品团队或行业观察者的具体影响。", prompt)
        self.assertNotIn("- 后续观察：给出后续验证点、应对动作或观察建议。", prompt)

    def test_build_write_prompt_for_news_discourages_fixed_product_manager_impact_section(self) -> None:
        fact_pack = {
            "primary_pool": "news",
            "topic_title": "阿尔特曼住宅遇袭后回应《纽约客》",
            "pool_signal_pack": {
                "event_points": ["阿尔特曼回应《纽约客》争议报道。"],
                "change_points": ["线上叙事争议与线下安全风险首次交汇。"],
                "impact_points": ["这件事暴露出 AI 领袖个人争议正在外溢成平台与行业信任问题。"],
                "open_questions": ["后续平台与公众沟通会不会进一步升级安全防护。"],
            },
            "key_points": ["OpenAI CEO Sam Altman responded after a reported attack near his residence."],
            "industry_context_points": ["事件焦点是信任裂痕与风险外溢，不是具体岗位的工作技巧。"],
            "grounded_context_facts": [],
            "soft_inferences": [],
            "unknowns": ["后续是否出现更强的安保与公关动作。"],
        }

        prompt = self.service.build_write_prompt(
            topic={
                "title": "阿尔特曼住宅遇袭后回应《纽约客》：叙事争议与物理风险的首次交汇",
                "summary": "Altman responded after a reported attack and a New Yorker profile controversy.",
                "url": "https://example.com/news",
            },
            fact_pack=fact_pack,
            audience_key="ai_product_manager",
            pool="news",
            subtype="controversy_risk",
        )

        self.assertIn("不要机械加一个『对产品经理的影响』小节", prompt)
        self.assertIn("否则优先写『这件事真正意味着什么』", prompt)

    def test_compact_news_heading_candidate_strips_fixed_product_manager_impact_prefix(self) -> None:
        heading = self.service._compact_news_heading_candidate("对产品经理的影响：AI 领袖争议开始外溢成平台信任问题")

        self.assertEqual(heading, "AI 领袖争议开始外溢成平台信任问题")


if __name__ == "__main__":
    unittest.main()
