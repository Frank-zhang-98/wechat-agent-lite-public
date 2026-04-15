from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from app.core.config import CONFIG
from app.policies import DeepDivePolicy, GithubPolicy, NewsPolicy, PolicyRegistry
from app.services.article_variant_policy import classify_article_variant, extract_project_subject, extract_repo_url
from app.services.humanizer_service import HumanizerService
from app.services.localization_service import LocalizationService


class WritingTemplateService:
    _DISPLAY_HEADING_REPLACEMENTS = (
        ("let's argue", "核心论证"),
        ("lets argue", "核心论证"),
        ("the pain point", "痛点"),
        ("pain point", "痛点"),
        ("drowning in the noise", "淹没在噪音中的困境"),
        ("the infrastructure shift", "基础设施的转变"),
        ("infrastructure shift", "基础设施的转变"),
        ("as the filter", "作为过滤器"),
        ("the geek reality", "技术现实"),
        ("geek reality", "技术现实"),
        ("code snippet", "代码片段"),
        ("what changed", "事件脉络"),
        ("why it matters", "意义判断"),
        ("the real changes that matter", "变化焦点"),
        ("orchestration", "编排"),
        ("integration", "集成"),
        ("mapping", "映射"),
        ("flow", "流程"),
        ("layer", "层"),
        ("component", "组件"),
        ("components", "组件"),
        ("responsibility", "职责"),
        ("responsibilities", "职责"),
        ("step", "步骤"),
    )

    def __init__(self) -> None:
        self.templates = self._load_templates()
        self.humanizer = HumanizerService()
        self.policy_registry = PolicyRegistry([NewsPolicy(), GithubPolicy(), DeepDivePolicy()])

    def _load_templates(self) -> dict[str, Any]:
        path = Path(CONFIG.data_dir).parents[0] / "config" / "writing_templates.yaml"
        if not path.exists():
            path = Path(__file__).resolve().parents[2] / "config" / "writing_templates.yaml"
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def get_audience(self, audience_key: str) -> dict[str, Any]:
        audiences = self.templates.get("audiences", {})
        if audience_key in audiences:
            return {"key": audience_key, **dict(audiences[audience_key] or {})}
        if audiences:
            fallback_key = next(iter(audiences))
            return {"key": fallback_key, **dict(audiences[fallback_key] or {})}
        return {
            "key": audience_key or "default",
            "label": "通用读者",
            "description": "关注 AI 产品、工具和落地价值的通用读者。",
            "focus": ["产品价值", "落地场景", "使用边界"],
            "tone": "专业、清晰、克制",
        }

    def get_content_type(self, content_type: str) -> dict[str, Any]:
        content_types = self.templates.get("content_types", {})
        if content_type in content_types:
            return {"key": content_type, **dict(content_types[content_type] or {})}
        if content_types:
            fallback_key = next(iter(content_types))
            return {"key": fallback_key, **dict(content_types[fallback_key] or {})}
        return {
            "key": content_type or "tool_review",
            "label": "工具 / 产品解读",
            "objective": "把产品是什么、能做什么、为什么值得关注讲清楚。",
            "sections": [],
            "emphasis": [],
        }

    def get_semantic_mode_quality_focus(self, semantic_mode: str) -> list[str]:
        cfg = self.get_content_type(semantic_mode)
        items = [str(item).strip() for item in (cfg.get("quality_focus") or []) if str(item).strip()]
        return items or ["结构是否清晰", "信息是否具体", "语气是否自然"]

    def get_semantic_mode_rewrite_focus(self, semantic_mode: str) -> list[str]:
        cfg = self.get_content_type(semantic_mode)
        items = [str(item).strip() for item in (cfg.get("rewrite_focus") or []) if str(item).strip()]
        return items or ["优先补足信息密度", "优先修复结构松散和表达空泛"]

    def get_pool_profile(self, pool: str) -> dict[str, Any]:
        pool_profiles = self.templates.get("pool_profiles", {})
        if pool in pool_profiles:
            return {"key": pool, **dict(pool_profiles[pool] or {})}
        if pool_profiles:
            fallback_key = next(iter(pool_profiles))
            return {"key": fallback_key, **dict(pool_profiles[fallback_key] or {})}
        return {
            "key": pool or "deep_dive",
            "label": "深度技术解读",
            "strategy": "mechanism_first_walkthrough",
            "objective": "先讲清问题和方法，再拆解机制、实现链路和工程边界。",
            "must_cover": [],
            "must_avoid": [],
            "outline_sections": [],
        }

    def get_pool_quality_focus(self, pool: str) -> list[str]:
        cfg = self.get_pool_profile(pool)
        items = [str(item).strip() for item in (cfg.get("quality_focus") or []) if str(item).strip()]
        return items or ["是否真正贴合当前池子的写作目标"]

    def get_pool_rewrite_focus(self, pool: str) -> list[str]:
        cfg = self.get_pool_profile(pool)
        items = [str(item).strip() for item in (cfg.get("rewrite_focus") or []) if str(item).strip()]
        return items or ["优先把文章拉回当前池子应有的写作视角"]

    @staticmethod
    def _is_news_subtype(*, primary_pool: str, subtype: str) -> bool:
        return str(primary_pool or "").strip() == "news"

    @staticmethod
    def _is_tutorial_subtype(*, primary_pool: str, subtype: str) -> bool:
        return str(primary_pool or "").strip() == "deep_dive" and str(subtype or "").strip() == "tutorial"

    @staticmethod
    def _is_technical_walkthrough_subtype(*, primary_pool: str, subtype: str) -> bool:
        normalized_pool = str(primary_pool or "").strip()
        normalized_subtype = str(subtype or "").strip()
        if normalized_pool == "github":
            return normalized_subtype in {"code_explainer", "stack_analysis"}
        return normalized_subtype in {"technical_walkthrough", "tutorial"}

    def get_subtype_quality_focus(self, *, primary_pool: str, subtype: str) -> list[str]:
        if self._is_news_subtype(primary_pool=primary_pool, subtype=subtype):
            return ["是否讲清事件、变化和影响", "是否保持克制，不把未知内容写成已知事实"]
        if self._is_tutorial_subtype(primary_pool=primary_pool, subtype=subtype):
            return ["步骤是否可执行", "前置条件和验证方式是否写清楚"]
        if self._is_technical_walkthrough_subtype(primary_pool=primary_pool, subtype=subtype):
            return ["结构和实现链路是否完整", "代码职责与工程取舍是否解释清楚"]
        return ["产品定义是否足够清楚", "场景是否具体到可执行"]

    def get_subtype_rewrite_focus(self, *, primary_pool: str, subtype: str) -> list[str]:
        if self._is_news_subtype(primary_pool=primary_pool, subtype=subtype):
            return ["减少新闻复述堆砌，补足变化判断和行动建议", "删除没有依据的技术细节脑补"]
        if self._is_tutorial_subtype(primary_pool=primary_pool, subtype=subtype):
            return ["把操作链写成真正的步骤，不要跳步", "补齐前置条件、输入输出和验证结果"]
        if self._is_technical_walkthrough_subtype(primary_pool=primary_pool, subtype=subtype):
            return ["补齐实现链路中的关键连接处", "减少空泛评价，强化模块职责与边界"]
        return ["补足价值判断和适用边界", "减少抽象套话，强化具体场景"]

    def get_github_repo_archetype_profile(self, archetype: str) -> dict[str, Any]:
        archetypes = self.templates.get("github_repo_archetypes", {})
        if archetype in archetypes:
            return {"key": archetype, **dict(archetypes[archetype] or {})}
        if archetypes:
            fallback_key = next(iter(archetypes))
            return {"key": fallback_key, **dict(archetypes[fallback_key] or {})}
        return {
            "key": archetype or "single_repo",
            "label": "单体系统仓库",
            "objective": "先讲项目定位，再拆解架构、关键链路、部署方式和采用边界。",
            "outline_sections": [],
            "must_cover": [],
            "writer_rules": [],
        }

    def _subtype_prompt_profile(self, *, primary_pool: str, subtype: str) -> dict[str, Any]:
        policy = self.policy_registry.get(primary_pool or "deep_dive")
        profile = policy.profile(subtype)
        seed_cfg = self._subtype_prompt_seed(primary_pool=primary_pool, subtype=subtype)
        objective_map = {
            "news": "鍏堣娓呬簨浠跺拰鍙樺寲锛屽啀鍒ゆ柇褰卞搷銆侀闄╁拰鍚庣画瑙傚療鐐广€?",
            "github": "鍏堣娓呴」鐩畾浣嶅拰閫傜敤浜虹兢锛屽啀鎷嗚В瀹炵幇閾捐矾銆佸伐绋嬪彇鑸嶅拰閮ㄧ讲杈圭晫銆?",
            "deep_dive": "鍏堣娓呴棶棰樺畾涔夛紝鍐嶆媶鏈哄埗銆佸疄鐜伴摼璺拰杈圭晫鏉′欢銆?",
        }
        emphasis: list[str] = []
        if profile.is_news:
            emphasis.append("浼樺厛绐佸嚭鍙樺寲浜嬪疄銆佸奖鍝嶅垽鏂拰鍚庣画瑙傚療鐐癸紝涓嶈鎵╁啓涓嶅瓨鍦ㄧ殑鎶€鏈粏鑺傘€?")
        elif primary_pool == "github":
            emphasis.append("浼樺厛璁叉竻椤圭洰瀹氫綅銆佸疄鐜伴摼璺拰閲囩敤杈圭晫锛屼笉瑕佸啓鎴愮┖娉涚殑浠撳簱浠嬬粛銆?")
        else:
            emphasis.append("浼樺厛鎷嗚В鏂规硶鏈哄埗銆佸疄鐜伴『搴忓拰闄愬埗鏉′欢锛屼笉瑕佸彧鍐欏ぇ鑰屽寲涔嬬殑鎬荤粨銆?")
        return {
            "key": profile.subtype,
            "label": profile.label or subtype or profile.subtype,
            "objective": str(seed_cfg.get("objective") or objective_map.get(primary_pool or "deep_dive", "")),
            "emphasis": self._merge_unique(seed_cfg.get("emphasis", []), emphasis),
            "opening_rules": list(seed_cfg.get("opening_rules") or []),
            "organization_rules": list(seed_cfg.get("organization_rules") or []),
            "evidence_rules": list(seed_cfg.get("evidence_rules") or []),
            "ending_rules": list(seed_cfg.get("ending_rules") or []),
        }

    def _subtype_prompt_seed(self, *, primary_pool: str, subtype: str) -> dict[str, Any]:
        template_key = self._subtype_semantic_mode(primary_pool=primary_pool, subtype=subtype)
        content_types = dict(self.templates.get("content_types") or {})
        seed_cfg = dict(content_types.get(template_key) or {})
        return {"key": template_key, **seed_cfg} if seed_cfg else {}

    @staticmethod
    def _subtype_semantic_mode(*, primary_pool: str, subtype: str) -> str:
        normalized_pool = str(primary_pool or "").strip()
        normalized_subtype = str(subtype or "").strip()
        if normalized_pool == "news":
            return "news_analysis"
        if normalized_subtype == "tutorial":
            return "tutorial"
        if normalized_subtype in {"code_explainer", "stack_analysis", "technical_walkthrough"}:
            return "technical_walkthrough"
        return "tool_review"

    def infer_github_repo_archetype(
        self,
        *,
        topic: dict[str, Any],
        source_structure: dict[str, Any],
        github_is_collection_repo: bool,
        code_artifacts: list[dict[str, Any]],
        deployment_points: list[str],
    ) -> str:
        if github_is_collection_repo:
            return "collection_repo"
        repo_level_parts = [
            str(topic.get("title", "") or ""),
            str(topic.get("summary", "") or ""),
            str(topic.get("url", "") or ""),
        ]
        text_parts = list(repo_level_parts)
        for section in (source_structure.get("sections") or [])[:8]:
            if not isinstance(section, dict):
                continue
            text_parts.extend(
                [
                    str(section.get("heading", "") or ""),
                    str(section.get("summary", "") or ""),
                ]
            )
        for item in code_artifacts[:8]:
            if not isinstance(item, dict):
                continue
            text_parts.extend(
                [
                    str(item.get("section", "") or ""),
                    str(item.get("source_path", "") or ""),
                ]
            )
        text_parts.extend(str(item or "") for item in deployment_points[:6])
        repo_haystack = " ".join(repo_level_parts).lower()
        haystack = " ".join(text_parts).lower()
        tooling_signals = (
            "cli",
            "command line",
            "sdk",
            "framework",
            "runtime",
            "toolkit",
            "starter",
            "template",
            "boilerplate",
            "scaffold",
            "library",
            "plugin",
            "extension",
            "workflow",
            "slash command",
            "skills",
            "skill",
            "playbook",
            "claude code",
            "copilot",
            "prompt",
            "spec",
            "commands",
        )
        if any(signal in haystack for signal in tooling_signals):
            return "tooling_repo"
        if re.search(
            r"\b(cli|command line|sdk|framework|runtime|toolkit|starter|template|boilerplate|scaffold|library|plugin|extension|workflow|prompt|spec)\b",
            haystack,
        ):
            return "tooling_repo"
        if re.search(r"\b(awesome|collection|curated|examples?|showcase|playground)\b", repo_haystack):
            return "collection_repo"
        return "single_repo"

    @staticmethod
    def _is_true_github_source_block(item: dict[str, Any]) -> bool:
        if not isinstance(item, dict):
            return False
        if str(item.get("origin", "") or "").strip() != "repo_file":
            return False
        code_text = str(item.get("code_text", "") or "").strip()
        if not code_text:
            return False
        source_path = str(item.get("source_path", "") or "").strip().lower()
        if not source_path:
            return False
        suffix = Path(source_path).suffix.lower()
        if suffix in {".md", ".mdx", ".txt", ".rst"}:
            return False
        language = str(item.get("language", "") or "").strip().lower()
        if language in {"markdown", "text"} and suffix not in {".json", ".yaml", ".yml", ".toml", ".env", ".ini", ".cfg"}:
            return False
        return True

    @staticmethod
    def infer_github_code_depth(
        *,
        archetype: str,
        available_source_code_block_count: int,
        available_code_block_count: int,
    ) -> str:
        if archetype == "single_repo":
            return "deep" if available_source_code_block_count >= 2 else "medium"
        if archetype == "collection_repo":
            return "medium" if available_source_code_block_count >= 1 else "light"
        if available_source_code_block_count >= 1 or available_code_block_count >= 2:
            return "medium"
        return "light"

    @staticmethod
    def infer_github_deployment_need(*, archetype: str, deployment_points: list[str]) -> str:
        if deployment_points:
            return "required"
        if archetype == "collection_repo":
            return "optional"
        return "required"

    def infer_content_type(
        self,
        topic: dict[str, Any],
        *,
        source_structure: dict[str, Any] | None = None,
        primary_source: dict[str, Any] | None = None,
    ) -> str:
        source_structure = dict(source_structure or {})
        primary_source = dict(primary_source or {})
        source_name = str(topic.get("source", "") or "").strip().lower()
        source_url = str(topic.get("url", "") or "").strip().lower()
        section_text = " ".join(
            " ".join(
                [
                    str(section.get("heading", "") or ""),
                    str(section.get("summary", "") or ""),
                ]
            )
            for section in (source_structure.get("sections") or [])
            if isinstance(section, dict)
        )
        text = " ".join(
            [
                " ".join(
                    str(topic.get(key, "") or "")
                    for key in ("title", "summary", "source", "url", "rerank_reason", "timeliness_profile")
                ),
                str(source_structure.get("lead", "") or ""),
                section_text,
                str(primary_source.get("content_text", "") or "")[:2400],
            ]
        ).lower()

        tutorial_keywords = [
            "教程",
            "指南",
            "实战",
            "工作流",
            "prompt",
            "提示词",
            "how to",
            "guide",
            "tutorial",
            "workflow",
        ]
        news_keywords = [
            "announced",
            "launches",
            "launch",
            "says",
            "said",
            "pricing",
            "price",
            "subscription",
            "support",
            "available now",
            "breaking",
            "news",
            "update",
            "unveils",
            "introduces",
            "raises",
            "cuts",
            "will require",
            "快讯",
            "新闻",
            "动态",
            "宣布",
            "发布",
            "上线",
            "涨价",
            "降价",
            "订阅",
            "支持",
            "更新",
        ]
        industry_keywords = [
            "融资",
            "收购",
            "趋势",
            "财报",
            "报告",
            "industry",
            "analysis",
            "发布会",
            "研究",
            "政策",
        ]
        news_source_markers = [
            "techcrunch",
            "the verge",
            "venturebeat",
            "wired",
            "tom's hardware",
            "arstechnica",
            "engadget",
            "infoq",
            "36kr",
            "机器之心",
            "量子位",
            "钛媒体",
            "新闻",
            "快讯",
        ]
        news_url_markers = [
            "/category/industrynews/",
            "/category/news/",
            "/news/",
            "/fastnews/",
            "techcrunch.com/",
            "theverge.com/",
            "venturebeat.com/",
            "wired.com/",
            "engadget.com/",
            "36kr.com/",
        ]
        news_event_keywords = [
            "officially announced",
            "announced",
            "launches",
            "launched",
            "introduces",
            "introduced",
            "unveiled",
            "release",
            "released",
            "funding",
            "raises",
            "raised",
            "pricing",
            "update",
            "updated",
            "官宣",
            "宣布",
            "发布",
            "推出",
            "上线",
            "正式发布",
            "获融资",
            "融资",
            "新一轮",
            "支持",
            "更新",
        ]
        technical_keywords = [
            "langgraph",
            "mcp",
            "rag",
            "agent",
            "graph",
            "pipeline",
            "workflow",
            "architecture",
            "orchestration",
            "implementation",
            "code",
            "sdk",
            "api",
            "state",
            "session",
            "ttl",
            "renewal",
            "lifecycle",
            "模块",
            "架构",
            "实现",
            "代码",
            "编排",
            "链路",
            "流程",
        ]

        sections = [item for item in (source_structure.get("sections") or []) if isinstance(item, dict)]
        section_count = len(sections)
        code_count = len(source_structure.get("code_blocks") or [])
        coverage_count = len(source_structure.get("coverage_checklist") or [])
        timeliness_profile = str(topic.get("timeliness_profile", "") or "").strip().lower()
        implementation_hits = 0
        architecture_hits = 0
        onboarding_hits = 0
        scenario_hits = 0
        release_section_hits = 0
        for section in sections:
            heading = str(section.get("heading", "") or "").strip()
            summary = str(section.get("summary", "") or "").strip()
            haystack = " ".join(
                [
                    heading,
                    summary,
                ]
            ).lower()
            if re.search(
                r"(step|步骤|阶段|流程|workflow|pipeline|graph|mcp|rag|agent|ttl|renewal|lifecycle)",
                haystack,
                flags=re.IGNORECASE,
            ):
                implementation_hits += 1
            if re.search(
                r"(architecture|架构|模块|组件|agent|mcp|rag|graph|workflow|pipeline|session)",
                haystack,
                flags=re.IGNORECASE,
            ):
                architecture_hits += 1
            if re.search(
                r"^(getting started(?: with)?|use .+ with|chat with .+ on|serve .+ locally|quick start|"
                r"快速开始|使用方式|接入方式|在哪里体验|如何体验|本地部署|本地运行)",
                heading,
                flags=re.IGNORECASE,
            ):
                onboarding_hits += 1
            if re.search(r"^(scenario|benchmark|case study|场景|基准|评测|案例)\b", heading, flags=re.IGNORECASE):
                scenario_hits += 1
            if re.search(
                r"(coming days|rolling out|publicly available|available at|official github|huggingface|modelscope|"
                r"coding plan users|subscribers|quota|promotion|local deployment|本地部署|开放权重|可在.+体验|正式可用)",
                haystack,
                flags=re.IGNORECASE,
            ):
                release_section_hits += 1

        technical_hits = sum(1 for keyword in technical_keywords if keyword in text)
        news_hits = sum(1 for keyword in news_keywords if keyword in text)
        news_source_hits = sum(1 for keyword in news_source_markers if keyword in text)
        news_url_hits = sum(1 for keyword in news_url_markers if keyword in source_url)
        news_event_hits = sum(1 for keyword in news_event_keywords if keyword in text)
        tutorial_hits = sum(1 for keyword in tutorial_keywords if keyword in text)
        explicit_news_url = news_url_hits >= 1
        newsy_source_context = news_source_hits >= 1 or any(
            marker in source_name for marker in ("雷峰网", "leiphone", "techcrunch", "the verge", "venturebeat", "wired", "engadget", "36kr")
        )
        news_like_without_code = (
            code_count == 0
            and tutorial_hits == 0
            and (
                timeliness_profile == "news"
                or explicit_news_url
                or (newsy_source_context and (news_hits >= 1 or news_event_hits >= 2))
            )
        )
        strong_technical_structure = (
            section_count >= 4
            and (
                implementation_hits >= 2
                or architecture_hits >= 2
                or code_count >= 1
                or coverage_count >= 4
            )
        ) or (
            section_count >= 2
            and code_count >= 1
            and (implementation_hits >= 1 or architecture_hits >= 1 or coverage_count >= 3)
        )
        official_release_like_without_code = (
            code_count == 0
            and section_count >= 4
            and onboarding_hits >= 2
            and (
                scenario_hits >= 1
                or release_section_hits >= 2
                or news_event_hits >= 1
                or "flagship model" in text
            )
        )
        if news_like_without_code and (
            explicit_news_url
            or implementation_hits <= 1
            or architecture_hits <= 2
            or news_event_hits >= 2
        ):
            return "news_analysis"
        if official_release_like_without_code:
            return "news_analysis"
        if (
            news_source_hits >= 1
            and news_hits >= 2
            and code_count == 0
            and implementation_hits <= 1
            and architecture_hits <= 1
        ):
            return "news_analysis"
        if strong_technical_structure and not news_like_without_code and (
            code_count >= 1
            or implementation_hits >= 2
            or (technical_hits >= 3 and architecture_hits >= 2)
        ):
            return "technical_walkthrough"
        if (
            timeliness_profile == "news"
            or (
                news_hits >= 2
                and code_count == 0
                and implementation_hits == 0
                and architecture_hits <= 1
                and section_count <= 4
            )
        ):
            return "news_analysis"
        if tutorial_hits >= 1:
            return "tutorial"
        if any(keyword in text for keyword in industry_keywords):
            return "industry_analysis"
        return "tool_review"

    def infer_primary_pool(
        self,
        topic: dict[str, Any],
        *,
        content_type: str = "",
        source_structure: dict[str, Any] | None = None,
        primary_source: dict[str, Any] | None = None,
        selection_arbitration: dict[str, Any] | None = None,
    ) -> str:
        topic = dict(topic or {})
        source_structure = dict(source_structure or {})
        primary_source = dict(primary_source or {})
        selection_arbitration = dict(selection_arbitration or {})

        explicit_pool = str(
            topic.get("primary_pool")
            or selection_arbitration.get("selected_pool")
            or topic.get("selection_pool")
            or ""
        ).strip()
        if explicit_pool in {"news", "github", "deep_dive"}:
            return explicit_pool

        source = str(topic.get("source", "") or "").strip().lower()
        url = str(topic.get("url", "") or "").strip().lower()
        source_category = str(topic.get("source_category", "") or "").strip().lower()
        timeliness_profile = str(topic.get("timeliness_profile", "") or "").strip().lower()
        text = " ".join(
            [
                str(topic.get("title", "") or ""),
                str(topic.get("summary", "") or ""),
                str(primary_source.get("content_text", "") or "")[:1200],
                " ".join(
                    " ".join(
                        [
                            str(section.get("heading", "") or ""),
                            str(section.get("summary", "") or ""),
                        ]
                    )
                    for section in (source_structure.get("sections") or [])
                    if isinstance(section, dict)
                ),
            ]
        ).lower()

        github_markers = (
            "github.com/",
            "githubusercontent.com/",
            "readme",
            "pyproject.toml",
            "package.json",
            "dockerfile",
            "cargo.toml",
            "go.mod",
        )
        news_markers = (
            "techcrunch",
            "venturebeat",
            "the verge",
            "news",
            "announced",
            "launch",
            "发布",
            "上线",
            "更新",
        )

        if source_category == "github" or "github" in source or any(marker in url for marker in ("github.com/", "githubusercontent.com/")):
            return "github"
        if any(marker in text for marker in github_markers):
            return "github"
        if content_type in {"news_analysis", "industry_analysis"}:
            return "news"
        if timeliness_profile == "news" or any(marker in text for marker in news_markers):
            return "news"
        if content_type in {"tutorial", "technical_walkthrough"}:
            return "deep_dive"
        if content_type == "tool_review":
            if any(marker in source for marker in ("techcrunch", "venturebeat", "机器之心", "量子位", "新智元")):
                return "news"
            if any(marker in url for marker in ("github.com/", "/releases", "/blob/", "/tree/")):
                return "github"
        return "deep_dive"

    def build_fact_pack(self, ctx: dict[str, Any], audience_key: str) -> dict[str, Any]:
        topic = dict(ctx.get("selected_topic") or {})
        related_candidates = list(ctx.get("top_k") or [])
        source_pack = dict(ctx.get("source_pack") or {})
        source_structure = dict(ctx.get("source_structure") or {})
        fact_grounding = dict(ctx.get("fact_grounding") or {})
        web_enrich = dict(ctx.get("web_enrich") or {})
        primary_source = dict(source_pack.get("primary") or {})
        raw_related_sources = [item for item in (source_pack.get("related") or []) if isinstance(item, dict)]
        audience = self.get_audience(audience_key)
        primary_pool = self.infer_primary_pool(
            topic,
            source_structure=source_structure,
            primary_source=primary_source,
            selection_arbitration=dict(ctx.get("selection_arbitration") or {}),
        )
        related_topics, related_sources = self._filter_related_material(
            primary_pool=primary_pool,
            topic=topic,
            related_candidates=related_candidates,
            related_sources=raw_related_sources,
        )

        primary_text = " ".join(str(topic.get(key, "") or "") for key in ("title", "summary", "rerank_reason"))
        primary_text = f"{primary_text} {str(primary_source.get('content_text', '') or '')}".strip()
        related_text = " ".join(
            " ".join(str(item.get(key, "") or "") for key in ("title", "summary")) for item in related_topics
        )
        related_text = (
            f"{related_text} " + " ".join(str(item.get("content_text", "") or "") for item in related_sources)
        ).strip()
        combined_text = f"{primary_text} {related_text}".strip()

        key_points = self._build_key_points(topic, related_topics, primary_source, related_sources)
        grounded_hard_facts = [str(item).strip() for item in (fact_grounding.get("hard_facts") or []) if str(item).strip()]
        grounded_official_facts = [str(item).strip() for item in (fact_grounding.get("official_facts") or []) if str(item).strip()]
        grounded_context_facts = [str(item).strip() for item in (fact_grounding.get("context_facts") or []) if str(item).strip()]
        soft_inferences = [str(item).strip() for item in (fact_grounding.get("soft_inferences") or []) if str(item).strip()]
        unknowns = [str(item).strip() for item in (fact_grounding.get("unknowns") or []) if str(item).strip()]
        forbidden_claims = [str(item).strip() for item in (fact_grounding.get("forbidden_claims") or []) if str(item).strip()]
        related_context_signals = self._build_related_context_signals(related_topics, related_sources)
        industry_context_points = grounded_context_facts[:6] or [
            str(item.get("summary", "") or "").strip()
            for item in related_topics[:3]
            if str(item.get("summary", "") or "").strip()
        ]
        if grounded_hard_facts or grounded_official_facts:
            key_points = (grounded_hard_facts[:4] + grounded_official_facts[:2])[:6]
        numbers = self._extract_numbers(combined_text)
        keywords = self._extract_keywords(combined_text)
        section_blueprint = self._build_section_blueprint(source_structure)
        implementation_steps = self._build_implementation_steps(source_structure)
        architecture_points = self._build_architecture_points(source_structure)
        code_artifacts = self._build_code_artifacts(source_structure)
        preserved_command_blocks = [item for item in code_artifacts if str(item.get("kind", "") or "") == "command"]
        preserved_code_blocks = [item for item in code_artifacts if str(item.get("kind", "") or "") != "command"]
        github_source_code_blocks = [
            item for item in preserved_code_blocks if str(item.get("origin", "") or "") == "repo_file"
        ]
        deployment_points = self._build_deployment_points(
            source_structure=source_structure,
            code_artifacts=code_artifacts,
            grounded_official_facts=grounded_official_facts,
            grounded_context_facts=grounded_context_facts,
        )
        primary_images = self._normalize_images(primary_source.get("images") or [])
        related_images = self._normalize_related_images(related_sources)
        searched_images = self._normalize_web_enrich_images(web_enrich=web_enrich)
        news_image_candidates = self._merge_news_image_candidates(
            primary_images=primary_images,
            related_images=related_images,
            searched_images=searched_images,
        )
        coverage_targets = self._build_coverage_checklist(source_structure)
        coverage_checklist = [str(item.get("display", "") or "").strip() for item in coverage_targets if str(item.get("display", "") or "").strip()]
        coverage_checklist_source = [str(item.get("source", "") or "").strip() for item in coverage_targets if str(item.get("source", "") or "").strip()]
        github_repo_context = dict(source_structure.get("github_repo_context") or {})
        repo_url = self._resolve_github_repo_url(
            topic=topic,
            primary_pool=primary_pool,
            source_structure=source_structure,
            primary_source=primary_source,
            fact_grounding=fact_grounding,
        )
        repo_slug = self._github_repo_slug(repo_url)
        github_is_collection_repo = bool(github_repo_context.get("is_collection_repo"))
        github_focus_root = str(github_repo_context.get("focus_root", "") or "").strip()
        github_focus_label = str(github_repo_context.get("focus_label", "") or "").strip()
        if primary_pool == "github" and (not github_is_collection_repo or not github_focus_root):
            inferred_collection, inferred_focus_root, inferred_focus_label = self._infer_github_focus_from_code_blocks(
                topic=topic,
                github_source_code_blocks=github_source_code_blocks,
            )
            if inferred_collection and inferred_focus_root:
                github_is_collection_repo = True
                github_focus_root = inferred_focus_root
                github_focus_label = inferred_focus_label
        if primary_pool == "github" and github_focus_root:
            focused_repo_blocks = self._filter_github_items_by_focus_root(
                github_source_code_blocks,
                focus_root=github_focus_root,
            )
            if focused_repo_blocks:
                github_source_code_blocks = focused_repo_blocks
            focused_preserved_code_blocks = self._filter_github_items_by_focus_root(
                preserved_code_blocks,
                focus_root=github_focus_root,
            )
            if focused_preserved_code_blocks:
                preserved_code_blocks = focused_preserved_code_blocks
            focused_code_artifacts = self._filter_github_items_by_focus_root(
                code_artifacts,
                focus_root=github_focus_root,
            )
            if focused_code_artifacts:
                code_artifacts = focused_code_artifacts + preserved_command_blocks[:1]
            focused_deployment_points = self._filter_text_points_by_focus_root(
                deployment_points,
                focus_root=github_focus_root,
            )
            if focused_deployment_points:
                deployment_points = focused_deployment_points
        github_documentation_code_blocks = [
            item
            for item in (
                list(github_source_code_blocks)
                + [entry for entry in preserved_code_blocks if isinstance(entry, dict) and str(entry.get("origin", "") or "").strip() == "repo_file"]
                + [entry for entry in preserved_command_blocks if isinstance(entry, dict) and str(entry.get("origin", "") or "").strip() == "repo_file"]
            )
            if not self._is_true_github_source_block(item)
        ]
        github_documentation_code_blocks = github_documentation_code_blocks[:8]
        true_source_code_blocks = [
            item for item in github_source_code_blocks if self._is_true_github_source_block(item)
        ]
        available_code_block_count = len(preserved_command_blocks) + len(preserved_code_blocks)
        available_source_code_block_count = len(true_source_code_blocks)
        if primary_pool == "github":
            github_repo_archetype = self.infer_github_repo_archetype(
                topic=topic,
                source_structure=source_structure,
                github_is_collection_repo=github_is_collection_repo,
                code_artifacts=code_artifacts,
                deployment_points=deployment_points,
            )
            github_archetype_cfg = self.get_github_repo_archetype_profile(github_repo_archetype)
            github_code_depth = self.infer_github_code_depth(
                archetype=github_repo_archetype,
                available_source_code_block_count=available_source_code_block_count,
                available_code_block_count=available_code_block_count,
            )
            github_deployment_need = self.infer_github_deployment_need(
                archetype=github_repo_archetype,
                deployment_points=deployment_points,
            )
            if github_repo_archetype == "single_repo":
                required_code_block_count = min(3, available_code_block_count) if available_code_block_count > 0 else 0
                required_source_code_block_count = min(2, available_source_code_block_count) if available_source_code_block_count > 0 else 0
            elif github_repo_archetype == "collection_repo":
                required_code_block_count = min(2, available_code_block_count) if available_code_block_count > 0 else 0
                required_source_code_block_count = min(1, available_source_code_block_count) if available_source_code_block_count > 0 else 0
            else:
                required_code_block_count = min(2, available_code_block_count) if available_code_block_count > 0 else 0
                required_source_code_block_count = min(1, available_source_code_block_count) if available_source_code_block_count > 0 else 0
            coverage_targets = self._build_github_coverage_targets(
                archetype=github_repo_archetype,
                deployment_need=github_deployment_need,
                section_blueprint=section_blueprint,
                implementation_steps=implementation_steps,
                architecture_points=architecture_points,
                github_source_code_blocks=github_source_code_blocks,
            )
            coverage_checklist = [
                str(item.get("display", "") or "").strip()
                for item in coverage_targets
                if str(item.get("display", "") or "").strip()
            ]
            coverage_checklist_source = [
                str(item.get("source", "") or "").strip()
                for item in coverage_targets
                if str(item.get("source", "") or "").strip()
            ]
        else:
            github_repo_archetype = ""
            github_archetype_cfg = {}
            github_code_depth = ""
            github_deployment_need = ""
            required_code_block_count = 0
            required_source_code_block_count = 0
        policy = self.policy_registry.get(primary_pool)
        subtype_seed = {
            "primary_pool": primary_pool,
            "key_points": key_points,
            "implementation_steps": implementation_steps,
            "architecture_points": architecture_points,
            "code_artifacts": code_artifacts,
            "github_source_code_blocks": true_source_code_blocks,
            "github_repo_archetype": github_repo_archetype,
        }
        subtype = policy.normalize_subtype(
            str(ctx.get("subtype") or topic.get("subtype") or policy.subtype(topic=topic, fact_pack=subtype_seed)).strip()
        )
        subtype_label = policy.subtype_label(subtype)
        pool_cfg = self.get_pool_profile(primary_pool)
        pool_signal_pack = self._build_pool_signal_pack(
            primary_pool=primary_pool,
            topic=topic,
            key_points=key_points,
            section_blueprint=section_blueprint,
            implementation_steps=implementation_steps,
            architecture_points=architecture_points,
            code_artifacts=code_artifacts,
            keywords=keywords,
            grounded_hard_facts=grounded_hard_facts,
            grounded_context_facts=grounded_context_facts,
            related_context_signals=related_context_signals,
            industry_context_points=industry_context_points,
            soft_inferences=soft_inferences,
            unknowns=unknowns,
            numbers=numbers,
            deployment_points=deployment_points,
            article_variant="standard",
        )
        result = {
            "topic_title": str(topic.get("title", "") or ""),
            "topic_summary": str(topic.get("summary", "") or ""),
            "topic_url": str(topic.get("url", "") or ""),
            "topic_source": str(topic.get("source", "") or ""),
            "published": str(topic.get("published", "") or ""),
            "primary_excerpt": str(primary_source.get("content_text", "") or "")[:2400],
            "source_status": str(primary_source.get("status", "") or ""),
            "audience_key": audience["key"],
            "audience_label": audience.get("label", audience["key"]),
            "primary_pool": primary_pool,
            "primary_pool_label": pool_cfg.get("label", primary_pool),
            "subtype": subtype,
            "subtype_label": subtype_label,
            "pool_writing_strategy": pool_cfg.get("strategy", ""),
            "pool_objective": pool_cfg.get("objective", ""),
            "pool_must_cover": [str(item).strip() for item in (pool_cfg.get("must_cover") or []) if str(item).strip()],
            "pool_must_avoid": [str(item).strip() for item in (pool_cfg.get("must_avoid") or []) if str(item).strip()],
            "pool_title_style": [str(item).strip() for item in (pool_cfg.get("title_style") or []) if str(item).strip()],
            "pool_signal_pack": pool_signal_pack,
            "evidence_mode": str(fact_grounding.get("evidence_mode", "") or ""),
            "key_points": key_points,
            "grounded_hard_facts": grounded_hard_facts[:8],
            "grounded_official_facts": grounded_official_facts[:8],
            "grounded_context_facts": grounded_context_facts[:8],
            "industry_context_points": industry_context_points[:8],
            "soft_inferences": soft_inferences[:8],
            "unknowns": unknowns[:8],
            "forbidden_claims": forbidden_claims[:8],
            "source_lead": str(source_structure.get("lead", "") or "")[:1200],
            "section_blueprint": section_blueprint,
            "implementation_steps": implementation_steps,
            "architecture_points": architecture_points,
            "code_artifacts": code_artifacts,
            "preserved_command_blocks": preserved_command_blocks[:8],
            "preserved_code_blocks": preserved_code_blocks[:8],
            "github_source_code_blocks": true_source_code_blocks[:6],
            "github_documentation_code_blocks": github_documentation_code_blocks,
            "deployment_points": deployment_points[:6],
            "github_repo_url": repo_url,
            "github_repo_slug": repo_slug,
            "github_is_collection_repo": github_is_collection_repo,
            "github_focus_root": github_focus_root,
            "github_focus_label": github_focus_label,
            "github_repo_archetype": github_repo_archetype,
            "github_repo_archetype_label": github_archetype_cfg.get("label", github_repo_archetype),
            "github_repo_archetype_objective": github_archetype_cfg.get("objective", ""),
            "github_code_depth": github_code_depth,
            "github_deployment_need": github_deployment_need,
            "available_code_block_count": available_code_block_count,
            "available_source_code_block_count": available_source_code_block_count,
            "required_code_block_count": required_code_block_count,
            "required_source_code_block_count": required_source_code_block_count,
            "primary_images": primary_images[:6],
            "related_images": related_images[:6],
            "news_image_candidates": news_image_candidates[:6],
            "coverage_checklist": coverage_checklist[:12],
            "coverage_checklist_source": coverage_checklist_source[:12],
            "coverage_checklist_meta": coverage_targets[:12],
            "related_topics": related_topics,
            "related_context_signals": related_context_signals[:6],
            "related_excerpts": [
                {
                    "title": str(item.get("title", "") or ""),
                    "url": str(item.get("url", "") or ""),
                    "content_text": str(item.get("content_text", "") or "")[:1200],
                }
                for item in related_sources[:2]
            ],
            "numbers": numbers,
            "keywords": keywords,
        }
        variant_info = classify_article_variant(topic=topic, fact_pack=result)
        article_variant = str(variant_info.get("article_variant", "standard") or "standard")
        result["article_variant"] = article_variant
        result["variant_match_reasons"] = list(variant_info.get("matched_features") or [])
        result["variant_blockers"] = list(variant_info.get("blocked_by") or [])
        result["variant_reason"] = str(variant_info.get("reason", "") or "").strip()
        result["project_subject"] = extract_project_subject(topic=topic, fact_pack=result)
        if article_variant == "project_explainer":
            result["pool_signal_pack"] = self._build_pool_signal_pack(
                primary_pool=primary_pool,
                topic=topic,
                key_points=key_points,
                section_blueprint=section_blueprint,
                implementation_steps=implementation_steps,
                architecture_points=architecture_points,
                code_artifacts=code_artifacts,
                keywords=keywords,
                grounded_hard_facts=grounded_hard_facts,
                grounded_context_facts=grounded_context_facts,
                related_context_signals=related_context_signals,
                industry_context_points=industry_context_points,
                soft_inferences=soft_inferences,
                unknowns=unknowns,
                numbers=numbers,
                deployment_points=deployment_points,
                article_variant=article_variant,
            )
        return result

    def _filter_related_material(
        self,
        *,
        primary_pool: str,
        topic: dict[str, Any],
        related_candidates: list[dict[str, Any]],
        related_sources: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if primary_pool != "github":
            related_topics: list[dict[str, Any]] = []
            seen_urls = {str(topic.get("url", "") or "").strip()}
            for item in related_candidates:
                url = str(item.get("url", "") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                related_topics.append(
                    {
                        "title": str(item.get("title", "") or ""),
                        "summary": str(item.get("summary", "") or ""),
                        "source": str(item.get("source", "") or ""),
                        "url": url,
                        "final_score": item.get("final_score"),
                    }
                )
                if len(related_topics) >= 3:
                    break
            return related_topics, related_sources[:2]

        related_topics: list[dict[str, Any]] = []
        seen_urls = {str(topic.get("url", "") or "").strip()}
        for item in related_candidates:
            url = str(item.get("url", "") or "").strip()
            if not url or url in seen_urls or not self._is_github_context_relevant(topic=topic, item=item):
                continue
            seen_urls.add(url)
            related_topics.append(
                {
                    "title": str(item.get("title", "") or ""),
                    "summary": str(item.get("summary", "") or ""),
                    "source": str(item.get("source", "") or ""),
                    "url": url,
                    "final_score": item.get("final_score"),
                }
            )
            if len(related_topics) >= 3:
                break
        filtered_sources = [item for item in related_sources if self._is_github_context_relevant(topic=topic, item=item)]
        return related_topics, filtered_sources[:2]

    @classmethod
    def _is_github_context_relevant(cls, *, topic: dict[str, Any], item: dict[str, Any]) -> bool:
        repo_url = cls._github_repo_url(topic, primary_pool="github")
        repo_slug = cls._github_repo_slug(repo_url)
        repo_name = repo_slug.split("/")[-1] if repo_slug else ""
        topic_tokens = cls._github_topic_tokens(topic)
        haystack = " ".join(
            str(item.get(key, "") or "")
            for key in ("title", "summary", "source", "url", "content_text")
        ).lower()
        if repo_slug and repo_slug.lower() in haystack:
            return True
        if repo_name and repo_name.lower() in haystack:
            return True
        token_hits = sum(1 for token in topic_tokens if token in haystack)
        return token_hits >= 2

    @staticmethod
    def _github_repo_url(topic: dict[str, Any], *, primary_pool: str) -> str:
        url = str(topic.get("url", "") or "").strip()
        if primary_pool == "github" and "github.com/" in url.lower():
            return url
        return ""

    @classmethod
    def _resolve_github_repo_url(
        cls,
        *,
        topic: dict[str, Any],
        primary_pool: str,
        source_structure: dict[str, Any],
        primary_source: dict[str, Any],
        fact_grounding: dict[str, Any],
    ) -> str:
        direct = cls._github_repo_url(topic, primary_pool=primary_pool)
        if direct:
            return direct
        repo_context = dict(source_structure.get("github_repo_context") or {})
        repo_slug = str(repo_context.get("repo_slug", "") or "").strip()
        if repo_slug:
            return f"https://github.com/{repo_slug}"
        inferred = extract_repo_url(
            topic=topic,
            fact_pack={
                "topic_url": str(topic.get("url", "") or "").strip(),
                "topic_title": str(topic.get("title", "") or "").strip(),
                "topic_summary": str(topic.get("summary", "") or "").strip(),
                "source_lead": str(source_structure.get("lead", "") or "").strip(),
                "primary_excerpt": str(primary_source.get("content_text", "") or "").strip()[:2400],
                "grounded_hard_facts": list(fact_grounding.get("hard_facts") or []),
                "grounded_official_facts": list(fact_grounding.get("official_facts") or []),
                "grounded_context_facts": list(fact_grounding.get("context_facts") or []),
            },
        )
        return inferred

    @staticmethod
    def _github_repo_slug(repo_url: str) -> str:
        url = str(repo_url or "").strip()
        if "github.com/" not in url.lower():
            return ""
        path = urlparse(url).path.strip("/")
        parts = [part for part in path.split("/") if part]
        if len(parts) < 2:
            return ""
        return f"{parts[0]}/{parts[1]}"

    @classmethod
    def _github_topic_tokens(cls, topic: dict[str, Any]) -> list[str]:
        repo_url = cls._github_repo_url(topic, primary_pool="github")
        repo_slug = cls._github_repo_slug(repo_url)
        repo_name = repo_slug.split("/")[-1] if repo_slug else ""
        title = str(topic.get("title", "") or "").strip()
        raw_tokens = re.findall(r"[a-z0-9._+-]{3,}", f"{repo_slug} {repo_name} {title}".lower())
        output: list[str] = []
        seen: set[str] = set()
        for token in raw_tokens:
            cleaned = token.strip("._+-")
            if len(cleaned) < 3 or cleaned in seen:
                continue
            seen.add(cleaned)
            output.append(cleaned)
        return output[:8]

    @staticmethod
    def _github_path_matches_focus_root(path: str, focus_root: str) -> bool:
        normalized_path = str(path or "").strip().strip("/")
        normalized_root = str(focus_root or "").strip().strip("/")
        if not normalized_path or not normalized_root:
            return False
        return normalized_path == normalized_root or normalized_path.startswith(f"{normalized_root}/")

    @staticmethod
    def _github_repo_is_collection_like_from_topic(topic: dict[str, Any]) -> bool:
        text = " ".join(
            str(topic.get(key, "") or "").strip()
            for key in ("title", "summary", "url")
        )
        if not text:
            return False
        return bool(
            re.search(
                r"\b(awesome|collection|curated|examples?|playground|showcase|templates?|starter|boilerplate)\b",
                text,
                flags=re.IGNORECASE,
            )
        )

    @classmethod
    def _github_focus_root_from_path(cls, path: str) -> str:
        normalized = str(path or "").strip().strip("/")
        if not normalized:
            return ""
        parts = [part for part in normalized.split("/") if part]
        if not parts:
            return ""
        service_markers = {
            "backend",
            "frontend",
            "src",
            "app",
            "server",
            "api",
            "core",
            "lib",
            "client",
            "web",
            "ui",
        }
        for idx, part in enumerate(parts):
            if part.lower() in service_markers and idx > 0:
                return "/".join(parts[:idx])
        if len(parts) <= 2:
            return "/".join(parts[:-1]) or normalized
        return "/".join(parts[:-1])

    @classmethod
    def _infer_github_focus_from_code_blocks(
        cls,
        *,
        topic: dict[str, Any],
        github_source_code_blocks: list[dict[str, Any]],
    ) -> tuple[bool, str, str]:
        if not github_source_code_blocks or not cls._github_repo_is_collection_like_from_topic(topic):
            return False, "", ""
        root_scores: dict[str, float] = {}
        for item in github_source_code_blocks:
            path = str(item.get("source_path", "") or "").strip()
            root = cls._github_focus_root_from_path(path)
            if not root:
                continue
            root_scores[root] = root_scores.get(root, 0.0) + max(1.0, float(item.get("line_count", 0) or 0))
        if len(root_scores) < 2:
            return False, "", ""
        focus_root = max(root_scores, key=lambda root: (root_scores.get(root, 0.0), root.count("/")))
        focus_label = focus_root.split("/")[-1]
        return True, focus_root, focus_label

    @classmethod
    def _filter_github_items_by_focus_root(
        cls,
        items: list[dict[str, Any]],
        *,
        focus_root: str,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source_path = str(item.get("source_path", "") or "").strip()
            if source_path and cls._github_path_matches_focus_root(source_path, focus_root):
                output.append(item)
        return output

    @staticmethod
    def _filter_text_points_by_focus_root(points: list[str], *, focus_root: str) -> list[str]:
        normalized_root = str(focus_root or "").strip().strip("/")
        if not normalized_root:
            return list(points)
        return [str(item).strip() for item in points if normalized_root in str(item or "").strip()]

    @classmethod
    def _build_deployment_points(
        cls,
        *,
        source_structure: dict[str, Any],
        code_artifacts: list[dict[str, Any]],
        grounded_official_facts: list[str],
        grounded_context_facts: list[str],
    ) -> list[str]:
        points: list[str] = []
        deployment_pattern = re.compile(
            r"(quick start|quickstart|getting started|部署|安装|运行|接入|self-host|self host|docker|compose|本地|启动|cli|playground|api key)",
            flags=re.IGNORECASE,
        )
        for section in (source_structure.get("sections") or [])[:10]:
            heading = str(section.get("heading", "") or "").strip()
            summary = str(section.get("summary", "") or "").strip()
            haystack = f"{heading} {summary}"
            if not heading or not deployment_pattern.search(haystack):
                continue
            points.append(f"{cls._localize_display_heading(heading)}：{summary}" if summary else cls._localize_display_heading(heading))
        for item in code_artifacts[:8]:
            summary = str(item.get("summary", "") or "").strip()
            code_text = str(item.get("code_text", "") or "").strip().lower()
            if str(item.get("kind", "") or "") != "command":
                continue
            if not deployment_pattern.search(f"{summary} {code_text}"):
                continue
            section = str(item.get("section", "") or "").strip() or "部署命令"
            points.append(f"{section}：{summary or '包含可直接运行的安装或启动命令'}")
        for text in grounded_official_facts[:3] + grounded_context_facts[:2]:
            cleaned = str(text or "").strip()
            if cleaned and deployment_pattern.search(cleaned):
                points.append(cleaned)
        return cls._merge_unique(points)[:6]

    def build_pool_writing_blueprint(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        audience_key: str,
        subtype: str,
    ) -> dict[str, Any]:
        primary_pool = str(fact_pack.get("primary_pool", "") or "").strip() or self.infer_primary_pool(topic)
        policy = self.policy_registry.get(primary_pool)
        resolved_subtype = policy.normalize_subtype(str(subtype or fact_pack.get("subtype") or "").strip())
        profile = policy.profile(resolved_subtype)
        pool_cfg = self.get_pool_profile(primary_pool)
        github_archetype_cfg = (
            self.get_github_repo_archetype_profile(str(fact_pack.get("github_repo_archetype", "") or "single_repo"))
            if primary_pool == "github"
            else {}
        )
        audience = self.get_audience(audience_key)
        outline_sections = self._plan_outline_sections(
            primary_pool=primary_pool,
            subtype=resolved_subtype,
            fact_pack=fact_pack,
            pool_cfg=pool_cfg,
        )

        return {
            "pool": primary_pool,
            "pool_label": pool_cfg.get("label", primary_pool),
            "strategy": pool_cfg.get("strategy", ""),
            "objective": pool_cfg.get("objective", ""),
            "subtype": resolved_subtype,
            "subtype_label": profile.label or resolved_subtype,
            "audience_key": audience["key"],
            "audience_label": audience.get("label", audience["key"]),
            "narrative_role": self._pool_narrative_role_adaptive(
                primary_pool=primary_pool,
                subtype=resolved_subtype,
                fact_pack=fact_pack,
            ),
            "opening_angle": self._pool_opening_angle_adaptive(primary_pool=primary_pool, fact_pack=fact_pack),
            "must_cover": self._merge_unique(
                list(github_archetype_cfg.get("must_cover") or []),
                list(pool_cfg.get("must_cover") or []),
                list(fact_pack.get("pool_must_cover") or []),
            )[:8],
            "must_avoid": self._merge_unique(
                list(pool_cfg.get("must_avoid") or []),
                list(fact_pack.get("pool_must_avoid") or []),
            )[:8],
            "title_style": self._merge_unique(
                list(pool_cfg.get("title_style") or []),
                list(fact_pack.get("pool_title_style") or []),
            )[:6],
            "quality_focus": self._merge_unique(
                self.get_pool_quality_focus(primary_pool),
                self.get_subtype_quality_focus(primary_pool=primary_pool, subtype=resolved_subtype),
            )[:8],
            "rewrite_focus": self._merge_unique(
                self.get_pool_rewrite_focus(primary_pool),
                self.get_subtype_rewrite_focus(primary_pool=primary_pool, subtype=resolved_subtype),
            )[:8],
            "outline_sections": outline_sections,
        }

    def build_outline_plan(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        pool_blueprint: dict[str, Any],
        fact_compress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fact_compress = dict(fact_compress or {})
        primary_pool = str(pool_blueprint.get("pool", "") or fact_pack.get("primary_pool", "") or "deep_dive").strip()
        outline_sections = [item for item in (pool_blueprint.get("outline_sections") or []) if isinstance(item, dict)]
        signal_pack = dict(fact_pack.get("pool_signal_pack") or {})

        sections: list[dict[str, Any]] = []
        for item in outline_sections:
            raw_heading = str(item.get("heading", "") or "").strip()
            purpose = str(item.get("purpose", "") or "").strip()
            if not raw_heading:
                continue
            evidence_points = self._outline_evidence_points_adaptive(
                primary_pool=primary_pool,
                heading=raw_heading,
                fact_pack=fact_pack,
                signal_pack=signal_pack,
                fact_compress=fact_compress,
            )
            heading = self._outline_heading_adaptive(
                primary_pool=primary_pool,
                heading=raw_heading,
                topic=topic,
                fact_pack=fact_pack,
                fact_compress=fact_compress,
                evidence_points=evidence_points,
            )
            sections.append(
                {
                    "heading": heading,
                    "purpose": purpose,
                    "evidence_points": evidence_points,
                }
            )

        return {
            "pool": primary_pool,
            "pool_label": pool_blueprint.get("pool_label", primary_pool),
            "strategy": pool_blueprint.get("strategy", ""),
            "article_intent": self._outline_article_intent_adaptive(primary_pool=primary_pool, fact_pack=fact_pack),
            "sections": sections,
            "section_count": len(sections),
            "writer_notes": self._outline_writer_notes_adaptive(primary_pool=primary_pool, fact_pack=fact_pack),
            "topic_title": str(topic.get("title", "") or ""),
        }

    def _outline_heading_adaptive(
        self,
        *,
        primary_pool: str,
        heading: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        evidence_points: list[str],
    ) -> str:
        if primary_pool != "news":
            return str(heading or "").strip()
        return self._rewrite_news_outline_heading(
            heading=str(heading or "").strip(),
            topic=topic,
            fact_pack=fact_pack,
            fact_compress=fact_compress,
            evidence_points=evidence_points,
        )

    def _rewrite_news_outline_heading(
        self,
        *,
        heading: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        evidence_points: list[str],
    ) -> str:
        heading_key = str(heading or "").strip()
        topic_title = str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip()
        slot = "watch"
        if any(token in heading_key for token in ("事件脉络", "关键信息", "发生了什么")):
            slot = "event"
        elif any(token in heading_key for token in ("变化焦点", "变化", "真正重要的变化", "值得关注")):
            slot = "change"
        elif any(token in heading_key for token in ("影响判断", "影响", "对谁")):
            slot = "impact"
        if any(token in heading_key for token in ("意义判断", "为什么重要", "这件事意味着什么")):
            slot = "impact"

        candidate_groups = {
            "event": self._merge_unique(
                evidence_points,
                fact_compress.get("what_it_is", []),
                [topic_title],
                [str(fact_pack.get("source_lead", "") or "").strip()],
                fact_pack.get("key_points", []),
            ),
            "change": self._merge_unique(
                evidence_points,
                fact_compress.get("key_mechanisms", []),
                fact_pack.get("grounded_hard_facts", []),
                fact_pack.get("key_points", []),
            ),
            "impact": self._merge_unique(
                evidence_points,
                fact_compress.get("concrete_scenarios", []),
                fact_pack.get("industry_context_points", []),
                fact_pack.get("grounded_context_facts", []),
                fact_compress.get("risks", []),
                fact_pack.get("soft_inferences", []),
            ),
            "watch": self._merge_unique(
                evidence_points,
                fact_compress.get("risks", []),
                fact_compress.get("uncertainties", []),
                fact_pack.get("unknowns", []),
                fact_pack.get("soft_inferences", []),
            ),
        }
        for candidate in candidate_groups.get(slot, []):
            compact = self._compact_news_heading_candidate(candidate)
            if compact:
                return compact
        if slot == "impact":
            return "这件事真正意味着什么"
        fallback_map = {
            "event": "这次调整改了哪里",
            "change": "最值得盯住的变化",
            "impact": "影响开始落到谁身上",
            "watch": "接下来盯哪些信号",
        }
        return fallback_map.get(slot, heading_key or "这件事值得继续盯")

    @staticmethod
    def _compact_news_heading_candidate(text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.replace("“", "").replace("”", "").replace('"', "")
        cleaned = re.sub(r"^来自[^：:\n]{1,30}[：:]\s*", "", cleaned)
        cleaned = re.sub(r"^(相关动态|公开信息|官方表述|报道|消息)显示[：:，,\s]*", "", cleaned)
        if "：" in cleaned or ":" in cleaned:
            parts = re.split(r"[：:]", cleaned, maxsplit=1)
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()
                if re.fullmatch(r"(发生了什么|真正重要的变化|对谁有影响|这对谁有影响|对产品经理的影响|对产品团队的影响|这对产品经理意味着什么|现在该关注什么|事件脉络|变化焦点|意义判断|影响判断|后续观察)", left):
                    cleaned = right
                elif 4 <= len(left) <= 24 and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", left):
                    cleaned = left
                elif right:
                    cleaned = right
        cleaned = re.split(r"[；;。！？!?|\n]", cleaned, maxsplit=1)[0].strip()
        cleaned = re.split(r"[，,]", cleaned, maxsplit=1)[0].strip() or cleaned
        cleaned = re.sub(r"^(发生了什么|真正重要的变化|对谁有影响|这对谁有影响|对产品经理的影响|对产品团队的影响|这对产品经理意味着什么|现在该关注什么|事件脉络|变化焦点|意义判断|影响判断|后续观察)[：:\s]*", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip("：:- ")
        if not cleaned:
            return ""
        if not re.search(r"[\u4e00-\u9fff]", cleaned):
            return ""
        if len(cleaned) > 24:
            cleaned = cleaned[:24].rstrip("，,:： ")
        if len(cleaned) < 5:
            return ""
        return cleaned

    def build_write_prompt(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        audience_key: str,
        pool: str = "",
        subtype: str = "",
        pool_blueprint: dict[str, Any] | None = None,
        outline_plan: dict[str, Any] | None = None,
    ) -> str:
        return self._build_write_prompt_pool_first(
            topic=topic,
            fact_pack=fact_pack,
            audience_key=audience_key,
            pool=pool,
            subtype=subtype,
            pool_blueprint=pool_blueprint,
            outline_plan=outline_plan,
        )


    def _build_write_prompt_pool_first(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        audience_key: str,
        pool: str = "",
        subtype: str = "",
        pool_blueprint: dict[str, Any] | None = None,
        outline_plan: dict[str, Any] | None = None,
    ) -> str:
        audience = self.get_audience(audience_key)
        quality = dict(self.templates.get("quality_requirements") or {})
        style = dict(self.templates.get("writing_style") or {})
        constraints = list(self.templates.get("global_constraints") or [])
        primary_pool = str(
            pool
            or (pool_blueprint or {}).get("pool")
            or fact_pack.get("primary_pool")
            or self.infer_primary_pool(topic)
        ).strip()
        resolved_subtype = str(
            subtype
            or (pool_blueprint or {}).get("subtype")
            or fact_pack.get("subtype")
            or ""
        ).strip()
        type_cfg = self._subtype_prompt_profile(primary_pool=primary_pool, subtype=resolved_subtype)
        pool_cfg = self.get_pool_profile(primary_pool)
        pool_blueprint = dict(
            pool_blueprint
            or self.build_pool_writing_blueprint(
                topic=topic,
                fact_pack=fact_pack,
                audience_key=audience_key,
                subtype=resolved_subtype,
            )
        )
        outline_plan = dict(
            outline_plan
            or self.build_outline_plan(
                topic=topic,
                fact_pack=fact_pack,
                pool_blueprint=pool_blueprint,
            )
        )

        opening_rules = self._merge_unique(
            self._type_rules(pool_cfg, "opening_rules"),
            self._type_rules(type_cfg, "opening_rules"),
        )
        organization_rules = self._merge_unique(
            self._type_rules(pool_cfg, "organization_rules"),
            self._type_rules(type_cfg, "organization_rules"),
        )
        evidence_rules = self._merge_unique(
            self._type_rules(pool_cfg, "evidence_rules"),
            self._type_rules(type_cfg, "evidence_rules"),
        )
        ending_rules = self._merge_unique(
            self._type_rules(pool_cfg, "ending_rules"),
            self._type_rules(type_cfg, "ending_rules"),
        )
        dynamic_rules = self._merge_unique(
            self._dynamic_pool_rules_adaptive(
                primary_pool=primary_pool,
                subtype=resolved_subtype,
                fact_pack=fact_pack,
                pool_blueprint=pool_blueprint,
                outline_plan=outline_plan,
            ),
            self._dynamic_subtype_rules(primary_pool=primary_pool, subtype=resolved_subtype, fact_pack=fact_pack),
        )
        humanizer_rules = self.humanizer.preventive_guidance(
            pool=primary_pool,
            subtype=resolved_subtype,
        )

        focus = [str(item) for item in audience.get("focus", []) if str(item).strip()]
        key_points = [str(item) for item in fact_pack.get("key_points", []) if str(item).strip()]
        related_context_signals = [str(item) for item in fact_pack.get("related_context_signals", []) if str(item).strip()]
        numbers = [str(item) for item in fact_pack.get("numbers", []) if str(item).strip()]
        keywords = [str(item) for item in fact_pack.get("keywords", []) if str(item).strip()]
        section_blueprint = [item for item in fact_pack.get("section_blueprint", []) if isinstance(item, dict)]
        implementation_steps = [item for item in fact_pack.get("implementation_steps", []) if isinstance(item, dict)]
        architecture_points = [item for item in fact_pack.get("architecture_points", []) if isinstance(item, dict)]
        code_artifacts = [item for item in fact_pack.get("code_artifacts", []) if isinstance(item, dict)]
        preserved_command_blocks = [item for item in fact_pack.get("preserved_command_blocks", []) if isinstance(item, dict)]
        preserved_code_blocks = [item for item in fact_pack.get("preserved_code_blocks", []) if isinstance(item, dict)]
        github_source_code_blocks = [item for item in fact_pack.get("github_source_code_blocks", []) if isinstance(item, dict)]
        coverage_checklist = [str(item) for item in fact_pack.get("coverage_checklist", []) if str(item).strip()]
        source_lead = str(fact_pack.get("source_lead", "") or "").strip()
        evidence_mode = str(fact_pack.get("evidence_mode", "") or "").strip().lower() or "analysis"
        grounded_hard_facts = [str(item) for item in fact_pack.get("grounded_hard_facts", []) if str(item).strip()]
        grounded_official_facts = [str(item) for item in fact_pack.get("grounded_official_facts", []) if str(item).strip()]
        grounded_context_facts = [str(item) for item in fact_pack.get("grounded_context_facts", []) if str(item).strip()]
        industry_context_points = [str(item) for item in fact_pack.get("industry_context_points", []) if str(item).strip()]
        soft_inferences = [str(item) for item in fact_pack.get("soft_inferences", []) if str(item).strip()]
        unknowns = [str(item) for item in fact_pack.get("unknowns", []) if str(item).strip()]
        forbidden_claims = [str(item) for item in fact_pack.get("forbidden_claims", []) if str(item).strip()]
        signal_pack = dict(fact_pack.get("pool_signal_pack") or {})
        article_variant = str(fact_pack.get("article_variant", "") or "standard").strip() or "standard"
        project_subject = str(fact_pack.get("project_subject", "") or "").strip()
        deployment_points = [str(item) for item in fact_pack.get("deployment_points", []) if str(item).strip()]
        github_repo_url = str(fact_pack.get("github_repo_url", "") or "").strip()
        github_repo_slug = str(fact_pack.get("github_repo_slug", "") or "").strip() or self._github_repo_slug(github_repo_url)
        github_is_collection_repo = bool(fact_pack.get("github_is_collection_repo"))
        github_focus_root = str(fact_pack.get("github_focus_root", "") or "").strip()
        github_focus_label = str(fact_pack.get("github_focus_label", "") or "").strip()
        github_repo_archetype = str(fact_pack.get("github_repo_archetype", "") or "").strip() or "single_repo"
        github_repo_archetype_label = str(fact_pack.get("github_repo_archetype_label", "") or "").strip() or github_repo_archetype
        github_repo_archetype_objective = str(fact_pack.get("github_repo_archetype_objective", "") or "").strip()
        github_code_depth = str(fact_pack.get("github_code_depth", "") or "").strip() or "-"
        github_deployment_need = str(fact_pack.get("github_deployment_need", "") or "").strip() or "-"
        required_code_block_count = int(fact_pack.get("required_code_block_count", 0) or 0)
        required_source_code_block_count = int(fact_pack.get("required_source_code_block_count", 0) or 0)

        section_text = "\n".join(
            f"- {item.get('heading', '')}：{item.get('summary', '')}" for item in section_blueprint
        ) or "- 暂无明确章节结构"
        implementation_steps_text = "\n".join(
            f"- {item.get('title', '')}：{item.get('summary', '')}"
            + (f" | 细节：{'；'.join(item.get('details', [])[:3])}" if item.get("details") else "")
            for item in implementation_steps
        ) or "- 暂无明确实现步骤"
        architecture_text = "\n".join(
            f"- {item.get('component', '')}：{item.get('responsibility', '')}" for item in architecture_points
        ) or "- 暂无明确架构拆解"
        code_text = "\n".join(
            f"- {item.get('section', '') or item.get('language', '代码片段')}：{item.get('summary', '')}"
            + (f" | 代码语言：{item.get('language', '')}" if item.get("language") else "")
            for item in code_artifacts
        ) or "- 暂无明显代码片段"
        outline_text = "\n".join(
            f"- {item.get('heading', '')}：{item.get('purpose', '')}"
            + (
                f" | 证据：{'；'.join(item.get('evidence_points', [])[:3])}"
                if item.get("evidence_points")
                else ""
            )
            for item in (outline_plan.get("sections") or [])
            if isinstance(item, dict)
        ) or "- 暂无提纲"
        structure_strategy = self._build_structure_strategy(
            primary_pool=primary_pool,
            subtype=resolved_subtype,
            section_blueprint=section_blueprint,
            implementation_steps=implementation_steps,
            architecture_points=architecture_points,
            code_artifacts=code_artifacts,
            coverage_checklist=coverage_checklist,
            article_variant=article_variant,
        )
        pool_signal_text = self._format_pool_signal_pack(primary_pool=primary_pool, signal_pack=signal_pack)

        prompt = f"""你是一名专业的中文科技作者，要为微信公众号写一篇高信息密度的技术文章。
[目标读者]
- 读者类型：{audience.get('label', audience_key)}
- 读者描述：{audience.get('description', '')}
- 读者最关心的点：
{self._bullet_block(focus)}

[写作任务]
- 当前选题池：{pool_blueprint.get('pool_label', pool_cfg.get('label', primary_pool))}
- 池子策略：{pool_blueprint.get('strategy', pool_cfg.get('strategy', ''))}
- 池子目标：{pool_blueprint.get('objective', pool_cfg.get('objective', ''))}
- 文章类型：{type_cfg.get('label', resolved_subtype or '-')}
- 文章类型目标：{type_cfg.get('objective', '')}
- 主题：{topic.get('title', '')}
- 原始摘要：{topic.get('summary', '')}
- 原始链接：{topic.get('url', '')}

[写作蓝图]
- 文章角色：{pool_blueprint.get('narrative_role', '')}
- 开场角度：{pool_blueprint.get('opening_angle', '')}
- 标题风格：
{self._bullet_block(pool_blueprint.get('title_style') or [])}
- 必须覆盖：
{self._bullet_block(pool_blueprint.get('must_cover') or [])}
- 必须避免：
{self._bullet_block(pool_blueprint.get('must_avoid') or [])}

[提纲计划]
- 文章意图：{outline_plan.get('article_intent', '')}
- 计划章节：
{outline_text}
- Writer notes：
{self._bullet_block(outline_plan.get('writer_notes') or [])}

[事实包]
- 主来源：{fact_pack.get('topic_source', '-') or '-'}
- 发布时间：{fact_pack.get('published', '-') or '-'}
- 原文导语：{source_lead or '-'}
- 已知关键点：
{self._bullet_block(key_points)}
- 原文章节结构：
{section_text}
- 原文实现步骤：
{implementation_steps_text}
- 原文架构拆解：
{architecture_text}
- 原文代码实现概括：
{code_text}
- 必须覆盖的实现清单：
{self._bullet_block(coverage_checklist)}
- 可直接引用的数字 / 量化信息：
{self._bullet_block(numbers)}
- 关键词：
{self._bullet_block(keywords)}

[池子专属素材]
{pool_signal_text}

[相关线索]
{self._bullet_block(related_context_signals)}

[部署线索]
{self._bullet_block(deployment_points)}

[GitHub 代表案例]
- 仓库画像：{github_repo_archetype_label}
- 仓库画像目标：{github_repo_archetype_objective or "-"}
- 代码拆解深度：{github_code_depth}
- 部署要求：{github_deployment_need}
- 是否为案例集合仓库：{"是" if github_is_collection_repo else "否"}
- 代表性子项目：{github_focus_label or github_focus_root or "-"}
- 代表性子项目路径：{github_focus_root or "-"}

[结构保持策略]
{self._bullet_block(structure_strategy)}

[文章变体]
- article_variant：{article_variant}
- project_subject：{project_subject or "-"}
- structure_mode：{outline_plan.get('structure_mode', 'standard')}

[池子写法]
{self._bullet_block(opening_rules)}

[【该类型的开头策略】]
{self._bullet_block(opening_rules)}

[池子组织方式]
{self._bullet_block(organization_rules)}

[【该类型的组织方式】]
{self._bullet_block(organization_rules)}

[池子证据方式]
{self._bullet_block(evidence_rules)}

[【该类型的论证方式】]
{self._bullet_block(evidence_rules)}

[池子结尾要求]
{self._bullet_block(ending_rules)}

[【该类型的结尾要求】]
{self._bullet_block(ending_rules)}

[运行时补强策略]
{self._bullet_block(dynamic_rules)}

[该类型需要特别强调]
{self._bullet_block(type_cfg.get('emphasis', []) or [])}

[必须包含]
{self._bullet_block(quality.get('must_have', []) or [])}

[必须避免]
{self._bullet_block(quality.get('must_avoid', []) or [])}

[最佳实践]
{self._bullet_block(quality.get('best_practices', []) or [])}

[写作风格]
- 整体语气：{style.get('tone', '')}
- 优先写法：
{self._bullet_block(style.get('prefer', []) or [])}
- 段落结构：
{self._bullet_block(style.get('paragraph_structure', []) or [])}

[自然表达约束]
{self._bullet_block(humanizer_rules)}

[【自然表达约束】]
{self._bullet_block(humanizer_rules)}

[全局约束]
{self._bullet_block(constraints)}

[额外要求]
- 写作时以当前池子的蓝图和提纲为第一约束，以文章类型为第二约束；不要反过来把池子写法冲淡掉。
- 开头第一段必须直接回答“它是什么”和“为什么值得关注”，不要用空泛背景开场。
- 开头必须写成完整、书面的中文陈述句，不要出现“一个……它是如何构建的”“它是什么？它为什么重要？”这类生硬串问句。
- 如果当前池子是 GitHub，正文必须同时覆盖 推荐价值 和 技术栈 / 执行链路，不要退化成项目介绍。
- 如果当前池子是 news，不要脑补技术实现；如果当前池子是 deep_dive，不要写成新闻快评。
- 正文中的二级、三级小标题默认使用中文书面表达；专有名词可以保留，但不要整行保留英文 heading。
- 如果事实包里没有的信息，请不要编造；可以明确写“现有公开信息尚不足以判断”。
- 全文输出为简体中文 Markdown，只输出正文，不要输出解释。"""
        prompt += (
            "\n\n[Fact Grounding]\n"
            f"- evidence_mode: {evidence_mode}\n"
            "- Hard facts:\n"
            f"{self._bullet_block(grounded_hard_facts)}\n"
            "- Official facts:\n"
            f"{self._bullet_block(grounded_official_facts)}\n"
            "- Context facts:\n"
            f"{self._bullet_block(grounded_context_facts)}\n"
            "- Soft inferences:\n"
            f"{self._bullet_block(soft_inferences)}\n"
            "- Unknowns:\n"
            f"{self._bullet_block(unknowns)}\n"
            "- Forbidden claims:\n"
            f"{self._bullet_block(forbidden_claims)}\n"
            "- Use hard_facts and official_facts as the only definite factual basis.\n"
            "- Context facts can only be used for background or comparison, not as direct product facts.\n"
            "- Soft inferences must be written as cautious judgments such as 可能 / 可以推测 / 从公开信息看。\n"
            "- Unknowns must remain unknown; do not fill them in with invented system design.\n"
            "- Forbidden claims must never appear in the final article as facts.\n"
        )
        prompt += (
            "\n\n[Industry Context Integration]\n"
            "- Use context facts and industry context points only as inline analysis, comparison, or background.\n"
            "- Do not output a standalone section titled 相关阅读 / 延伸阅读 / 参考资料 / Related Reading / Further Reading.\n"
            "- When using external context, explicitly connect it to the current topic instead of listing links or titles.\n"
            "- Never write external context as 某条目 / 某标题 / 某篇文章指出 这种论文式注释口吻。\n"
            "- Prefer paraphrasing the external development in your own words, then explain why it matters here.\n"
            "- If a context point is not useful for the current argument, omit it instead of appending it as a reading list.\n"
            "- Industry context points:\n"
            f"{self._bullet_block(industry_context_points)}\n"
        )
        prompt += (
            "\n\n[Code Preservation]\n"
            "- Treat original command/code blocks as article assets, not as summaries.\n"
            "- Keep command blocks and code blocks verbatim whenever possible.\n"
            "- Do not rewrite, simplify, translate, or convert code into pseudo-code.\n"
            "- Place each code block under the most relevant section heading, then explain it before or after the block.\n"
            "- Code blocks do not count toward prose density; keep enough explanation text around them.\n"
            "- Every fenced block must use standard Markdown: opening ```lang on its own line, code on following lines, closing ``` on its own line.\n"
            "- Never put prose, headings, or list items inside a code fence unless they are truly part of the original file content.\n"
        )
        if preserved_command_blocks or preserved_code_blocks:
            prompt += "\n\n[Preserved Blocks]\n"
            for idx, item in enumerate(preserved_command_blocks[:4], start=1):
                language = str(item.get("language", "") or "bash").strip() or "bash"
                section = str(item.get("section", "") or "未指定章节").strip()
                source_path = str(item.get("source_path", "") or "").strip()
                code_text = str(item.get("code_text", "") or "").strip()
                if not code_text:
                    continue
                path_label = f" | Source Path: {source_path}" if source_path else ""
                prompt += f"\nCommand Block {idx} | Section: {section}{path_label}\n```{language}\n{code_text}\n```\n"
            for idx, item in enumerate(preserved_code_blocks[:4], start=1):
                language = str(item.get("language", "") or "text").strip() or "text"
                section = str(item.get("section", "") or "未指定章节").strip()
                source_path = str(item.get("source_path", "") or "").strip()
                code_text = str(item.get("code_text", "") or "").strip()
                if not code_text:
                    continue
                path_label = f" | Source Path: {source_path}" if source_path else ""
                prompt += f"\nCode Block {idx} | Section: {section}{path_label}\n```{language}\n{code_text}\n```\n"
        if primary_pool == "github" and github_source_code_blocks:
            prompt += "\n\n[Source-backed GitHub Code Blocks]\n"
            for idx, item in enumerate(github_source_code_blocks[:4], start=1):
                language = str(item.get("language", "") or "text").strip() or "text"
                source_path = str(item.get("source_path", "") or "").strip() or "unknown"
                code_text = str(item.get("code_text", "") or "").strip()
                if not code_text:
                    continue
                prompt += f"\nRepo Code Block {idx} | File: {source_path}\n```{language}\n{code_text}\n```\n"
        if primary_pool == "github":
            prompt += (
                "\n\n[GitHub Special Requirements]\n"
                "- 开头先用一到两句话完成『一句话定位』，说明这个项目本质上是什么、在解决哪类问题，再进入使用场景。\n"
                "- 第一屏必须让目标读者判断『这是不是自己需要的项目』，第二个核心小节再回答为什么同类项目里值得优先看它。\n"
                "- 技术栈部分必须分层写，不要只列语言名；至少解释 SDK / 服务端 / 集成 / 部署 这类层次里的实际职责。\n"
                "- 核心实现拆解只挑 2 到 4 条最关键链路深拆，并把代码块或命令块嵌入这些步骤中解释，不要平均铺开所有模块。\n"
                "- 如果原始材料里存在安装、启动、Docker、CLI、API key、Quick Start、自托管等线索，必须单独组织成『部署方式』或『部署方式与接入建议』小节。\n"
                "- 在总结之前必须单独交代『适用边界与采用建议』，明确适合谁、代价是什么、哪些场景不适合直接采用。\n"
                f"- 当前至少要实际整合 {max(0, required_code_block_count)} 个代码块或命令块；如果可用块更少，就尽量全部用上。\n"
                f"- 其中至少 {max(0, required_source_code_block_count)} 个非命令代码块必须直接截取自真实仓库文件，并优先使用上面带有 Source Path / File 的片段。\n"
                "- 非部署章节里的代码块必须来自真实仓库源码或配置文件，不要自己补全、翻写、改写、缩写，不能把 README 描述改造成新的代码。\n"
                "- 每个实现类代码块前后最好点出文件路径，例如“在 src/server/app.ts 里，入口先完成……”，让读者知道代码来自仓库哪里。\n"
                f"- 结尾必须附上 GitHub 项目链接，推荐写成：GitHub 项目链接：[{github_repo_slug or topic.get('title', '项目仓库')}]({github_repo_url or topic.get('url', '')})\n"
                "- 联网补充只用于场景说明、背景知识和同类方案对比，且必须和当前仓库强相关；不要把别的热点新闻、无关教程或 unrelated product update 混进正文。\n"
                "- 如果无法从公开材料确认部署细节或架构细节，要明确写出现有公开信息不足，而不是自行补全。\n"
            )
            if github_is_collection_repo and github_focus_root:
                prompt += (
                    f"- 当前仓库是案例集合型项目；“核心实现拆解”和“部署方式与接入建议”必须统一锚定到 `{github_focus_root}` 这个代表性子项目。\n"
                    f"- 在“核心实现拆解”开头直接说明：以下以 `{github_focus_root}` 为代表案例展开，不要把别的子项目再并列写成新的 链路二 / 链路三。\n"
                )
        return prompt

    @staticmethod
    def _merge_unique(*groups: list[Any]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for item in group or []:
                cleaned = str(item or "").strip()
                if not cleaned:
                    continue
                key = re.sub(r"\s+", "", cleaned.lower())
                if key in seen:
                    continue
                seen.add(key)
                output.append(cleaned)
        return output

    def _build_pool_signal_pack(
        self,
        *,
        primary_pool: str,
        topic: dict[str, Any],
        key_points: list[str],
        section_blueprint: list[dict[str, Any]],
        implementation_steps: list[dict[str, Any]],
        architecture_points: list[dict[str, Any]],
        code_artifacts: list[dict[str, Any]],
        keywords: list[str],
        grounded_hard_facts: list[str],
        grounded_context_facts: list[str],
        related_context_signals: list[str],
        industry_context_points: list[str],
        soft_inferences: list[str],
        unknowns: list[str],
        numbers: list[str],
        deployment_points: list[str],
        article_variant: str = "standard",
    ) -> dict[str, list[str]]:
        section_lines = [
            f"{str(item.get('heading', '') or '').strip()}：{str(item.get('summary', '') or '').strip()}"
            for item in section_blueprint
            if str(item.get("heading", "") or "").strip()
        ]
        implementation_lines = [
            f"{str(item.get('title', '') or '').strip()}：{str(item.get('summary', '') or '').strip()}"
            for item in implementation_steps
            if str(item.get("title", "") or "").strip()
        ]
        architecture_lines = [
            f"{str(item.get('component', '') or '').strip()}：{str(item.get('responsibility', '') or '').strip()}"
            for item in architecture_points
            if str(item.get("component", "") or "").strip()
        ]
        code_lines = [
            f"{str(item.get('section', '') or item.get('language', '代码片段')).strip()}：{str(item.get('summary', '') or '').strip()}"
            for item in code_artifacts
            if str(item.get("summary", "") or "").strip()
        ]
        tech_stack = self._merge_unique(
            [str(item.get("language", "") or "").strip() for item in code_artifacts if str(item.get("language", "") or "").strip()],
            [str(item.get("component", "") or "").strip() for item in architecture_points if str(item.get("component", "") or "").strip()],
            keywords,
        )[:8]

        if primary_pool == "news":
            return {
                "event_points": self._merge_unique(grounded_hard_facts[:4], key_points[:4], section_lines[:2])[:6],
                "change_points": self._merge_unique(section_lines[:4], numbers[:3], grounded_hard_facts[:3])[:6],
                "impact_points": self._merge_unique(industry_context_points[:4], grounded_context_facts[:4], related_context_signals[:3])[:6],
                "open_questions": self._merge_unique(unknowns[:4], soft_inferences[:3])[:5],
            }
        if primary_pool == "github":
            repo_url = str(topic.get("url", "") or "").strip()
            repo_signal = [f"仓库地址：{repo_url}"] if repo_url else []
            return {
                "scenario_points": self._merge_unique(grounded_context_facts[:3], section_lines[:3], key_points[:3])[:6],
                "differentiation_points": self._merge_unique(numbers[:4], grounded_context_facts[:4], key_points[:4], related_context_signals[:2])[:7],
                "recommendation_points": self._merge_unique(repo_signal, key_points[:4], numbers[:3])[:6],
                "problem_points": self._merge_unique(section_lines[:3], grounded_hard_facts[:3], key_points[:2])[:5],
                "tech_stack_points": tech_stack[:8],
                "execution_flow_points": self._merge_unique(implementation_lines[:5], architecture_lines[:3], code_lines[:3])[:7],
                "code_points": self._merge_unique(code_lines[:6], implementation_lines[:4])[:7],
                "deployment_points": self._merge_unique(deployment_points[:6], repo_signal)[:6],
                "repository_points": repo_signal[:2],
                "tradeoff_points": self._merge_unique(architecture_lines[:4], soft_inferences[:4], unknowns[:3])[:6],
            }
        signal_pack = {
            "problem_definition_points": self._merge_unique(key_points[:4], grounded_hard_facts[:4], section_lines[:2])[:6],
            "core_mechanism_points": self._merge_unique(architecture_lines[:4], grounded_hard_facts[:4], tech_stack[:4])[:6],
            "implementation_chain_points": self._merge_unique(implementation_lines[:6], code_lines[:4], section_lines[:3])[:8],
            "module_points": self._merge_unique(architecture_lines[:5], code_lines[:5])[:8],
            "limitation_points": self._merge_unique(unknowns[:5], soft_inferences[:4], grounded_context_facts[:3])[:6],
        }
        if article_variant == "project_explainer":
            signal_pack["component_points"] = self._merge_unique(architecture_lines[:6], section_lines[:4])[:8]
            signal_pack["evaluation_points"] = self._merge_unique(numbers[:6], grounded_context_facts[:4], related_context_signals[:3])[:8]
            signal_pack["benchmark_points"] = self._merge_unique(numbers[:6], related_context_signals[:4], section_lines[:3])[:8]
            signal_pack["repo_asset_points"] = self._merge_unique(section_lines[:4], code_lines[:4], tech_stack[:4])[:8]
        return signal_pack

    def _plan_outline_sections(
        self,
        *,
        primary_pool: str,
        subtype: str,
        fact_pack: dict[str, Any],
        pool_cfg: dict[str, Any],
    ) -> list[dict[str, Any]]:
        sections = [dict(item) for item in (pool_cfg.get("outline_sections") or []) if isinstance(item, dict)]
        if primary_pool == "github":
            archetype = str(fact_pack.get("github_repo_archetype", "") or "single_repo").strip() or "single_repo"
            archetype_cfg = self.get_github_repo_archetype_profile(archetype)
            archetype_sections = [
                dict(item)
                for item in (archetype_cfg.get("outline_sections") or [])
                if isinstance(item, dict)
            ]
            if archetype_sections:
                return archetype_sections
        if primary_pool == "deep_dive" and str(subtype or "").strip() == "tutorial":
            return [
                {"heading": "它在解决什么问题", "purpose": "先说清方法目标、适用场景和前提条件。"},
                {"heading": "核心机制", "purpose": "解释方法关键原理和和常见方案的差异。"},
                {"heading": "按步骤落地", "purpose": "沿着实现顺序讲清执行步骤和依赖关系。"},
                {"heading": "关键代码与验证方法", "purpose": "说明配置、代码片段和如何验证结果。"},
                {"heading": "边界与避坑建议", "purpose": "交代常见坑、限制和扩展顺序。"},
            ]
        if primary_pool == "news":
            return [
                {"heading": "事件脉络", "purpose": "快速概括事件和关键变化。"},
                {"heading": "变化焦点", "purpose": "提炼最值得关注的变化和信号。"},
                {"heading": "影响判断", "purpose": "解释对开发者、产品或行业的影响。"},
                {"heading": "后续观察", "purpose": "给出验证点、应对动作和观察建议。"},
            ]
        return sections

    def _pool_narrative_role_adaptive(
        self,
        *,
        primary_pool: str,
        subtype: str,
        fact_pack: dict[str, Any],
    ) -> str:
        if primary_pool != "github":
            return self._pool_narrative_role(primary_pool=primary_pool, subtype=subtype)
        archetype = str(fact_pack.get("github_repo_archetype", "") or "single_repo").strip() or "single_repo"
        if archetype == "collection_repo":
            return "你是技术编辑和选型向导：先解释这个仓库为什么值得收藏，再梳理内容地图，最后只用一个代表案例做适度拆解。"
        if archetype == "tooling_repo":
            return "你是工具评估者和工程顾问：先说明它解决什么痛点、适合谁，再讲技术栈、命令流、扩展方式和接入门槛。"
        return "你既是项目编辑，也是工程 reviewer：先说明项目定位和价值，再按系统结构拆关键链路、技术取舍和部署方式。"

    def _pool_opening_angle_adaptive(self, *, primary_pool: str, fact_pack: dict[str, Any]) -> str:
        if primary_pool != "github":
            return self._pool_opening_angle(primary_pool=primary_pool, fact_pack=fact_pack)
        topic_title = str(fact_pack.get("topic_title", "") or "").strip()
        archetype = str(fact_pack.get("github_repo_archetype", "") or "single_repo").strip() or "single_repo"
        if archetype == "collection_repo":
            return f"先说清 {topic_title or '这个仓库'} 更像样本库、案例集还是学习地图，再直接交代谁最适合从它里面取材、学习或做选型。"
        if archetype == "tooling_repo":
            return f"先用一句话解释 {topic_title or '这个仓库'} 是什么工具/模板，再直接说明它优先解决什么痛点、谁会需要它。"
        return f"先用一句话解释 {topic_title or '这个项目'} 本质上是什么系统，再立即交代它解决的核心问题和为什么值得关注。"

    def _outline_evidence_points_adaptive(
        self,
        *,
        primary_pool: str,
        heading: str,
        fact_pack: dict[str, Any],
        signal_pack: dict[str, Any],
        fact_compress: dict[str, Any],
    ) -> list[str]:
        if primary_pool != "github":
            return self._outline_evidence_points(
                primary_pool=primary_pool,
                heading=heading,
                fact_pack=fact_pack,
                signal_pack=signal_pack,
                fact_compress=fact_compress,
            )
        heading_key = str(heading or "").strip()
        archetype = str(fact_pack.get("github_repo_archetype", "") or "single_repo").strip() or "single_repo"
        focus_points: list[str] = []
        if fact_pack.get("github_is_collection_repo") and fact_pack.get("github_focus_root"):
            focus_label = str(fact_pack.get("github_focus_label", "") or "").strip()
            focus_root = str(fact_pack.get("github_focus_root", "") or "").strip()
            focus_points.append(f"代表性案例：{focus_label or focus_root}（实现与部署只围绕 {focus_root} 展开）")
        if archetype == "collection_repo":
            if "仓库定位" in heading_key or "使用价值" in heading_key:
                return self._merge_unique(
                    focus_points,
                    signal_pack.get("problem_points", []),
                    signal_pack.get("recommendation_points", []),
                    fact_pack.get("key_points", []),
                )[:5]
            if "内容地图" in heading_key or "范式分类" in heading_key:
                return self._merge_unique(
                    focus_points,
                    signal_pack.get("scenario_points", []),
                    signal_pack.get("tech_stack_points", []),
                    fact_pack.get("coverage_checklist", []),
                )[:6]
            if "为什么值得" in heading_key:
                return self._merge_unique(
                    focus_points,
                    signal_pack.get("differentiation_points", []),
                    signal_pack.get("recommendation_points", []),
                    fact_compress.get("key_mechanisms", []),
                )[:5]
            if "代表案例" in heading_key:
                return self._merge_unique(
                    focus_points,
                    signal_pack.get("execution_flow_points", []),
                    signal_pack.get("code_points", []),
                    signal_pack.get("deployment_points", []),
                )[:6]
            if "如何使用" in heading_key:
                return self._merge_unique(
                    focus_points,
                    signal_pack.get("deployment_points", []),
                    signal_pack.get("scenario_points", []),
                    signal_pack.get("tradeoff_points", []),
                )[:5]
            if "适用边界" in heading_key or "采用建议" in heading_key:
                return self._merge_unique(
                    signal_pack.get("tradeoff_points", []),
                    fact_pack.get("unknowns", []),
                    signal_pack.get("scenario_points", []),
                )[:5]
            return self._merge_unique(signal_pack.get("repository_points", []), focus_points)[:4]
        if archetype == "tooling_repo":
            if "工具定位" in heading_key or "核心痛点" in heading_key:
                return self._merge_unique(
                    signal_pack.get("problem_points", []),
                    signal_pack.get("recommendation_points", []),
                    fact_pack.get("key_points", []),
                )[:5]
            if "使用场景" in heading_key or "上手门槛" in heading_key:
                return self._merge_unique(
                    signal_pack.get("scenario_points", []),
                    signal_pack.get("deployment_points", []),
                    signal_pack.get("recommendation_points", []),
                )[:5]
            if "技术栈" in heading_key or "关键能力" in heading_key:
                return self._merge_unique(
                    signal_pack.get("tech_stack_points", []),
                    signal_pack.get("differentiation_points", []),
                    signal_pack.get("code_points", []),
                )[:6]
            if "命令流" in heading_key or "扩展方式" in heading_key:
                return self._merge_unique(
                    signal_pack.get("code_points", []),
                    signal_pack.get("execution_flow_points", []),
                    signal_pack.get("deployment_points", []),
                )[:6]
            if "部署" in heading_key or "接入" in heading_key:
                return self._merge_unique(
                    signal_pack.get("deployment_points", []),
                    fact_pack.get("deployment_points", []),
                    signal_pack.get("scenario_points", []),
                )[:5]
            if "适用边界" in heading_key or "采用建议" in heading_key:
                return self._merge_unique(
                    signal_pack.get("tradeoff_points", []),
                    signal_pack.get("scenario_points", []),
                    fact_pack.get("unknowns", []),
                )[:5]
            return self._merge_unique(signal_pack.get("repository_points", []), signal_pack.get("deployment_points", []))[:4]
        if "项目定位" in heading_key or "核心问题" in heading_key or "一句话定位" in heading_key:
            return self._merge_unique(
                signal_pack.get("problem_points", []),
                signal_pack.get("recommendation_points", []),
                fact_pack.get("key_points", []),
            )[:5]
        if "为什么值得" in heading_key:
            return self._merge_unique(
                signal_pack.get("differentiation_points", []),
                signal_pack.get("recommendation_points", []),
                fact_compress.get("key_mechanisms", []),
            )[:5]
        if "架构" in heading_key or "技术栈" in heading_key:
            return self._merge_unique(signal_pack.get("tech_stack_points", []), signal_pack.get("execution_flow_points", []))[:6]
        if "关键模块" in heading_key or "执行链路" in heading_key or "核心实现" in heading_key:
            return self._merge_unique(
                signal_pack.get("execution_flow_points", []),
                signal_pack.get("code_points", []),
                signal_pack.get("tradeoff_points", []),
                fact_pack.get("coverage_checklist", []),
            )[:6]
        if "工程取舍" in heading_key or "技术总结" in heading_key:
            return self._merge_unique(
                signal_pack.get("tradeoff_points", []),
                signal_pack.get("tech_stack_points", []),
                fact_compress.get("key_mechanisms", []),
            )[:5]
        if "部署" in heading_key or "接入" in heading_key:
            return self._merge_unique(
                signal_pack.get("deployment_points", []),
                fact_pack.get("deployment_points", []),
                fact_compress.get("concrete_scenarios", []),
            )[:5]
        if "适用边界" in heading_key or "采用建议" in heading_key:
            return self._merge_unique(
                signal_pack.get("tradeoff_points", []),
                fact_pack.get("unknowns", []),
                signal_pack.get("scenario_points", []),
            )[:5]
        return self._merge_unique(signal_pack.get("repository_points", []), signal_pack.get("deployment_points", []))[:4]

    def _outline_article_intent_adaptive(self, *, primary_pool: str, fact_pack: dict[str, Any]) -> str:
        if primary_pool != "github":
            return self._outline_article_intent(primary_pool=primary_pool, fact_pack=fact_pack)
        title = str(fact_pack.get("topic_title", "") or "").strip()
        archetype = str(fact_pack.get("github_repo_archetype", "") or "single_repo").strip() or "single_repo"
        if archetype == "collection_repo":
            return f"让读者先理解 {title or '这个仓库'} 作为样本库/地图的价值，再把内容分类和一个代表案例讲清，最后知道如何把它用于学习、选型或找灵感。"
        if archetype == "tooling_repo":
            return f"让读者快速判断 {title or '这个仓库'} 是否适合自己的工作流，再理解它的技术栈、关键能力、上手方式和接入边界。"
        return f"让读者先理解 {title or '这个项目'} 的核心问题和价值，再按系统结构看清它的关键链路、工程取舍、部署方式和采用边界。"

    def _outline_writer_notes_adaptive(self, *, primary_pool: str, fact_pack: dict[str, Any]) -> list[str]:
        if primary_pool != "github":
            return self._outline_writer_notes(primary_pool=primary_pool, fact_pack=fact_pack)
        archetype = str(fact_pack.get("github_repo_archetype", "") or "single_repo").strip() or "single_repo"
        notes = [
            "GitHub 文章必须先建立项目价值，再进入技术解释，不能只做仓库简介。",
            f"当前仓库画像：{fact_pack.get('github_repo_archetype_label', archetype)}；代码拆解深度 = {fact_pack.get('github_code_depth', '-') or '-'}；部署要求 = {fact_pack.get('github_deployment_need', '-') or '-'}。",
        ]
        if archetype == "collection_repo":
            notes.extend(
                [
                    "重点是仓库的样本价值、分类地图和使用路径，不要把多个子项目混写成同一套系统。",
                    "实现与部署只允许围绕一个代表案例展开，别的子项目只能点到为止。",
                ]
            )
        elif archetype == "tooling_repo":
            notes.extend(
                [
                    "优先把使用路径、接入方式、命令流、配置与扩展方式讲清楚，不要为了显得深入而强拆无意义源码。",
                    "如果是 starter/template，要明确哪些部分值得复用、哪些部分需要改造。",
                ]
            )
        else:
            notes.extend(
                [
                    "按系统结构去写：先定位和价值，再讲架构、关键链路、工程取舍、部署和边界。",
                    "关键链路只挑最重要的 2 到 4 条，每条都要补一个技术总结，说明它体现了什么工程组织方式。",
                ]
            )
        if fact_pack.get("github_is_collection_repo") and fact_pack.get("github_focus_root"):
            notes.append(
                f"当前是案例集合型仓库；“代表案例拆解”以及任何实现/部署段落都必须锚定到 `{fact_pack.get('github_focus_root')}`。"
            )
        if fact_pack.get("required_code_block_count"):
            notes.append(f"正文至少整合 {int(fact_pack.get('required_code_block_count') or 0)} 个代码块或命令块。")
        if fact_pack.get("github_repo_url"):
            notes.append("结尾必须附上 GitHub 项目链接。")
        return notes[:12]

    def _dynamic_pool_rules_adaptive(
        self,
        *,
        primary_pool: str,
        subtype: str,
        fact_pack: dict[str, Any],
        pool_blueprint: dict[str, Any],
        outline_plan: dict[str, Any],
    ) -> list[str]:
        if primary_pool != "github":
            return self._dynamic_pool_rules(
                primary_pool=primary_pool,
                subtype=subtype,
                fact_pack=fact_pack,
                pool_blueprint=pool_blueprint,
                outline_plan=outline_plan,
            )
        rules: list[str] = [
            "外部联网背景只能服务当前仓库的场景判断、同类对比或差异分析，和仓库不直接相关的材料宁可不用。",
            "禁止自己发明伪代码、类结构或所谓『基于某设计模式的推测实现』；只允许解释仓库里真实出现的代码、命令、目录和配置。",
            "结尾必须附上 GitHub 项目链接，并用 Markdown 链接形式给出仓库入口。",
        ]
        archetype = str(fact_pack.get("github_repo_archetype", "") or "single_repo").strip() or "single_repo"
        if archetype == "collection_repo":
            rules.extend(
                [
                    "文章顺序优先按 仓库定位与使用价值 -> 内容地图与范式分类 -> 为什么值得持续关注 -> 代表案例拆解 -> 如何使用这个仓库 -> 适用边界与采用建议 -> GitHub 项目链接 展开。",
                    "整篇主任务是解释仓库的样本价值、分类视角和使用路径，而不是把整个仓库写成单体系统源码 walkthrough。",
                    "代表案例拆解只围绕一个代表性子项目展开，代码块和部署线索也只服务这个案例。",
                ]
            )
        elif archetype == "tooling_repo":
            rules.extend(
                [
                    "文章顺序优先按 工具定位与核心痛点 -> 使用场景与上手门槛 -> 技术栈与关键能力 -> 关键命令流或扩展方式 -> 部署或接入方式 -> 适用边界与采用建议 -> GitHub 项目链接 展开。",
                    "重点是上手路径、接入方式、命令流、扩展点和工程价值，不要为了显得深而硬拆底层系统。",
                    "如果项目更像 starter/template，要明确默认结构解决了什么、哪些部分值得复用、哪些部分需要替换。",
                ]
            )
        else:
            rules.extend(
                [
                    "文章顺序优先按 项目定位与核心问题 -> 为什么值得关注 -> 整体架构与技术栈 -> 关键模块与执行链路 -> 工程取舍与技术总结 -> 部署方式与接入建议 -> 适用边界与采用建议 -> GitHub 项目链接 展开。",
                    "关键模块与执行链路只挑 2 到 4 条最关键链路深拆，每一条都要解释代码或命令在整条链路里的作用、依赖和工程取舍。",
                    "每条关键链路都要先概括它属于什么技术范式、抽象层或工程模式，再进入代码细节；不要只做函数说明文。",
                    "每条链路在讲完代码职责后，都要补一小段技术总结，说明这种实现反映出的组织方式、复用策略或维护性取舍。",
                ]
            )
        if fact_pack.get("github_is_collection_repo") and fact_pack.get("github_focus_root"):
            rules.append(
                f"当前仓库属于案例集合型项目；任何实现、部署或命令段落都必须显式说明以下内容以 `{fact_pack.get('github_focus_root')}` 为代表案例展开。"
            )
        required_code_blocks = int(fact_pack.get("required_code_block_count", 0) or 0)
        if required_code_blocks >= 1:
            rules.append(f"当前材料里至少有 {required_code_blocks} 个可用代码块或命令块，正文必须实际整合进去。")
        required_source_code_blocks = int(fact_pack.get("required_source_code_block_count", 0) or 0)
        if required_source_code_blocks >= 1:
            rules.append(f"正文至少要整合 {required_source_code_blocks} 个来自真实仓库文件的源码块。")
        if outline_plan.get("sections"):
            rules.append("正文一级结构优先对齐当前提纲，不要随意换成另一套模板。")
        if pool_blueprint.get("must_cover"):
            rules.append("写作过程中要持续回看当前仓库画像和 must_cover，缺项时优先补足。")
        return rules

    @staticmethod
    def _pool_narrative_role(*, primary_pool: str, subtype: str) -> str:
        if primary_pool == "news":
            return "你不是在复述新闻，而是在帮助读者快速判断变化、影响和观察重点。"
        if primary_pool == "github":
            if str(subtype or "").strip() in {"code_explainer", "stack_analysis"}:
                return "你既是项目编辑，也是工程 reviewer：先解释为什么值得看，再拆它如何实现。"
            return "你要兼顾项目推荐和技术拆解，不能退化成单纯项目介绍。"
        return "你是一名技术讲解者，要把问题、机制、实现链路和边界讲透。"

    @staticmethod
    def _pool_opening_angle(*, primary_pool: str, fact_pack: dict[str, Any]) -> str:
        topic_title = str(fact_pack.get("topic_title", "") or "").strip()
        if primary_pool == "news":
            return f"先用一句话概括 {topic_title or '这件事'}，再直接指出为什么这次变化值得关注。"
        if primary_pool == "github":
            return f"先用一句话概括 {topic_title or '这个项目'} 本质上是什么，再说明它适合谁、为什么值得看。"
        return f"先讲清 {topic_title or '这套方法'} 要解决的技术问题，再进入机制和实现。"

    def _outline_evidence_points(
        self,
        *,
        primary_pool: str,
        heading: str,
        fact_pack: dict[str, Any],
        signal_pack: dict[str, Any],
        fact_compress: dict[str, Any],
    ) -> list[str]:
        heading_key = str(heading or "").strip()
        if primary_pool == "news":
            if any(token in heading_key for token in ("事件脉络", "关键信息", "发生了什么")):
                return self._merge_unique(signal_pack.get("event_points", []), fact_compress.get("what_it_is", []))[:4]
            if any(token in heading_key for token in ("变化焦点", "变化", "值得关注")):
                return self._merge_unique(signal_pack.get("change_points", []), fact_compress.get("key_mechanisms", []))[:4]
            if any(token in heading_key for token in ("影响判断", "影响", "对谁")):
                return self._merge_unique(signal_pack.get("impact_points", []), fact_compress.get("concrete_scenarios", []))[:4]
            return self._merge_unique(signal_pack.get("open_questions", []), fact_compress.get("risks", []), fact_compress.get("uncertainties", []))[:4]
        if primary_pool == "github":
            focus_points = []
            if fact_pack.get("github_is_collection_repo") and fact_pack.get("github_focus_root"):
                focus_label = str(fact_pack.get("github_focus_label", "") or "").strip()
                focus_root = str(fact_pack.get("github_focus_root", "") or "").strip()
                focus_points.append(
                    f"代表性案例：{focus_label or focus_root}（实现与部署段落应统一锚定到 {focus_root}）"
                )
            if "一句话定位" in heading_key:
                return self._merge_unique(
                    focus_points,
                    signal_pack.get("problem_points", []),
                    signal_pack.get("recommendation_points", []),
                    fact_pack.get("key_points", []),
                )[:4]
            if "使用场景" in heading_key or "目标读者" in heading_key:
                return self._merge_unique(
                    signal_pack.get("scenario_points", []),
                    signal_pack.get("problem_points", []),
                    fact_pack.get("key_points", []),
                )[:5]
            if "为什么是它" in heading_key or "创新点" in heading_key or "同类差异" in heading_key or "为什么选它" in heading_key:
                return self._merge_unique(
                    signal_pack.get("differentiation_points", []),
                    signal_pack.get("recommendation_points", []),
                    fact_compress.get("key_mechanisms", []),
                )[:5]
            if "技术栈" in heading_key:
                return self._merge_unique(signal_pack.get("tech_stack_points", []), fact_pack.get("keywords", []))[:5]
            if "核心实现" in heading_key or "执行链路" in heading_key or "拆实现" in heading_key or "代码块" in heading_key:
                return self._merge_unique(
                    focus_points,
                    signal_pack.get("execution_flow_points", []),
                    signal_pack.get("tech_stack_points", []),
                    signal_pack.get("code_points", []),
                    signal_pack.get("tradeoff_points", []),
                    fact_pack.get("coverage_checklist", []),
                )[:6]
            if "部署" in heading_key or "接入" in heading_key:
                return self._merge_unique(
                    focus_points,
                    signal_pack.get("deployment_points", []),
                    fact_pack.get("deployment_points", []),
                    fact_compress.get("concrete_scenarios", []),
                )[:5]
            if "适用边界" in heading_key or "采用建议" in heading_key:
                return self._merge_unique(
                    signal_pack.get("tradeoff_points", []),
                    fact_compress.get("risks", []),
                    fact_pack.get("unknowns", []),
                    signal_pack.get("deployment_points", []),
                )[:5]
            if "总结" in heading_key:
                return self._merge_unique(
                    signal_pack.get("recommendation_points", []),
                    signal_pack.get("tradeoff_points", []),
                    signal_pack.get("scenario_points", []),
                )[:5]
            return self._merge_unique(
                signal_pack.get("repository_points", []),
                signal_pack.get("deployment_points", []),
            )[:4]
        if "技术问题" in heading_key:
            return self._merge_unique(signal_pack.get("problem_definition_points", []), fact_pack.get("key_points", []))[:4]
        if "核心机制" in heading_key:
            return self._merge_unique(signal_pack.get("core_mechanism_points", []), fact_compress.get("key_mechanisms", []))[:5]
        if "链路" in heading_key or "步骤" in heading_key:
            return self._merge_unique(signal_pack.get("implementation_chain_points", []), fact_pack.get("coverage_checklist", []))[:5]
        if "代码" in heading_key or "模块" in heading_key:
            return self._merge_unique(signal_pack.get("module_points", []), fact_pack.get("keywords", []))[:5]
        return self._merge_unique(signal_pack.get("limitation_points", []), fact_pack.get("unknowns", []), fact_compress.get("risks", []))[:4]

    @staticmethod
    def _outline_article_intent(*, primary_pool: str, fact_pack: dict[str, Any]) -> str:
        title = str(fact_pack.get("topic_title", "") or "").strip()
        if primary_pool == "news":
            return f"让读者快速理解 {title or '这件事'} 的关键变化、真正含义和后续观察点。"
        if primary_pool == "github":
            return f"让读者先判断 {title or '这个项目'} 是否适合自己的场景，再理解它的差异化、技术栈、实现链路、部署方式、采用边界和仓库入口。"
        return f"把 {title or '这套方法'} 的问题、机制、实现链路和工程边界讲清楚。"

    @staticmethod
    def _outline_writer_notes(*, primary_pool: str, fact_pack: dict[str, Any]) -> list[str]:
        notes = [
            "不要写成模板化总分总，正文必须顺着当前池子的任务去组织。",
            "如果原文已有清晰结构，优先沿用原结构和实现链路。",
        ]
        if primary_pool == "github":
            notes.extend(
                [
                    "GitHub 文章必须兼顾 推荐价值 和 技术拆解，不能只做仓库简介。",
                    "开头先用一句话定位，再让读者判断使用场景和目标读者，第二个核心小节再回答为什么同类项目里值得优先看它。",
                    "“为什么是它”不能只写优点，还要交代它相对同类方案的代价、边界或前提条件。",
                    "“核心实现拆解”只挑 2 到 4 条最关键链路深拆，每条都要回到代码块、命令块或目录职责。",
                    "“核心实现拆解”里的每条链路都要先给一句技术定位：它属于哪一层、用了什么范式或抽象，例如事件流、状态容器、React/Hook、Web Components、消息适配层或插件式扩展。",
                    "不要只复述函数做了什么；每条实现链路结尾都要补一个技术总结，说明这种写法体现了什么工程思路，以及为什么这样组织。",
                ]
            )
            if fact_pack.get("github_is_collection_repo") and fact_pack.get("github_focus_root"):
                notes.append(
                    f"这是一个案例集合型仓库；“核心实现拆解”和“部署方式与接入建议”必须明确以 `{fact_pack.get('github_focus_root')}` 作为代表性示例，不要在同一篇实现段落里混写多个子项目。"
                )
        elif primary_pool == "news":
            notes.extend(
                [
                    "新闻稿只写有依据的变化、意义和风险外溢，不脑补系统实现。",
                    "不要机械加一个『对产品经理的影响』小节；只有证据明确指向某类角色时，才写对谁有影响。",
                    "如果新闻核心是叙事争议、信任裂痕、平台风险或行业信号，就直接把第三段写成这些真正重要的含义。",
                ]
            )
        else:
            notes.append("深度讲解要把机制和链路写透，不要只堆结论。")
        if fact_pack.get("coverage_checklist"):
            notes.append("覆盖清单里的要点必须在正文中出现，可以用等价中文表达。")
        if primary_pool == "github" and fact_pack.get("required_code_block_count"):
            notes.append(f"正文至少整合 {int(fact_pack.get('required_code_block_count') or 0)} 个代码块或命令块，并解释它们在链路中的作用。")
        if primary_pool == "github" and fact_pack.get("github_repo_url"):
            notes.append("结尾必须附上 GitHub 项目链接，方便读者直接进入仓库。")
        return notes[:12]

    @staticmethod
    def _format_pool_signal_pack(*, primary_pool: str, signal_pack: dict[str, Any]) -> str:
        labels = {
            "news": {
                "event_points": "事件事实",
                "change_points": "关键变化",
                "impact_points": "影响线索",
                "open_questions": "开放问题",
            },
            "github": {
                "scenario_points": "适用场景",
                "differentiation_points": "创新点 / 差异化",
                "recommendation_points": "推荐价值",
                "problem_points": "问题定义",
                "tech_stack_points": "技术栈线索",
                "execution_flow_points": "执行链路",
                "code_points": "代码与命令线索",
                "deployment_points": "部署方式",
                "repository_points": "仓库入口",
                "tradeoff_points": "工程取舍",
            },
            "deep_dive": {
                "problem_definition_points": "问题定义",
                "core_mechanism_points": "核心机制",
                "implementation_chain_points": "实现链路",
                "module_points": "关键模块",
                "limitation_points": "边界与限制",
            },
        }
        label_map = labels.get(primary_pool, labels["deep_dive"])
        blocks: list[str] = []
        for key, title in label_map.items():
            items = [str(item).strip() for item in (signal_pack.get(key) or []) if str(item).strip()]
            if not items:
                continue
            blocks.append(f"{title}:\n" + "\n".join(f"- {item}" for item in items[:6]))
        return "\n\n".join(blocks) if blocks else "- 暂无额外池子线索"

    def _dynamic_pool_rules(
        self,
        *,
        primary_pool: str,
        subtype: str,
        fact_pack: dict[str, Any],
        pool_blueprint: dict[str, Any],
        outline_plan: dict[str, Any],
    ) -> list[str]:
        rules: list[str] = []
        coverage_checklist = [str(item).strip() for item in (fact_pack.get("coverage_checklist") or []) if str(item).strip()]
        if primary_pool == "news":
            rules.extend(
                [
                    "先形成事件判断，再展开变化和影响，不要把正文写成新闻素材转述。",
                    "未知内容必须明确保留为未知，不要为了显得深入去脑补实现链路。",
                    "不要把第三段固定写成『对产品经理的影响』或类似职业化模板；第三段应该由新闻本身决定，可以写行业含义、信任裂痕、平台风险、资本信号或外溢影响。",
                    "只有当证据明确落到某类角色、岗位或人群时，才允许写『对谁有影响』；否则优先写『这件事真正意味着什么』。",
                ]
            )
        elif primary_pool == "github":
            rules.extend(
                [
                    "GitHub 文章必须按 一句话定位 -> 使用场景与目标读者 -> 为什么是它：创新点与同类差异 -> 技术栈分层总览 -> 核心实现拆解 -> 部署方式与接入建议 -> 适用边界与采用建议 -> 总结 -> GitHub 项目链接 的顺序展开。",
                    "第一屏先用一句话说明这个项目本质上是什么，再回答『谁会需要它 / 典型场景是什么』，不要一上来只堆功能。",
                    "第二个核心小节要回答它的创新点、突破点、同类差异和为什么在同类项目里值得优先看。",
                    "如果项目有代码、目录、依赖或工作流线索，必须写进技术栈分层总览或核心实现拆解，而不是只介绍用途。",
                    "核心实现拆解只挑 2 到 4 条最关键链路深拆，每一条都要解释这段代码或命令在整条链路里的作用、依赖和工程取舍。",
                    "核心实现拆解里的每一条链路，都要先概括它属于什么技术范式、抽象层或工程模式，再进入代码细节；不要只做函数说明文。",
                    "如果材料显示某个层使用了 React 组件 / Hook、Web Components、事件驱动、状态机、消息适配层、插件式扩展等范式，要明确点出；如果证据不足，就写成谨慎判断，不要强行断言。",
                    "每条链路在讲完代码职责后，都要补一小段“技术总结”或“工程总结”，解释这种实现反映出的组织方式、复用策略或性能/维护性取舍。",
                    "禁止自己发明伪代码、类结构或所谓“基于某设计模式的推测实现”；只允许解释仓库里真实出现的代码、命令、目录和配置。",
                    "实现细节里的非命令代码块，优先引用带 source_path 的真实仓库文件片段，并在正文里点出文件路径。",
                    "部署方式必须单独成节；如果源材料里有安装、运行、Docker、CLI 或 API key 线索，就要写成可执行的上手路径。",
                    "在总结之前要单独写『适用边界与采用建议』，明确适合谁、部署门槛是什么、哪些团队不该直接照搬。",
                    "结尾必须附上 GitHub 项目链接，并用 Markdown 链接形式给出仓库入口。",
                    "外部联网背景只能服务于使用场景、同类方案对比或差异化判断；如果和当前仓库不直接相关，就宁可不用。",
                ]
            )
            if fact_pack.get("github_is_collection_repo") and fact_pack.get("github_focus_root"):
                rules.extend(
                    [
                        f"当前仓库属于案例集合型项目；正文允许把整个仓库当作技术样本库来介绍，但“核心实现拆解”和“部署方式与接入建议”必须显式说明以下内容以 `{fact_pack.get('github_focus_root')}` 为代表案例展开。",
                        "不要把多个示例项目并列写成 链路一 / 链路二 / 链路三；如果需要提到别的示例，也只能放在对比或补充句里，不能当作同一套实现链路。",
                    ]
                )
            if self._is_technical_walkthrough_subtype(primary_pool=primary_pool, subtype=subtype):
                rules.append("对 GitHub 技术拆解稿，优先解释模块职责、执行链路和工程取舍，而不是功能列表。")
            required_code_blocks = int(fact_pack.get("required_code_block_count", 0) or 0)
            if required_code_blocks >= 2:
                rules.append(f"当前材料里至少有 {required_code_blocks} 个可用代码块或命令块，正文必须实际整合至少 {required_code_blocks} 个。")
            required_source_code_blocks = int(fact_pack.get("required_source_code_block_count", 0) or 0)
            if required_source_code_blocks >= 1:
                rules.append(
                    f"当前材料里至少有 {required_source_code_blocks} 个真实仓库源码片段可用，正文至少要实际整合 {required_source_code_blocks} 个非命令源码块。"
                )
        else:
            rules.extend(
                [
                    "深度讲解稿要顺着问题 -> 机制 -> 实现 -> 边界展开，不要写成热点快评。",
                    "关键模块和代码片段必须回到整体链路里解释其职责和依赖。 ",
                ]
            )
        if coverage_checklist:
            rules.append("覆盖清单中的要点必须全部出现，允许用等价中文表达覆盖英文原始标题。")
        if outline_plan.get("sections"):
            rules.append("正文一级结构优先对齐提纲计划，不要随意改成另一套模板。")
        if pool_blueprint.get("must_cover"):
            rules.append("写作过程中要不断回看蓝图里的 must_cover，缺项时优先补足。")
        return rules

    @staticmethod
    def _build_structure_strategy(
        *,
        primary_pool: str,
        subtype: str,
        section_blueprint: list[dict[str, Any]],
        implementation_steps: list[dict[str, Any]],
        architecture_points: list[dict[str, Any]],
        code_artifacts: list[dict[str, Any]],
        coverage_checklist: list[str],
        article_variant: str = "standard",
    ) -> list[str]:
        has_strong_source_structure = len(section_blueprint) >= 4
        has_dense_implementation = (
            len(implementation_steps) >= 2
            or len(architecture_points) >= 2
            or len(code_artifacts) >= 1
            or len(coverage_checklist) >= 4
        )
        structure_strategy: list[str] = []
        if article_variant == "project_explainer":
            structure_strategy.extend(
                [
                    "优先保留原文的章节顺序和组件层级，不要先套成通用 tutorial 四段骨架。",
                    "原文如果有独立 benchmark、evaluation、comparison、failure 或 tradeoff 段，必须保留成独立 section。",
                    "多个组件或模块段不要合并成一个笼统的“核心机制”，组件名和职责要落到具体名字。",
                ]
            )
        if has_strong_source_structure:
            structure_strategy.append("优先沿用原文章节顺序组织正文，只允许合并相邻小节，不要重排实现链路。")
        else:
            structure_strategy.append("如果原文结构不够完整，再参考当前池子蓝图和提纲自行组织结构。")
        if has_dense_implementation or WritingTemplateService._is_technical_walkthrough_subtype(primary_pool=primary_pool, subtype=subtype):
            structure_strategy.extend(
                [
                    "正文优先使用 ## 和 ### 标题展开技术链路，不要把全文写成多个重复从 1 开始的顶层编号列表。",
                    "凡是原文提到的实现步骤、系统角色、代码片段，都要解释它在整条链路里的作用、依赖关系和工程取舍。",
                ]
            )
        else:
            structure_strategy.append("列表只用于并列信息，不要为了显得工整而把所有段落都改写成清单。")
        return structure_strategy

    @staticmethod
    def _type_rules(type_cfg: dict[str, Any], key: str) -> list[str]:
        return [str(item).strip() for item in (type_cfg.get(key) or []) if str(item).strip()]

    @staticmethod
    def _dynamic_subtype_rules(*, primary_pool: str, subtype: str, fact_pack: dict[str, Any]) -> list[str]:
        rules: list[str] = []
        implementation_steps = [item for item in (fact_pack.get("implementation_steps") or []) if isinstance(item, dict)]
        architecture_points = [item for item in (fact_pack.get("architecture_points") or []) if isinstance(item, dict)]
        code_artifacts = [item for item in (fact_pack.get("code_artifacts") or []) if isinstance(item, dict)]
        numbers = [str(item).strip() for item in (fact_pack.get("numbers") or []) if str(item).strip()]
        related_topics = [item for item in (fact_pack.get("related_topics") or []) if isinstance(item, dict)]

        if WritingTemplateService._is_tutorial_subtype(primary_pool=primary_pool, subtype=subtype):
            if implementation_steps:
                rules.append("把“分步实战”写成真正的操作链路：每一步都说明输入、动作和预期结果。")
            if code_artifacts:
                rules.append("命令块和代码块必须贴着对应步骤出现，不要统一堆到文末。")
            rules.append("如果原文给了多个步骤，优先用小标题组织，而不是只写列表。")
        elif WritingTemplateService._is_technical_walkthrough_subtype(primary_pool=primary_pool, subtype=subtype):
            if architecture_points:
                rules.append("在进入实现细节前，先用一节交代组件角色和分工。")
            if code_artifacts:
                rules.append("代码相关段落必须解释职责、上下游依赖和工程取舍，不要只摘代码。")
            if implementation_steps:
                rules.append("按实现链路顺序展开，每一层都回答“为什么这样设计”。")
        elif WritingTemplateService._is_news_subtype(primary_pool=primary_pool, subtype=subtype):
            if numbers:
                rules.append("优先把数字放在变化、影响和判断里使用，而不是零散摆事实。")
            if related_topics:
                rules.append("背景材料只用于支撑判断，不能在文末堆成信息串或阅读列表。")
                rules.append("引用相关新闻时，用自己的话概括它传递的信号，不要把新闻标题原样写进正文。")
            rules.append("每个小节都要形成判断句，避免把新闻素材逐条转述。")
        else:
            if architecture_points:
                rules.append("如果产品涉及模块或链路，至少用一段讲清内部机制。")
            if code_artifacts:
                rules.append("如果产品原文出现代码或命令，要解释这说明了什么能力边界。")
            rules.append("对比同类方案时，优先写差异化机制、采用门槛和适用对象。")
        return rules or ["围绕当前类型最重要的判断维度展开，不要回退成通用型模板文章。"]

    @staticmethod
    def _build_key_points(
        topic: dict[str, Any],
        related_topics: list[dict[str, Any]],
        primary_source: dict[str, Any],
        related_sources: list[dict[str, Any]],
    ) -> list[str]:
        points: list[str] = []
        title = str(topic.get("title", "") or "").strip()
        summary = str(topic.get("summary", "") or "").strip()
        if title:
            points.append(f"主题本身：{title}")
        if summary:
            points.append(f"主题摘要：{summary}")
        if topic.get("rerank_reason"):
            points.append(f"入选原因：{topic.get('rerank_reason')}")
        if topic.get("final_score") is not None:
            points.append(f"综合评分：{topic.get('final_score')}")
        for paragraph in (primary_source.get("paragraphs") or [])[:3]:
            text = str(paragraph or "").strip()
            if text:
                points.append(f"正文线索：{text}")
        for item in related_topics[:2]:
            if item.get("summary"):
                points.append(f"相关线索：{item['summary']}")
        for item in related_sources[:1]:
            text = str(item.get("content_text", "") or "").strip()
            if text:
                points.append(f"相关正文：{text[:220]}")
        return points[:6]

    @staticmethod
    def _build_related_context_signals(related_topics: list[dict[str, Any]], related_sources: list[dict[str, Any]]) -> list[str]:
        signals: list[str] = []
        for item in related_topics[:3]:
            summary = str(item.get("summary", "") or "").strip()
            source = str(item.get("source", "") or "").strip()
            if summary:
                prefix = f"来自{source}的相关动态显示：" if source else "相关动态显示："
                signals.append(f"{prefix}{summary}")
        for item in related_sources[:2]:
            text = str(item.get("content_text", "") or "").strip()
            source = str(item.get("source", "") or "").strip()
            if text:
                prefix = f"另一条来自{source}的报道提到：" if source else "另一条相关报道提到："
                signals.append(f"{prefix}{text[:180]}")
        output: list[str] = []
        seen: set[str] = set()
        for signal in signals:
            cleaned = str(signal or "").strip()
            if not cleaned:
                continue
            key = re.sub(r"\s+", "", cleaned.lower())
            if key in seen:
                continue
            seen.add(key)
            output.append(cleaned)
            if len(output) >= 6:
                break
        return output

    @classmethod
    def _build_section_blueprint(cls, source_structure: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for section in (source_structure.get("sections") or [])[:8]:
            source_heading = str(section.get("heading", "") or "").strip()
            if not source_heading:
                continue
            output.append(
                {
                    "heading": cls._localize_display_heading(source_heading),
                    "source_heading": source_heading,
                    "summary": str(section.get("summary", "") or ""),
                }
            )
        return output

    @classmethod
    def _build_implementation_steps(cls, source_structure: dict[str, Any]) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for section in (source_structure.get("sections") or [])[:8]:
            heading = str(section.get("heading", "") or "").strip()
            if not heading:
                continue
            if not re.search(
                r"(step|步骤|阶段|流程|workflow|pipeline|graph|mcp|rag|agent|ttl|renewal|lifecycle)",
                heading,
                flags=re.IGNORECASE,
            ):
                continue
            paragraphs = [str(item).strip() for item in (section.get("paragraphs") or []) if str(item).strip()]
            steps.append(
                {
                    "title": cls._localize_display_heading(heading),
                    "source_title": heading,
                    "summary": str(section.get("summary", "") or ""),
                    "details": paragraphs[:3],
                }
            )
        return steps[:6]

    @classmethod
    def _build_architecture_points(cls, source_structure: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for section in (source_structure.get("sections") or [])[:8]:
            heading = str(section.get("heading", "") or "").strip()
            summary = str(section.get("summary", "") or "").strip()
            haystack = f"{heading} {summary}"
            if not heading or not summary:
                continue
            if not re.search(
                r"(architecture|模块|组件|架构|agent|mcp|rag|graph|workflow|pipeline|session|编排)",
                haystack,
                flags=re.IGNORECASE,
            ):
                continue
            output.append({"component": heading, "responsibility": summary})
        for item in output:
            item["source_component"] = item["component"]
            item["component"] = cls._localize_display_heading(str(item.get("component", "") or ""))
        return output[:6]

    @classmethod
    def _build_code_artifacts(cls, source_structure: dict[str, Any]) -> list[dict[str, Any]]:
        sections = list(source_structure.get("sections") or [])
        code_blocks = list(source_structure.get("code_blocks") or [])
        output: list[dict[str, Any]] = []
        for idx, code in enumerate(code_blocks[:6]):
            section_title = ""
            for section in sections:
                if idx in (section.get("code_refs") or []):
                    section_title = str(section.get("heading", "") or "")
                    break
            excerpt = str(code.get("code_excerpt", "") or "").strip()
            if not excerpt:
                continue
            source_path = str(code.get("source_path", "") or "").strip()
            output.append(
                {
                    "section": cls._localize_display_heading(section_title),
                    "source_section": section_title,
                    "language": str(code.get("language", "") or ""),
                    "summary": excerpt.splitlines()[0][:160],
                    "code_text": str(code.get("code_text", "") or excerpt),
                    "kind": str(code.get("kind", "code") or "code"),
                    "line_count": int(code.get("line_count", 0) or 0),
                    "origin": str(code.get("origin", "article_code") or "article_code"),
                    "source_path": source_path,
                    "preserve_verbatim": True,
                }
            )
        return output

    @classmethod
    def _build_coverage_checklist(cls, source_structure: dict[str, Any]) -> list[dict[str, str]]:
        section_summaries = {
            str(section.get("heading", "") or "").strip(): str(section.get("summary", "") or "").strip()
            for section in (source_structure.get("sections") or [])[:12]
            if str(section.get("heading", "") or "").strip()
        }
        output: list[dict[str, str]] = []
        for item in (source_structure.get("coverage_checklist") or [])[:12]:
            source = str(item or "").strip()
            if not source:
                continue
            output.append(
                {
                    "source": source,
                    "display": cls._localize_display_heading(source),
                    "summary": section_summaries.get(source, ""),
                }
            )
        return output

    @classmethod
    def _build_github_coverage_targets(
        cls,
        *,
        archetype: str,
        deployment_need: str,
        section_blueprint: list[dict[str, Any]],
        implementation_steps: list[dict[str, Any]],
        architecture_points: list[dict[str, Any]],
        github_source_code_blocks: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        if archetype == "collection_repo":
            headings = [
                "项目定位与核心价值",
                "内容地图与分类视角",
                "为什么值得关注",
                "代表案例与实现观察",
                "如何使用这个仓库",
                "GitHub 项目链接",
            ]
        elif archetype == "tooling_repo":
            headings = [
                "项目定位与核心问题",
                "为什么值得关注",
                "整体架构与技术栈",
                "关键模块与执行链路",
                "部署方式与接入建议",
                "适用边界与采用建议",
                "GitHub 项目链接",
            ]
        else:
            headings = [
                "项目定位与核心问题",
                "为什么值得关注",
                "整体架构与技术栈",
                "关键模块与执行链路",
                "工程取舍与技术总结",
                "部署方式与接入建议",
                "适用边界与采用建议",
                "GitHub 项目链接",
            ]
        if deployment_need != "required":
            headings = [item for item in headings if item != "部署方式与接入建议"]

        source_map: dict[str, str] = {}
        if architecture_points:
            source_map["整体架构与技术栈"] = str(architecture_points[0].get("source_component") or architecture_points[0].get("component") or "").strip()
        if implementation_steps:
            source_map["关键模块与执行链路"] = str(implementation_steps[0].get("source_title") or implementation_steps[0].get("title") or "").strip()
        if github_source_code_blocks:
            source_map["工程取舍与技术总结"] = str(github_source_code_blocks[0].get("source_path") or "").strip()
            source_map["代表案例与实现观察"] = str(github_source_code_blocks[0].get("source_path") or "").strip()
        if section_blueprint:
            source_map["项目定位与核心问题"] = str(section_blueprint[0].get("source_heading") or section_blueprint[0].get("heading") or "").strip()
            source_map["项目定位与核心价值"] = str(section_blueprint[0].get("source_heading") or section_blueprint[0].get("heading") or "").strip()

        output: list[dict[str, str]] = []
        for heading in headings:
            output.append(
                {
                    "source": source_map.get(heading) or heading,
                    "display": heading,
                    "summary": "",
                }
            )
        return output

    @classmethod
    def _localize_display_heading(cls, heading: str) -> str:
        raw = str(heading or "").strip()
        if not raw:
            return raw
        working = raw
        for source, target in cls._DISPLAY_HEADING_REPLACEMENTS:
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])", flags=re.IGNORECASE)
            working = pattern.sub(target, working)
        localized = LocalizationService.localize_heading_text(working)
        result = localized or working
        result = re.sub(r"^(?:the|a|an)\s+", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s*:\s*", "：", result)
        result = re.sub(r"\(([^)]+)\)", r"（\1）", result)
        result = re.sub(r"\s+（", "（", result)
        result = re.sub(r"\s{2,}", " ", result)
        return result.strip(" -:")

    @staticmethod
    def _extract_numbers(text: str) -> list[str]:
        values = re.findall(r"\d+(?:\.\d+)?(?:%|倍|x|X|万|亿|k|K|m|M|分钟|小时|天|年|美元|元)?", text or "")
        output: list[str] = []
        for value in values:
            if value not in output:
                output.append(value)
            if len(output) >= 8:
                break
        return output

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        candidates = re.findall(r"[A-Za-z][A-Za-z0-9._/-]{2,}|[\u4e00-\u9fff]{2,8}", text or "")
        blacklist = {
            "这是",
            "这个",
            "可以",
            "一个",
            "我们",
            "他们",
            "因为",
            "所以",
            "如果",
            "但是",
            "进行",
            "以及",
            "相关",
            "功能",
            "能力",
            "产品",
            "工具",
            "文章",
            "工作流",
        }
        output: list[str] = []
        for item in candidates:
            if item in blacklist:
                continue
            if item not in output:
                output.append(item)
            if len(output) >= 12:
                break
        return output

    @staticmethod
    def _normalize_images(items: list[Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            output.append(
                {
                    "url": url,
                    "alt": str(item.get("alt", "") or "").strip(),
                    "caption": str(item.get("caption", "") or "").strip(),
                    "context": str(item.get("context", "") or "").strip(),
                    "source": str(item.get("source", "") or "").strip(),
                    "origin": str(item.get("origin", "") or "").strip() or "primary",
                    "score": int(item.get("score", 0) or 0),
                    "relevance_hits": int(item.get("relevance_hits", 0) or 0),
                    "host": str(item.get("host", "") or "").strip(),
                }
            )
        return output

    @classmethod
    def _normalize_related_images(cls, related_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for source in related_sources[:3]:
            title = str(source.get("title", "") or "").strip()
            for image in cls._normalize_images(source.get("images") or []):
                item = dict(image)
                item["source_article"] = title
                item["origin"] = "related"
                output.append(item)
        return output

    @classmethod
    def _normalize_web_enrich_images(cls, *, web_enrich: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for source_name, sources in (
            ("web_search_official", web_enrich.get("official_sources") or []),
            ("web_search_context", web_enrich.get("context_sources") or []),
        ):
            for source in sources[:4]:
                if not isinstance(source, dict):
                    continue
                source_title = str(source.get("title", "") or "").strip()
                source_domain = str(source.get("domain", "") or "").strip()
                for image in cls._normalize_images(source.get("images") or []):
                    item = dict(image)
                    item["source_article"] = source_title or source_domain
                    item["source"] = source_domain or str(source.get("url", "") or "").strip()
                    item["origin"] = source_name
                    item["score"] = max(int(item.get("score", 0) or 0), 78 if source_name == "web_search_official" else 64)
                    output.append(item)
        return output

    @staticmethod
    def _merge_news_image_candidates(
        *,
        primary_images: list[dict[str, Any]],
        related_images: list[dict[str, Any]],
        searched_images: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = []
        seen: set[str] = set()
        for image in [*primary_images, *related_images, *searched_images]:
            url = str(image.get("url", "") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(image)
        origin_rank = {
            "primary": 0,
            "related": 1,
            "web_search_official": 2,
            "web_search_context": 3,
        }
        merged.sort(
            key=lambda item: (
                int(origin_rank.get(str(item.get("origin", "") or "").strip(), 9)),
                -int(item.get("relevance_hits", 0) or 0),
                -int(item.get("score", 0) or 0),
                str(item.get("url", "") or ""),
            )
        )
        return merged

    @staticmethod
    def _bullet_block(items: list[Any]) -> str:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if not cleaned:
            return "- 暂无"
        return "\n".join(f"- {item}" for item in cleaned)

    @staticmethod
    def preview_fact_pack(fact_pack: dict[str, Any], limit: int = 4000) -> str:
        text = json.dumps(fact_pack, ensure_ascii=False, indent=2)
        return text if len(text) <= limit else text[:limit] + f"\n... [truncated, total {len(text)} chars]"
