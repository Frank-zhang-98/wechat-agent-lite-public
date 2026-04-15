from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.llm_gateway import LLMGateway


@dataclass
class TitlePlan:
    article_title: str
    wechat_title: str
    source: str = "heuristic"
    debug: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "article_title": self.article_title,
            "wechat_title": self.wechat_title,
            "source": self.source,
            "debug": self.debug,
        }


class TitleSurfaceAndHeadlineValidator:
    BROKEN_SURFACE_PATTERNS = (
        (r"\bOpen AI\b", "split_openai"),
        (r"\bChat GPT\b", "split_chatgpt"),
        (r"\bA PI\b", "split_api"),
        (r"\bS OTA\b", "split_sota"),
        (r"\bL LM\b", "split_llm"),
        (r"\bM CP\b", "split_mcp"),
        (r"\bR AG\b", "split_rag"),
        (r"\bG PU\b", "split_gpu"),
        (r"\bS DK\b", "split_sdk"),
        (r"\b[A-Z]\s+[A-Z]{2,}\b", "split_acronym"),
        (r"\b[A-Z]{2,}\s+[A-Z]\b", "split_acronym"),
    )
    NEWS_WEAK_HEADLINE_PHRASES = (
        "核心能力分析",
        "产品分析",
        "能力解析",
        "产品定位与使用场景",
        "变化分析",
        "事件分析",
    )

    def __init__(self, service: "TitleGenerationService") -> None:
        self.service = service

    def validate_plan(
        self,
        *,
        article_title: str,
        wechat_title: str,
        topic: dict[str, Any],
        pool: str,
        subtype: str,
    ) -> dict[str, Any]:
        resolved_pool, resolved_subtype, semantic_mode = self.service._resolve_content_semantics(
            pool=pool,
            subtype=subtype,
            fact_pack={"primary_pool": pool, "subtype": subtype},
        )
        article = self._validate_title(
            title=article_title,
            topic=topic,
            pool=resolved_pool,
            subtype=resolved_subtype,
            semantic_mode=semantic_mode,
        )
        wechat = self._validate_title(
            title=wechat_title,
            topic=topic,
            pool=resolved_pool,
            subtype=resolved_subtype,
            semantic_mode=semantic_mode,
        )
        return {
            "valid": bool(article["valid"] and wechat["valid"]),
            "article": article,
            "wechat": wechat,
            "surface_reject_reason": str(article["surface_reject_reason"] or wechat["surface_reject_reason"] or ""),
            "headline_reject_reason": str(article["headline_reject_reason"] or wechat["headline_reject_reason"] or ""),
            "semantic_mode": semantic_mode,
        }

    def _validate_title(
        self,
        *,
        title: str,
        topic: dict[str, Any],
        pool: str,
        subtype: str,
        semantic_mode: str,
    ) -> dict[str, Any]:
        normalized = self.service._normalize_spaces(title)
        if not normalized:
            return {
                "valid": False,
                "surface_reject_reason": "",
                "headline_reject_reason": "empty_title",
            }
        surface_reject_reason = self.broken_surface_reason(normalized)
        if surface_reject_reason:
            return {
                "valid": False,
                "surface_reject_reason": surface_reject_reason,
                "headline_reject_reason": "",
            }
        if not self.service._is_natural_title(normalized):
            return {
                "valid": False,
                "surface_reject_reason": "",
                "headline_reject_reason": "awkward_title",
            }
        if self.service._is_news_semantics(pool=pool, subtype=subtype):
            headline_reject_reason = self.headline_reject_reason(title=normalized)
            if headline_reject_reason:
                return {
                    "valid": False,
                    "surface_reject_reason": "",
                    "headline_reject_reason": headline_reject_reason,
                }
            if not self.service._is_valid_news_title(normalized, topic=topic):
                return {
                    "valid": False,
                    "surface_reject_reason": "",
                    "headline_reject_reason": "invalid_news_title",
                }
        return {
            "valid": True,
            "surface_reject_reason": "",
            "headline_reject_reason": "",
            "semantic_mode": semantic_mode,
        }

    def broken_surface_reason(self, title: str) -> str:
        value = self.service._normalize_spaces(title)
        if not value:
            return ""
        for pattern, reason in self.BROKEN_SURFACE_PATTERNS:
            if re.search(pattern, value):
                return reason
        return ""

    def headline_reject_reason(self, *, title: str) -> str:
        value = self.service._normalize_spaces(title)
        if not value:
            return ""
        for phrase in self.NEWS_WEAK_HEADLINE_PHRASES:
            if phrase in value:
                return "analysis_style_headline"
        return ""


class TitleGenerationService:
    ARTICLE_TITLE_MAX_CHARS = 80
    WECHAT_TITLE_MAX_CHARS = 64
    WECHAT_TITLE_MAX_BYTES = 192
    SUBJECTIVE_TITLE_PHRASES = ("心头好", "值不值得用", "神器", "封神", "绝了", "宝藏", "闭眼入")
    NEWS_EVENT_KEYWORDS = (
        "融资",
        "收费",
        "计费",
        "发布",
        "开放",
        "推出",
        "上线",
        "更新",
        "调整",
        "开源",
        "合作",
        "收购",
        "回应",
        "发布会",
        "入局",
        "登顶",
        "夺冠",
        "刷榜",
        "爆火",
        "停运",
        "增长",
        "押注",
        "IPO",
        "上市",
        "贷款",
        "估值",
    )
    AWKWARD_TITLE_PATTERNS = (
        r"[，,]\s*它是如何(?:构建|实现|设计|搭建)的[？?]?$",
        r"[，,]\s*它是怎么(?:构建|实现|设计|搭建)的[？?]?$",
        r"[：:]\s*一个为[^，,。！？?]{2,40}设计的[^，,。！？?]{2,60}[，,]\s*它是如何(?:构建|实现|设计|搭建)的[？?]?$",
    )

    CLICKBAIT_WORDS = ("震惊", "必看", "惊呆", "不看后悔", "全网最全", "保姆级")
    GENERIC_TITLE_PHRASES = ("个重点看懂", "为什么值得关注", "实战解读", "变化解读", "事件解读")
    GENERIC_NEWS_TITLE_PHRASES = ("变化分析", "事件分析", "最新变化解读", "关键更新解读", "变化观察")
    COLLOQUIAL_TITLE_PHRASES = (
        "值不值得用",
        "它能解决什么问题",
        "个重点看懂",
        "上手",
        "为什么值得关注",
        "这次变化意味着什么",
    )
    PROFESSIONAL_TITLE_KEYWORDS = (
        "分析",
        "拆解",
        "实践",
        "指南",
        "设计",
        "实现",
        "机制",
        "边界",
        "定位",
        "观察",
        "影响",
    )
    NEWS_IMPACT_KEYWORDS = (
        "影响",
        "成本",
        "开发者",
        "订阅",
        "调用",
        "付费",
        "收费",
        "计费",
        "免费",
        "融资",
        "企业",
        "端侧",
        "大模型",
        "生态",
        "上线",
        "开源",
        "价格",
        "资本",
        "融资",
        "IPO",
        "上市",
        "贷款",
        "估值",
        "投融资",
    )
    NEWS_HOOK_KEYWORDS = (
        "首个",
        "首次",
        "又一",
        "爆火",
        "刷屏",
        "登顶",
        "夺冠",
        "入局",
        "押注",
        "杀入",
        "开打",
        "IPO",
        "上市",
        "数十亿",
        "百亿",
    )
    NEWS_REFERENCE_PATTERNS = (
        "文件泄露指向新系统：公司正在用AI重构某个后台流程",
        "模型或产品发布：关键指标、核心能力、支持范围一并写清",
        "团队开源框架或模型：训练规模、基准结果、超过谁直接点明",
    )

    PRODUCT_HINTS = (
        "Claude Code",
        "Claude",
        "OpenAI",
        "GPT",
        "ChatGPT",
        "Gemini",
        "Anthropic",
        "Cursor",
        "Copilot",
        "LangChain",
        "Perplexity",
        "DeepSeek",
        "Qwen",
        "Midjourney",
        "Sora",
        "SoftBank",
    )

    ENGLISH_STOPWORDS = {
        "how",
        "what",
        "why",
        "when",
        "where",
        "who",
        "i",
        "my",
        "your",
        "our",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "and",
        "or",
        "to",
        "of",
        "for",
        "with",
        "from",
        "in",
        "on",
    }

    ENGLISH_PHRASE_MAP = {
        "multi-agent systems": "多代理系统",
        "software development": "软件开发",
        "claude code session": "Claude Code 会话",
        "claude code": "Claude Code",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "reshaping": "重塑",
        "analyzed": "复盘",
        "analyze": "拆解",
        "session": "会话",
        "workflow": "工作流",
        "developer": "开发者",
        "coding": "编程",
        "tool": "工具",
        "tools": "工具",
        "agent": "Agent",
        "agents": "Agents",
        "subscribers": "订阅用户",
        "third-party": "第三方",
        "billing": "计费",
        "support": "支持",
        "pay extra": "额外付费",
        "ipo": "IPO",
        "loan": "贷款",
        "valuation": "估值",
        "betting": "押注",
    }

    def _title_validator(self) -> TitleSurfaceAndHeadlineValidator:
        return TitleSurfaceAndHeadlineValidator(self)

    def generate(
        self,
        *,
        run_id: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        pool: str = "",
        subtype: str = "",
        llm: LLMGateway,
    ) -> TitlePlan:
        resolved_pool, resolved_subtype, semantic_mode = self._resolve_content_semantics(
            pool=pool,
            subtype=subtype,
            fact_pack=fact_pack,
        )
        fallback = self._generate_fallback(
            topic=topic,
            fact_pack=fact_pack,
            fact_compress=fact_compress,
            pool=resolved_pool,
            subtype=resolved_subtype,
            semantic_mode=semantic_mode,
        )
        llm_plan = self._generate_with_llm(
            run_id=run_id,
            topic=topic,
            fact_pack=fact_pack,
            fact_compress=fact_compress,
            pool=resolved_pool,
            subtype=resolved_subtype,
            semantic_mode=semantic_mode,
            llm=llm,
            fallback=fallback,
        )
        plan = llm_plan or fallback
        article_title = self._clean_article_title(plan.article_title or fallback.article_title)
        wechat_title = self._clean_wechat_title(plan.wechat_title or article_title or fallback.wechat_title)
        if not article_title:
            article_title = fallback.article_title
        if not wechat_title:
            wechat_title = self._clean_wechat_title(article_title)
        return TitlePlan(
            article_title=article_title,
            wechat_title=wechat_title,
            source=plan.source,
            debug=plan.debug,
        )

    def _generate_with_llm(
        self,
        *,
        run_id: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        pool: str = "",
        subtype: str = "",
        semantic_mode: str,
        llm: LLMGateway,
        fallback: TitlePlan,
    ) -> TitlePlan | None:
        prompt = self._build_prompt(
            topic=topic,
            fact_pack=fact_pack,
            fact_compress=fact_compress,
            semantic_mode=semantic_mode,
            fallback=fallback,
        )
        result = llm.call(run_id, "WRITE", "writer", prompt, temperature=0.35)
        parsed = self._parse_llm_result(result.text)
        if not parsed:
            return None
        article_title = self._clean_article_title(parsed.get("article_title", ""))
        wechat_title = self._clean_wechat_title(parsed.get("wechat_title", ""))
        if not article_title or not wechat_title:
            return None
        validation = self.validate_title_plan(
            article_title=article_title,
            wechat_title=wechat_title,
            topic=topic,
            pool=pool,
            subtype=subtype,
        )
        if not bool(validation.get("valid", False)):
            return None
        return TitlePlan(
            article_title=article_title,
            wechat_title=wechat_title,
            source="llm",
            debug={
                "prompt": prompt[:4000],
                "response": result.text[:2000],
                "fallback_article_title": fallback.article_title,
                "fallback_wechat_title": fallback.wechat_title,
                "surface_reject_reason": str(validation.get("surface_reject_reason", "") or ""),
                "headline_reject_reason": str(validation.get("headline_reject_reason", "") or ""),
            },
        )

    def _build_prompt(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        semantic_mode: str,
        fallback: TitlePlan,
    ) -> str:
        return (
            "你是一名微信公众号标题编辑，请为同一篇 AI 技术解读文章生成两层标题，并只返回 JSON。\n\n"
            "返回格式：\n"
            "{\n"
            '  "article_title": "...",\n'
            '  "wechat_title": "...",\n'
            '  "reason": "一句话说明为什么这么写"\n'
            "}\n\n"
            "要求：\n"
            "- 输出简体中文标题，可保留关键英文产品名，如 Claude Code、OpenAI，可保留关键英文术语，如token、agent等。\n"
            "- article_title 用于站内/邮件，信息要完整，建议 18-34 个字，不能空泛，不要标题党。\n"
            "- wechat_title 专门用于公众号草稿，建议控制在 12-40 个字内；只要不超过微信标题上限 64 字，就优先保证完整表达，不要为了变短牺牲可读性。\n"
            "- 如果原始标题是英文，请翻成自然中文，保留关键专有名词。\n"
            "- 不要编造数字；只有事实包里明确有数字时才能写数字。\n"
            "- 优先突出：它是什么、为什么值得关注、对谁有价值。\n"
            "- 标题整体保持书面、专业、克制，不要为了传播感写成口语问句、公众号套路句或“看懂/值不值得用/它能解决什么问题”这类表达。\n"
            "- 不要写成口语提问式病句标题，例如“一个……它是如何构建的”；优先使用书面表达，如“架构与实现拆解”“设计与实现”。\n"
            f"- 参考这类新闻标题结构，而不是照抄：{json.dumps(list(self.NEWS_REFERENCE_PATTERNS), ensure_ascii=False)}\n"
            f"- 如果你拿不准，请参考这个兜底方向：article_title={fallback.article_title} | wechat_title={fallback.wechat_title}\n\n"
            f"标题语义：{semantic_mode}\n"
            f"原始标题：{topic.get('title', '')}\n"
            f"原始摘要：{topic.get('summary', '')}\n"
            f"一句话总结：{fact_compress.get('one_sentence_summary', '')}\n"
            f"关键机制：{json.dumps(fact_compress.get('key_mechanisms', []), ensure_ascii=False)}\n"
            f"典型场景：{json.dumps(fact_compress.get('concrete_scenarios', []), ensure_ascii=False)}\n"
            f"数字信息：{json.dumps(fact_compress.get('numbers', []), ensure_ascii=False)}\n"
            f"关键点：{json.dumps(fact_pack.get('key_points', []), ensure_ascii=False)}\n"
        )

    def _generate_fallback(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        pool: str = "",
        subtype: str = "",
        semantic_mode: str,
    ) -> TitlePlan:
        core_title = self._extract_core_title(topic)
        tool_name = self._extract_tool_name(topic)
        benefit = self._extract_benefit(topic, fact_pack, fact_compress)
        number = self._extract_number(topic, fact_pack, fact_compress)
        localized_title = (
            core_title
            if self._is_news_semantics(pool=pool, subtype=subtype) and re.search(r"[\u4e00-\u9fff]", core_title)
            else self._localize_title(core_title)
        )
        localized_title = self._polish_title_surface(localized_title)
        if self._is_news_semantics(pool=pool, subtype=subtype):
            news_fallback = self._build_news_fallback_title(
                topic=topic,
                fact_pack=fact_pack,
                fact_compress=fact_compress,
                tool_name=tool_name,
                localized_title=localized_title,
            )
            if news_fallback:
                return news_fallback
            fact_titles = [
                self._normalize_spaces(str(item or ""))
                for item in fact_pack.get("key_points", [])[:2]
                if self._normalize_spaces(str(item or ""))
            ]
            if (
                fact_titles
                and any(re.search(r"[\u4e00-\u9fff]", item) for item in fact_titles)
                and any(any(keyword in item for keyword in self.NEWS_EVENT_KEYWORDS) for item in fact_titles)
            ):
                article_candidates = self._unique_titles(
                    [
                        f"{fact_titles[0]}：{fact_titles[1]}" if len(fact_titles) > 1 else fact_titles[0],
                        fact_titles[0],
                    ]
                )
                wechat_candidates = self._unique_titles(
                    [
                        f"{fact_titles[0]}：{fact_titles[1]}" if len(fact_titles) > 1 else fact_titles[0],
                        f"{fact_titles[0]}，{fact_titles[1]}" if len(fact_titles) > 1 else "",
                        fact_titles[0],
                    ]
                )
                article_title = self._pick_best_title(article_candidates, prefer_short=False, semantic_mode="news_analysis")
                wechat_title = self._pick_best_title(wechat_candidates, prefer_short=True, semantic_mode="news_analysis")
                if article_title and wechat_title:
                    return TitlePlan(
                        article_title=self._clean_article_title(article_title),
                        wechat_title=self._clean_wechat_title(wechat_title),
                        source="heuristic",
                        debug={"news_mode": "fact_key_points", "fact_titles": fact_titles},
                    )
        if (
            self._is_news_semantics(pool=pool, subtype=subtype)
            and localized_title
            and not self._mostly_ascii(localized_title)
            and len(localized_title) <= self.WECHAT_TITLE_MAX_CHARS
            and any(keyword in localized_title for keyword in self.NEWS_EVENT_KEYWORDS)
            and any(keyword in localized_title for keyword in self.NEWS_IMPACT_KEYWORDS)
        ):
            preferred_title = self._clean_wechat_title(localized_title)
            if preferred_title:
                return TitlePlan(
                    article_title=self._clean_article_title(localized_title),
                    wechat_title=preferred_title,
                    source="heuristic",
                    debug={
                        "tool_name": tool_name,
                        "benefit": benefit,
                        "number": number,
                        "localized_title": localized_title,
                        "preferred_news_title": preferred_title,
                    },
                )
        templates_article = self._article_templates(
            pool=pool,
            subtype=subtype,
            semantic_mode=semantic_mode,
            tool_name=tool_name,
            benefit=benefit,
            number=number,
            core_title=localized_title,
        )
        templates_wechat = self._wechat_templates(
            pool=pool,
            subtype=subtype,
            semantic_mode=semantic_mode,
            tool_name=tool_name,
            benefit=benefit,
            number=number,
            core_title=localized_title,
        )
        article_title = self._pick_best_title(templates_article, prefer_short=False, semantic_mode=semantic_mode) or self._default_article_title(
            localized_title,
            tool_name,
            benefit,
            semantic_mode=semantic_mode,
        )
        wechat_title = self._pick_best_title(templates_wechat, prefer_short=True, semantic_mode=semantic_mode) or self._default_wechat_title(
            article_title,
            tool_name,
            semantic_mode=semantic_mode,
        )
        return TitlePlan(
            article_title=self._clean_article_title(article_title),
            wechat_title=self._clean_wechat_title(wechat_title),
            source="heuristic",
            debug={
                "tool_name": tool_name,
                "benefit": benefit,
                "number": number,
                "localized_title": localized_title,
            },
        )

    def _build_news_fallback_title(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        tool_name: str,
        localized_title: str,
    ) -> TitlePlan | None:
        source_summary = " ".join(
            [
                str(topic.get("summary", "") or ""),
                str(fact_compress.get("one_sentence_summary", "") or ""),
                " ".join(str(item).strip() for item in fact_pack.get("key_points", [])[:3] if str(item).strip()),
            ]
        )
        raw_title = str(topic.get("title", "") or "")
        raw_haystack = f"{raw_title} {source_summary}".lower()
        subject = self._extract_news_subject(raw_title) or self._extract_news_subject(localized_title or self._extract_core_title(topic))
        if self._mostly_ascii(subject) and re.search(
            r"\b(responds|says|announces|launch(?:es|ed)?|introduc(?:e|es|ing)|update|updated|shut(?:s|ting)?\s+down|kills?)\b",
            str(subject or "").lower(),
        ):
            person_subject = self._extract_english_news_subject(raw_title)
            if person_subject:
                subject = person_subject
        if not subject or subject.endswith("相关变化"):
            subject = tool_name or subject
        keypoint_subject = self._extract_news_subject_from_key_points(fact_pack)
        if keypoint_subject and (not subject or subject == tool_name or len(keypoint_subject) > len(subject)):
            subject = keypoint_subject
        if str(subject).strip().lower() == "sam altman":
            subject = "\u963f\u5c14\u7279\u66fc"
        organization = self._extract_news_organization(source_summary)
        if (
            any(token in raw_haystack for token in ("leaked", "leak", "files", "文件", "代码"))
            and any(token in raw_haystack for token in ("review", "moderat", "security", "account", "incident", "审核", "风控", "账户", "违规", "安全"))
        ):
            actor = organization or "相关团队"
            article_title = f"{subject}文件泄露：{actor}用AI改造审核与风控后台"
            wechat_title = f"{subject}文件泄露：{actor}正把AI接入审核后台"
            return TitlePlan(
                article_title=self._clean_article_title(article_title),
                wechat_title=self._clean_wechat_title(wechat_title),
                source="heuristic",
                debug={"news_mode": "leak_workflow", "subject": subject, "organization": actor},
            )
        if re.search(r"(发布|推出|上线)", source_summary) and (fact_compress.get("numbers") or fact_pack.get("numbers")):
            metric = self._extract_primary_metric(fact_compress=fact_compress, fact_pack=fact_pack)
            if metric and self._is_safe_launch_metric(
                metric=metric,
                subject=subject,
                raw_title=raw_title,
                localized_title=localized_title,
            ):
                article_title = f"{subject}发布：{metric}"
                return TitlePlan(
                    article_title=self._clean_article_title(article_title),
                    wechat_title=self._clean_wechat_title(article_title),
                    source="heuristic",
                    debug={"news_mode": "launch_metric", "subject": subject, "metric": metric},
                )
        event = self._extract_news_event_phrase(raw_title=raw_title, localized_title=localized_title, text=source_summary)
        if not event:
            for key_point in fact_pack.get("key_points") or []:
                candidate = self._extract_news_event_phrase(
                    raw_title=str(key_point or ""),
                    localized_title=str(key_point or ""),
                    text=str(key_point or ""),
                )
                if candidate:
                    event = candidate
                    break
        impact = self._extract_news_impact_phrase(text=source_summary, localized_title=localized_title, fact_pack=fact_pack)
        target = self._extract_news_target_audience(text=source_summary, subject=subject)
        hook = self._extract_news_hook_phrase(raw_title=raw_title, localized_title=localized_title, text=source_summary)
        source_title_candidates = self._extract_news_source_title_candidates(raw_title=raw_title, localized_title=localized_title)
        if source_title_candidates:
            preferred_source_title = self._pick_best_title(
                source_title_candidates,
                prefer_short=True,
                semantic_mode="news_analysis",
            )
            if preferred_source_title:
                return TitlePlan(
                    article_title=self._clean_article_title(preferred_source_title),
                    wechat_title=self._clean_wechat_title(preferred_source_title),
                    source="heuristic",
                    debug={
                        "news_mode": "strong_source_title",
                        "subject": subject,
                        "event": event,
                        "impact": impact,
                        "target": target,
                        "hook": hook,
                        "source_title_candidates": source_title_candidates,
                    },
                )
        if subject and event:
            article_candidates = self._unique_titles(
                source_title_candidates
                + self._build_news_template_candidates(
                    subject=subject,
                    event=event,
                    impact=impact,
                    target=target,
                    hook=hook,
                    prefer_short=False,
                )
            )
            wechat_candidates = self._unique_titles(
                source_title_candidates
                + self._build_news_template_candidates(
                    subject=subject,
                    event=event,
                    impact=impact,
                    target=target,
                    hook=hook,
                    prefer_short=True,
                )
            )
            article_title = self._pick_best_title(article_candidates, prefer_short=False, semantic_mode="news_analysis")
            wechat_title = self._pick_best_title(wechat_candidates, prefer_short=True, semantic_mode="news_analysis")
            if article_title and wechat_title:
                return TitlePlan(
                    article_title=self._clean_article_title(article_title),
                    wechat_title=self._clean_wechat_title(wechat_title),
                    source="heuristic",
                    debug={
                        "news_mode": "event_impact",
                        "subject": subject,
                        "event": event,
                        "impact": impact,
                        "target": target,
                        "hook": hook,
                        "source_title_candidates": source_title_candidates,
                    },
                )
        return None

    def _build_news_template_candidates(
        self,
        *,
        subject: str,
        event: str,
        impact: str,
        target: str,
        hook: str,
        prefer_short: bool,
    ) -> list[str]:
        subject_event = self._compose_news_subject_event(subject=subject, event=event)
        templates = [
            *self._build_news_surface_candidates(
                subject=subject,
                event=event,
                impact=impact,
                target=target,
                prefer_short=prefer_short,
            ),
            f"{subject_event}：{impact}" if impact else "",
            f"{subject_event}，{impact}" if impact else "",
            subject_event,
            f"{hook}：{impact}" if hook and impact else "",
            f"{hook}，{impact}" if hook and impact else "",
            f"{hook}" if hook else "",
            f"{subject_event}：{target}需要关注的{impact}" if target and impact and not prefer_short else "",
            f"{hook}背后：{subject} {impact}" if hook and impact and not prefer_short else "",
            f"{subject_event}：{target}需要知道的关键信息" if target and not impact and not prefer_short else "",
            f"{subject_event}：变化与影响" if not impact and not prefer_short else "",
        ]
        return self._unique_titles(templates)

    def _build_news_surface_candidates(
        self,
        *,
        subject: str,
        event: str,
        impact: str,
        target: str,
        prefer_short: bool,
    ) -> list[str]:
        candidates: list[str] = []
        normalized_subject = " ".join(str(subject or "").split()).strip()
        normalized_event = " ".join(str(event or "").split()).strip()
        normalized_impact = " ".join(str(impact or "").split()).strip()

        if normalized_event == "贷款动作指向IPO":
            candidates.extend(
                [
                    f"{normalized_subject}大额贷款引出 IPO 预期",
                    f"{normalized_subject}大额贷款背后：IPO 预期升温" if not prefer_short else "",
                    f"{normalized_subject}大额贷款推进 IPO 预期" if not prefer_short else "",
                ]
            )
            if normalized_impact:
                candidates.extend(
                    [
                        f"{normalized_subject}大额贷款引出 IPO 预期：{normalized_impact}",
                        f"{normalized_subject}大额贷款背后，{normalized_impact}" if not prefer_short else "",
                    ]
                )

        if normalized_event == "资本押注与产品调整并行":
            candidates.extend(
                [
                    f"资本还在押注，{normalized_subject}却在调整",
                    f"{normalized_subject}一边被资本押注，一边调整产品方向" if not prefer_short else "",
                ]
            )
            if "Sora" in normalized_subject:
                candidates.extend(
                    [
                        "资本还在押注，OpenAI 却在收缩 Sora",
                        "资本押注下一轮 AI，OpenAI 却在调整 Sora" if not prefer_short else "",
                    ]
                )
            if normalized_impact:
                candidates.append(f"{normalized_subject}：{normalized_impact}")

        if normalized_event == "宣布停运" and "Sora" in normalized_subject:
            candidates.extend(
                [
                    f"{normalized_subject}停运，背后是产品方向调整",
                    "OpenAI 停运 Sora：商业化压力与产品方向再平衡" if not prefer_short else "",
                ]
            )
            if normalized_impact:
                candidates.append(f"{normalized_subject}停运：{normalized_impact}")

        return self._unique_titles(candidates)

    @staticmethod
    def _compose_news_subject_event(*, subject: str, event: str) -> str:
        normalized_subject = " ".join(str(subject or "").split()).strip()
        normalized_event = " ".join(str(event or "").split()).strip()
        if not normalized_subject:
            return normalized_event
        if not normalized_event:
            return normalized_subject
        if re.search(r"[A-Za-z0-9]$", normalized_subject) or normalized_event.startswith(("IPO", "AI", "OpenAI", "Sora", "Claude")):
            return f"{normalized_subject} {normalized_event}"
        return f"{normalized_subject}{normalized_event}"

    def _extract_news_source_title_candidates(self, *, raw_title: str, localized_title: str) -> list[str]:
        candidates: list[str] = []
        for value in (localized_title, raw_title):
            normalized = self._normalize_spaces(value)
            if not self._is_high_signal_news_headline(normalized):
                continue
            candidates.append(normalized)
            clauses = [item.strip("：:- ，。；、！？! ") for item in re.split(r"[！!]", normalized) if item.strip()]
            if len(clauses) >= 2:
                candidates.append("！".join(clauses[:2]))
        return self._unique_titles(candidates)

    def _is_high_signal_news_headline(self, title: str) -> bool:
        value = self._normalize_spaces(title)
        if not value or self._mostly_ascii(value):
            return False
        if len(value) > self.WECHAT_TITLE_MAX_CHARS:
            return False
        clause_count = len([item for item in re.split(r"[，,。；;：:！!]", value) if item.strip()])
        event_hit = any(keyword in value for keyword in self.NEWS_EVENT_KEYWORDS)
        hook_hit = any(keyword in value for keyword in self.NEWS_HOOK_KEYWORDS)
        return clause_count >= 2 and (event_hit or hook_hit)

    @staticmethod
    def _extract_news_organization(text: str) -> str:
        source = str(text or "")
        for name in ("Valve", "OpenAI", "Google", "Anthropic", "MiniMax", "Steam", "微软", "阿里云", "字节", "Meta"):
            if name.lower() in source.lower():
                return name
        return ""

    @staticmethod
    def _extract_primary_metric(*, fact_compress: dict[str, Any], fact_pack: dict[str, Any]) -> str:
        numbers = [str(item).strip() for item in (fact_compress.get("numbers") or fact_pack.get("numbers") or []) if str(item).strip()]
        if not numbers:
            return ""
        return numbers[0][:28]

    def _is_safe_launch_metric(self, *, metric: str, subject: str, raw_title: str, localized_title: str) -> bool:
        normalized_metric = self._normalize_spaces(metric)
        normalized_subject = self._normalize_spaces(subject)
        raw_source = self._normalize_spaces(" ".join(part for part in (raw_title, localized_title) if str(part or "").strip()))
        if not normalized_metric or not normalized_subject:
            return False
        if self._looks_like_date_metric(normalized_metric):
            return False
        if "发布时间" in normalized_metric or "博客发布时间" in normalized_metric:
            return False
        if self._mostly_ascii(normalized_subject):
            return False
        if self._mostly_ascii(raw_source) and not re.search(r"[\u4e00-\u9fff]", normalized_metric):
            return False
        return True

    @staticmethod
    def _looks_like_date_metric(value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lowered = text.lower()
        patterns = (
            r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}",
            r"20\d{2}年\d{1,2}月\d{1,2}日",
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+20\d{2}\b",
        )
        return "publish" in lowered or any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def _extract_english_news_subject(title: str) -> str:
        raw = " ".join(str(title or "").split()).strip()
        if not raw:
            return ""
        match = re.match(
            r"^([A-Z][A-Za-z.+_-]*(?:\s+[A-Z][A-Za-z.+_-]*){0,3})\s+(?:responds|says|announces|launch(?:es|ed)?|introduc(?:e|es|ing)|update|updated|shut(?:s|ting)?\s+down|kills?)\b",
            raw,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    def _article_templates(self, *, pool: str = "", subtype: str = "", semantic_mode: str, tool_name: str, benefit: str, number: str, core_title: str) -> list[str]:
        if semantic_mode == "technical_walkthrough":
            return self._technical_walkthrough_article_templates(tool_name=tool_name, core_title=core_title)
        if semantic_mode == "news_analysis":
            news_focus = self._extract_news_focus(core_title)
            news_subject = self._extract_news_subject(core_title)
            news_event = self._extract_news_event_phrase(raw_title=core_title, localized_title=core_title, text=core_title)
            news_impact = self._extract_news_impact_phrase(text=core_title, localized_title=core_title, fact_pack={})
            return [
                f"{news_subject}{news_event}：{news_impact}" if news_subject and news_event and news_impact else "",
                f"{news_subject}{news_event}" if news_subject and news_event else "",
                core_title,
                f"{news_subject}：{news_focus}",
                f"{news_subject}：变化与影响分析",
                f"{news_subject}事件分析",
            ]
        if semantic_mode == "industry_analysis":
            return [
                *self._core_title_variants(core_title),
                f"{tool_name or core_title}：影响、变化与判断",
                f"{core_title}：关键变化与影响分析",
                f"{tool_name or core_title}：变化观察",
            ]
        if not tool_name:
            return [
                *self._core_title_variants(core_title),
                f"{core_title}：分析",
                f"{core_title}：核心问题与机制",
                f"{core_title}：观察与判断",
            ]
        if "workflow" in semantic_mode:
            return [
                *self._core_title_variants(core_title),
                f"{tool_name or core_title}：工作流设计与落地",
                f"{tool_name or core_title}：能力边界与工作流价值",
                f"{core_title}：工作流实践分析",
            ]
        if "tutorial" in semantic_mode:
            return [
                *self._core_title_variants(core_title),
                f"{tool_name or core_title}：实践指南",
                f"{tool_name or core_title}：部署与使用指南",
                f"{core_title}：从原理到实践",
            ]
        return [
            *self._core_title_variants(core_title),
            f"{tool_name or core_title}：产品定位与使用场景",
            f"{tool_name or core_title}：核心能力与适用边界",
            f"{core_title}：产品分析",
            f"{core_title}：能力解析",
        ]

    def _wechat_templates(self, *, pool: str = "", subtype: str = "", semantic_mode: str, tool_name: str, benefit: str, number: str, core_title: str) -> list[str]:
        if semantic_mode == "technical_walkthrough":
            return self._technical_walkthrough_wechat_templates(tool_name=tool_name, core_title=core_title)
        if semantic_mode == "news_analysis":
            news_focus = self._extract_news_focus(core_title)
            news_subject = self._extract_news_subject(core_title)
            news_event = self._extract_news_event_phrase(raw_title=core_title, localized_title=core_title, text=core_title)
            news_impact = self._extract_news_impact_phrase(text=core_title, localized_title=core_title, fact_pack={})
            return [
                f"{news_subject}{news_event}：{news_impact}" if news_subject and news_event and news_impact else "",
                f"{news_subject}{news_event}" if news_subject and news_event else "",
                f"{news_subject}：{news_focus}",
                f"{news_subject}变化分析",
                f"{news_subject}事件分析",
                *self._core_title_variants(core_title),
            ]
        if semantic_mode == "industry_analysis":
            return [
                f"{tool_name}变化判断" if tool_name else "",
                f"{tool_name}影响分析" if tool_name else "",
                f"{tool_name or core_title}变化观察",
                f"{core_title}分析",
                *self._core_title_variants(core_title),
            ]
        if not tool_name:
            return [
                f"{core_title}分析",
                *self._core_title_variants(core_title),
                f"{core_title}观察",
            ]
        return [
            f"{tool_name}：核心能力分析" if tool_name else "",
            f"{tool_name}：能力边界" if tool_name else "",
            f"{core_title}分析",
            *self._core_title_variants(core_title),
        ]

    def _technical_walkthrough_article_templates(self, *, tool_name: str, core_title: str) -> list[str]:
        head = self._normalize_spaces(tool_name or self._title_head_before_colon(core_title) or core_title)
        positioning = self._extract_positioning_phrase(core_title)
        candidates = []
        if head and positioning:
            candidates.extend(
                [
                    f"{head}：{positioning}，架构与实现拆解",
                    f"{head}：{positioning}的设计与实现",
                ]
            )
        if head:
            candidates.extend(
                [
                    f"{head}：系统设计与实现拆解",
                    f"{head}：架构、链路与工程取舍",
                ]
            )
        candidates.append(f"{core_title}：技术实现拆解")
        candidates.extend(self._core_title_variants(core_title))
        return self._unique_titles(candidates)

    def _technical_walkthrough_wechat_templates(self, *, tool_name: str, core_title: str) -> list[str]:
        head = self._normalize_spaces(tool_name or self._title_head_before_colon(core_title) or core_title)
        positioning = self._compact_positioning_phrase(self._extract_positioning_phrase(core_title))
        candidates = []
        if head and positioning:
            candidates.extend(
                [
                    f"{head}：{positioning}拆解",
                    f"{head}：架构与实现拆解",
                ]
            )
        if head:
            candidates.extend(
                [
                    f"{head}架构拆解",
                    f"{head}实现拆解",
                    f"{head}技术拆解",
                ]
            )
        candidates.extend(self._core_title_variants(core_title))
        candidates.append(f"{core_title}解读")
        return self._unique_titles(candidates)

    @staticmethod
    def _unique_titles(candidates: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in candidates:
            value = " ".join(str(candidate or "").split()).strip()
            if value and value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

    def _core_title_variants(self, core_title: str) -> list[str]:
        value = self._normalize_spaces(core_title)
        if not value:
            return []

        variants: list[str] = []
        seen: set[str] = set()

        def add(candidate: str) -> None:
            normalized = self._normalize_spaces(candidate).strip("：:- ,.;")
            if normalized and normalized not in seen:
                seen.add(normalized)
                variants.append(normalized)

        add(value)

        match = re.match(r"^(?P<head>[^：:]{2,32})[：:](?P<tail>.+)$", value)
        if not match:
            return variants

        head = match.group("head").strip()
        tail = match.group("tail").strip()
        first_clause = re.split(r"[，,；;]", tail, maxsplit=1)[0].strip()
        if first_clause:
            add(f"{head}：{first_clause}")

        positioning_match = re.search(
            r"(面向\s*AI Agent\s*的[^，,；;]+|AI Agent\s*的[^，,；;]+|零信任安全运行时|安全运行时|Agent 运行时)",
            tail,
            flags=re.IGNORECASE,
        )
        if positioning_match:
            add(f"{head}：{positioning_match.group(1).strip()}")

        risk_match = re.search(r"(\d+)\s*层检查拦截\s*rm -rf\s*等危险命令", tail, flags=re.IGNORECASE)
        if risk_match:
            add(f"{head}：{risk_match.group(1)} 层检查拦截危险命令")

        return variants

    def _pick_best_title(self, candidates: list[str], *, prefer_short: bool, semantic_mode: str = "") -> str:
        best_title = ""
        best_score = -1
        for candidate in candidates:
            title = self._normalize_spaces(candidate)
            if not title:
                continue
            score = self._score_title(title, prefer_short=prefer_short, semantic_mode=semantic_mode)
            if score > best_score:
                best_score = score
                best_title = title
        return best_title

    def _score_title(self, title: str, *, prefer_short: bool, semantic_mode: str = "") -> int:
        score = 50
        length = len(title)
        if prefer_short:
            if 10 <= length <= 24:
                score += 20
            elif length <= 32:
                score += 14
            elif length <= 40:
                score += 4
            elif length <= self.WECHAT_TITLE_MAX_CHARS:
                score -= 12
            else:
                score -= 20
        else:
            if 14 <= length <= 30:
                score += 20
            elif length <= 40:
                score += 10
            else:
                score -= 15
        if any(char.isdigit() for char in title):
            score += 6
        if any(kw in title for kw in ("效率", "上手", "实战", "重点", "落地", "解读", "工作流")):
            score += 8
        if any(kw in title for kw in ("架构", "拆解", "实现", "设计", "工程取舍")):
            score += 12
        if any(kw in title for kw in self.PROFESSIONAL_TITLE_KEYWORDS):
            score += 10
        if any(kw in title for kw in ("收费", "计费", "涨价", "降价", "变化", "调整", "融资", "发布", "更新")):
            score += 10
        if any(kw in title for kw in ("背后", "预期升温", "停运", "押注", "收缩")):
            score += 8
        if any(kw in title for kw in self.NEWS_EVENT_KEYWORDS) and len(title) >= 18:
            score += 12
        if any(kw in title for kw in self.NEWS_IMPACT_KEYWORDS):
            score += 10
        if any(kw in title for kw in ("运行时", "框架", "工作流", "安全", "防护", "风险", "命令", "零信任")):
            score += 8
        if any(phrase in title for phrase in self.GENERIC_TITLE_PHRASES):
            score -= 8
        if any(phrase in title for phrase in self.GENERIC_NEWS_TITLE_PHRASES):
            score -= 18
        if any(phrase in title for phrase in self.COLLOQUIAL_TITLE_PHRASES):
            score -= 18
        if "？" in title or "?" in title:
            score -= 14
        if str(semantic_mode or "").strip() == "news_analysis":
            event_hit = any(kw in title for kw in self.NEWS_EVENT_KEYWORDS)
            impact_hit = any(kw in title for kw in self.NEWS_IMPACT_KEYWORDS)
            hook_hit = any(kw in title for kw in self.NEWS_HOOK_KEYWORDS)
            if event_hit:
                score += 10
            if impact_hit:
                score += 12
            if hook_hit:
                score += 10
            if event_hit and impact_hit:
                score += 18
            if self._is_high_signal_news_headline(title):
                score += 20
            if ("：" in title or "，" in title) and event_hit and impact_hit:
                score += 6
            if "相关变化" not in title and any(kw in title for kw in ("背后", "却在", "引出", "停运")):
                score += 6
        if str(semantic_mode or "").strip() == "technical_walkthrough":
            if any(kw in title for kw in ("架构", "拆解", "实现", "设计", "机制", "工程取舍")):
                score += 14
            elif any(kw in title for kw in ("命令", "收费", "融资", "变化", "发布")):
                score -= 14
        if self._contains_awkward_title_pattern(title):
            score -= 28
        if any(phrase in title for phrase in ("AI代理", "Open source ", "检查防", "against rm -rf")):
            score -= 20
        if any(kw in title for kw in self.SUBJECTIVE_TITLE_PHRASES):
            score -= 18
        if self._mostly_ascii(title):
            score -= 12
        if len(title.encode("utf-8")) > (self.WECHAT_TITLE_MAX_BYTES if prefer_short else 180):
            score -= 20
        return score

    def _default_article_title(self, core_title: str, tool_name: str, benefit: str, *, semantic_mode: str = "") -> str:
        if str(semantic_mode or "").strip() == "news_analysis":
            return self._normalize_spaces(core_title) or (f"{tool_name}最新进展" if tool_name else "AI 行业最新进展")
        if tool_name:
            return f"{tool_name}：产品分析"
        return f"{core_title}：分析"

    def _default_wechat_title(self, article_title: str, tool_name: str, *, semantic_mode: str = "") -> str:
        if str(semantic_mode or "").strip() == "news_analysis":
            return self._normalize_spaces(article_title)
        if tool_name:
            return f"{tool_name}分析"
        simplified = re.sub(r"[:：].*$", "", article_title).strip()
        return simplified or article_title

    def _extract_core_title(self, topic: dict[str, Any]) -> str:
        title = self._normalize_spaces(str(topic.get("title", "") or "AI 热点"))
        title = re.sub(r"\s*[|丨｜]\s*.*$", "", title).strip()
        title = re.sub(r"\s+-\s+.*$", "", title).strip()
        return title[:120]

    def _extract_tool_name(self, topic: dict[str, Any]) -> str:
        title = self._extract_core_title(topic)
        explicit_candidates = re.findall(r'([A-Z][A-Za-z0-9.+_-]{2,})', title)
        scored_candidates = [
            candidate
            for candidate in explicit_candidates
            if candidate.lower() not in {"what", "using", "creating", "could", "mean", "files"}
        ]
        scored_candidates.sort(
            key=lambda item: (
                1 if re.search(r"(GPT|AI|Code|Studio|Flow|Agent|Speech|Tracking|Search)$", item) else 0,
                len(item),
            ),
            reverse=True,
        )
        if scored_candidates:
            return scored_candidates[0][:32]
        for product in self.PRODUCT_HINTS:
            if product.lower() in title.lower():
                return product
        guessed = self._guess_tool_name(title)
        if guessed:
            return guessed
        if not self._mostly_ascii(title):
            return title[:18]
        return ""

    def _extract_benefit(self, topic: dict[str, Any], fact_pack: dict[str, Any], fact_compress: dict[str, Any]) -> str:
        text = " ".join(
            [
                str(topic.get("title", "") or ""),
                str(topic.get("summary", "") or ""),
                str(fact_compress.get("one_sentence_summary", "") or ""),
                " ".join(str(item) for item in fact_pack.get("key_points", [])[:4]),
            ]
        ).lower()
        mapping = [
            ("安全性", ("security", "safe", "safety", "安全", "防护", "零信任", "风险", "拦截", "隔离")),
            ("效率", ("efficiency", "productivity", "提效", "效率", "省时", "save time")),
            ("工作流", ("workflow", "工作流", "协同", "自动化", "automation")),
            ("开发效率", ("developer", "coding", "code", "开发", "编程", "写代码")),
            ("落地速度", ("launch", "ship", "上线", "落地", "部署")),
            ("团队协作", ("team", "collaboration", "协作", "团队")),
        ]
        for benefit, keywords in mapping:
            if any(keyword in text for keyword in keywords):
                return benefit
        return "效率提升"

    def _extract_number(self, topic: dict[str, Any], fact_pack: dict[str, Any], fact_compress: dict[str, Any]) -> str:
        text = " ".join(
            [
                str(topic.get("title", "") or ""),
                str(topic.get("summary", "") or ""),
                json.dumps(fact_compress.get("numbers", []), ensure_ascii=False),
                json.dumps(fact_pack.get("numbers", []), ensure_ascii=False),
            ]
        )
        numbers = re.findall(r"\b([3-9]|10)\b", text)
        return numbers[0] if numbers else "3"

    def _localize_title(self, title: str) -> str:
        command_token = "__RM_RF__"
        normalized = str(title or "").replace("rm -rf", command_token).replace("rm-rf", command_token)
        normalized = normalized.replace("-", " ").replace(command_token, "rm -rf")
        lower_title = normalized.lower()
        rewritten = self._rewrite_patterned_english_title(title)
        if rewritten:
            return rewritten
        if "multi agent systems" in lower_title and "software development" in lower_title:
            return "多代理系统重塑软件开发"
        if "claude code" in lower_title and "session" in lower_title:
            if "mistake" in lower_title or "repeat" in lower_title:
                return "Claude Code 会话复盘"
            return "Claude Code 会话拆解"
        if (
            "claude code" in lower_title
            and "openclaw" in lower_title
            and (
                "pay extra" in lower_title
                or "will need to pay extra" in lower_title
                or "billing" in lower_title
            )
        ):
            return "Claude Code 调用 OpenClaw 将单独收费"

        localized = normalized
        for src, target in sorted(self.ENGLISH_PHRASE_MAP.items(), key=lambda item: len(item[0]), reverse=True):
            if src in lower_title:
                localized = re.sub(src, target, localized, flags=re.IGNORECASE)
        localized = self._normalize_spaces(localized)
        localized = localized.replace("  ", " ").strip(" -|：:")
        if self._mostly_ascii(localized):
            words = [
                word
                for word in re.findall(r"[A-Za-z0-9]+", localized)
                if word.lower() not in self.ENGLISH_STOPWORDS
            ]
            if words:
                localized = " ".join(words[:4]).strip()
        if self._mostly_ascii(localized):
            tool_name = self._extract_tool_name({"title": localized})
            if tool_name:
                return f"{tool_name} 相关变化"
        return localized

    def _extract_positioning_phrase(self, core_title: str) -> str:
        value = self._normalize_spaces(core_title)
        if not value:
            return ""
        match = re.search(
            r"(面向\s*AI Agent\s*的[^，,；;]+|AI Agent\s*的[^，,；;]+|零信任安全运行时|安全运行时|Agent 运行时)",
            value,
            flags=re.IGNORECASE,
        )
        return self._normalize_spaces(match.group(1)) if match else ""

    @staticmethod
    def _compact_positioning_phrase(positioning: str) -> str:
        value = " ".join(str(positioning or "").split()).strip()
        value = value.replace("面向 AI Agent 的", "")
        value = value.replace("AI Agent 的", "")
        value = value.strip("：:- ")
        return value

    def _rewrite_patterned_english_title(self, title: str) -> str:
        raw = self._normalize_spaces(title)
        lower = raw.lower()
        tool_name = self._guess_tool_name(raw)
        if not tool_name:
            return ""

        is_open_source = bool(re.search(r"\bopen[- ]source(?:d)?\b", lower))
        has_agent_runtime = ("runtime" in lower or "sandbox" in lower) and (
            "ai agent" in lower or "ai agents" in lower or "agent runtime" in lower
        )
        has_zero_trust = "zero trust" in lower or "zero-trust" in lower
        check_match = re.search(
            r"(\d+)\s*[- ]?layer\s+checks?\s+against\s+(rm\s*-\s*rf(?:\s+[a-z0-9._/-]+)*)",
            raw,
            flags=re.IGNORECASE,
        )

        if has_agent_runtime or has_zero_trust:
            prefix = f"{tool_name} 开源" if is_open_source else tool_name
            positioning = "面向 AI Agent 的零信任安全运行时" if has_zero_trust else "面向 AI Agent 的安全运行时"
            if check_match:
                command = self._normalize_command_phrase(check_match.group(2))
                return f"{prefix}：{positioning}，通过 {check_match.group(1)} 层检查拦截 {command} 等危险命令"
            return f"{prefix}：{positioning}"
        if is_open_source:
            return f"{tool_name} 开源"
        return ""

    @staticmethod
    def _extract_news_subject(core_title: str) -> str:
        raw = str(core_title or "").strip()
        lowered = raw.lower()
        if "softbank" in lowered and "openai" in lowered:
            return "SoftBank 与 OpenAI"
        if "openai" in lowered and "sora" in lowered:
            return "OpenAI 与 Sora"
        if "chatgpt" in lowered:
            return "ChatGPT"
        if "claude code" in lowered and "openclaw" in lowered:
            return "Claude Code 与 OpenClaw"
        if "claude code" in lowered:
            return "Claude Code"
        if "anthropic" in lowered and "claude" in lowered:
            return "Anthropic Claude"
        if "claude" in lowered:
            return "Claude"
        for product in TitleGenerationService.PRODUCT_HINTS:
            if product.lower() in lowered:
                return product
        if "openclaw" in lowered:
            quoted_with_company = re.match(r"^(.{2,32}?[A-Za-z][^，,。；;]{0,18}“[^”]{1,12}”)", raw)
            if quoted_with_company:
                return quoted_with_company.group(1).strip("：:，, ")
            if re.search(r"[\u4e00-\u9fff]", raw):
                match = re.match(r"^(.{2,32}?)(?:获|宣布|发布|推出|上线|更新|调整|开源|回应|收购|完成)", raw)
                if match:
                    return match.group(1).strip("：:，, ")
            return "OpenClaw"
        quoted = re.match(r"^(.{2,32}?“[^”]{1,12}”)", raw)
        if quoted:
            return quoted.group(1).strip("：:，, ")
        match = re.match(r"^(.{2,32}?)(?:获|宣布|发布|推出|上线|更新|调整|开源|回应|收购|完成)", raw)
        if match:
            return match.group(1).strip("：:，, ")
        match = re.match(r"^(.{2,32}?)[：:，,]", raw)
        if match:
            return match.group(1).strip("：:，, ")
        return raw[:24] or "AI 行业动态"

    @staticmethod
    def _extract_news_focus(core_title: str) -> str:
        lowered = str(core_title or "").lower()
        if "融资" in core_title or "新一轮" in core_title:
            return "获新一轮融资"
        if "发布" in core_title or "推出" in core_title:
            return "新产品发布"
        if "上线" in core_title:
            return "新能力上线"
        if "更新" in core_title:
            return "关键更新解读"
        if "单独收费" in core_title or "额外付费" in core_title:
            return "调用将单独收费"
        if "订阅不再覆盖" in core_title:
            return "订阅不再覆盖调用"
        if "计费" in core_title:
            return "计费规则调整"
        if "pay extra" in lowered or "will need to pay extra" in lowered:
            if "openclaw" in lowered:
                return "调用将单独收费"
            return "需额外付费"
        if "billing" in lowered or "pricing" in lowered:
            return "计费规则调整"
        if "support" in lowered:
            return "支持策略变化"
        if "introducing" in lowered or "launch" in lowered or "launches" in lowered:
            return "新能力发布"
        if "acquire" in lowered or "acquisition" in lowered:
            return "收购动作披露"
        if "shut down" in lowered or "shutdown" in lowered:
            return "产品停运"
        if "raises" in lowered or "raised" in lowered or "fund" in lowered:
            return "融资进展"
        if "leaves" in lowered or "left" in lowered:
            return "人事变化"
        return "最新变化解读"

    def _extract_news_event_phrase(self, *, raw_title: str, localized_title: str, text: str) -> str:
        source = self._normalize_spaces(" ".join(part for part in (raw_title, localized_title, text) if str(part or "").strip()))
        if not source:
            return ""
        if re.search(r"\bresponds?\b.*\bnew yorker\b|\battack on (?:his|her) home\b", source, flags=re.IGNORECASE):
            return "回应争议报道与安全事件"
        if re.search(r"(?:回应|响应).*(?:纽约客|报道)|(?:住家遇袭|住宅遇袭)", source):
            return "回应争议报道与安全事件"
        explicit_map = (
            (r"(?:单独收费|单独计费|额外付费)", "调用将单独收费"),
            (r"(?:订阅不再覆盖|不再覆盖)", "订阅不再覆盖调用"),
            (r"(?:获新一轮融资|完成新一轮融资|新一轮融资)", "获新一轮融资"),
            (r"(?:发布新版本|发布新产品|正式发布)", "发布新版本"),
            (r"(?:开源|正式开源|宣布开源)", "正式开源"),
            (r"(?:上线新能力|正式上线)", "正式上线"),
            (r"(?:计费规则调整|价格调整)", "计费规则调整"),
            (r"(?:入局具身创业|入局创业)", "入局具身创业"),
            (r"(?:首个模型登顶|登顶.*榜单|登顶.*Arena|登顶)", "登顶榜单"),
            (r"(?:贷款|loan).*(?:ipo|上市)|(?:ipo|上市).*(?:贷款|loan)", "贷款动作指向IPO"),
            (r"(?:押注).*(?:sora|openai)|(?:betting billions).*(?:sora|openai)", "资本押注与产品调整并行"),
        )
        lowered = source.lower()
        for pattern, phrase in explicit_map:
            if re.search(pattern, source, flags=re.IGNORECASE):
                return phrase
        if "openclaw" in lowered and ("claude code" in lowered or "claude" in lowered) and re.search(r"(收费|计费|extra|billing)", source, flags=re.IGNORECASE):
            return "调用 OpenClaw 将单独收费"
        english_map = (
            (r"\b(?:introducing|launch(?:es|ed)?)\b", "发布新能力"),
            (r"\b(?:acquire|acquires|acquisition)\b", "披露收购计划"),
            (r"\b(?:shut down|shutdown)\b", "宣布停运"),
            (r"\b(?:raises|raised|funding|fund)\b", "披露融资进展"),
            (r"\b(?:leaves|left)\b", "出现人事变化"),
            (r"\b(?:announces|announced|update on)\b", "发布最新进展"),
            (r"\bpowering product discovery\b", "强化商品导购能力"),
            (r"\bpopularity .*skyrocketing\b", "付费用户增长提速"),
            (r"\bipo\b", "IPO预期升温"),
            (r"\bloan points to\b", "融资动作指向IPO"),
            (r"\bbetting billions on\b", "资本加码押注"),
            (r"\bnew \$?\d+(?:\.\d+)?b loan\b", "大额贷款推进融资布局"),
            (r"\bkilling sora\b", "产品调整引发资本分歧"),
        )
        for pattern, phrase in english_map:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return phrase
        clauses = [item.strip("：:- ，。；、") for item in re.split(r"[，,。；;]", self._normalize_spaces(localized_title or raw_title)) if item.strip()]
        for clause in clauses[1:]:
            if any(keyword in clause for keyword in self.NEWS_EVENT_KEYWORDS):
                return clause[:24]
        for clause in clauses:
            if any(keyword in clause for keyword in self.NEWS_EVENT_KEYWORDS):
                return clause[:24]
        return ""

    def _extract_news_impact_phrase(self, *, text: str, localized_title: str, fact_pack: dict[str, Any]) -> str:
        source = self._normalize_spaces(
            " ".join(
                [
                    str(localized_title or ""),
                    str(text or ""),
                    " ".join(str(item).strip() for item in (fact_pack.get("key_points") or [])[:3] if str(item).strip()),
                ]
            )
        )
        if not source:
            return ""
        if re.search(r"\bnew yorker\b|\btrust\b|\bsafety\b|\bpublic reaction\b", source, flags=re.IGNORECASE):
            return "舆论压力与 AI 信任风险继续升温"
        if re.search(r"(?:舆论|信任|安全).*(?:讨论|升温|风险)", source):
            return "舆论压力与 AI 信任风险继续升温"
        explicit_map = (
            (r"订阅.*(?:不再覆盖|单独收费|单独计费)", "订阅不再覆盖相关调用"),
            (r"开发者.*(?:额外付费|单独收费|单独计费|成本)", "开发者调用成本将上升"),
            (r"(?:端侧|端侧大模型|端侧模型)", "端侧大模型布局继续推进"),
            (r"(?:企业|团队).*(?:成本|效率|部署)", "企业落地成本与效率将变化"),
            (r"(?:开源|上线|发布).*(?:生态|开发者|社区)", "开发者生态和接入方式变化"),
            (r"subscribers?.*(?:no longer|not included|pay extra|separate billing)", "订阅不再覆盖相关调用"),
            (r"developers?.*(?:pay extra|separate billing|extra per use|cost)", "开发者调用成本将上升"),
            (r"teen safety|safety policies", "面向青少年的安全约束升级"),
            (r"bug bounty|vulnerabilities|prompt injection|data exfiltration", "安全治理和漏洞响应升级"),
            (r"shopping|merchant integration|product discovery", "ChatGPT 商业化和导购能力继续扩展"),
            (r"invest at least|\\$1 billion|economic opportunity|community programs", "基金投入规模与公益方向同步扩大"),
            (r"knowledge work|saving time|productivity", "企业内部知识工作效率继续提升"),
            (r"视频生成数据|家用机器人|具身", "具身机器人训练和落地进度被拉快"),
            (r"paying consumers|paid users|consumer adoption|consumer demand", "付费用户渗透和产品热度继续走高"),
            (r"ipo|public offering|go public", "资本市场对上市节奏的预期升温"),
            (r"loan|credit line|debt financing", "融资弹药和资本运作空间继续扩大"),
            (r"betting billions|backing|capital wave|next wave", "资本继续押注下一轮 AI 竞争"),
            (r"valuation|valued at", "估值预期和资本博弈同步升温"),
            (r"killing sora|shut down sora|scale(?:s|d)? back sora", "资本判断和产品方向出现分歧"),
            (r"loan points to|new .*loan .*ipo", "大额贷款被视为 IPO 前置信号"),
        )
        for pattern, phrase in explicit_map:
            if re.search(pattern, source, flags=re.IGNORECASE):
                return phrase
        clauses = [item.strip("：:- ，。；、") for item in re.split(r"[，,。；;]", source) if item.strip()]
        for clause in clauses:
            if any(keyword in clause for keyword in self.NEWS_IMPACT_KEYWORDS) and not any(keyword in clause for keyword in self.NEWS_EVENT_KEYWORDS):
                return clause[:22]
        for key_point in fact_pack.get("key_points") or []:
            value = self._normalize_spaces(str(key_point or ""))
            if any(keyword in value for keyword in self.NEWS_IMPACT_KEYWORDS) and not any(
                keyword in value for keyword in self.NEWS_EVENT_KEYWORDS
            ):
                return value[:22]
        return ""

    def _extract_news_target_audience(self, *, text: str, subject: str) -> str:
        source = self._normalize_spaces(f"{subject} {text}").lower()
        mapping = (
            (("开发者", "developer", "developers", "coding"), "开发者"),
            (("企业", "enterprise", "business", "team"), "企业团队"),
            (("机器人", "robot", "embodied"), "机器人团队"),
            (("订阅", "subscriber", "subscribers"), "订阅用户"),
            (("商家", "merchant", "shopping", "discovery"), "商家与平台团队"),
            (("青少年", "teen", "teen safety"), "平台治理团队"),
            (("investor", "investors", "capital", "ipo", "valuation", "loan"), "投资人与资本市场"),
        )
        for keywords, target in mapping:
            if any(keyword in source for keyword in keywords):
                return target
        return ""

    def _extract_news_hook_phrase(self, *, raw_title: str, localized_title: str, text: str) -> str:
        source = self._normalize_spaces(" ".join(part for part in (raw_title, localized_title, text) if str(part or "").strip()))
        if not source:
            return ""
        clauses = [item.strip("：:- ，。；、！？! ") for item in re.split(r"[，,。；;]", source) if item.strip()]
        selected: list[str] = []
        for clause in clauses:
            if not re.search(r"[\u4e00-\u9fff]", clause):
                continue
            if re.match(r"^[A-Za-z0-9$]", clause):
                continue
            if re.match(r"^(?:被视为|被看作|意味着|说明|显示|预示|反映|信号是|这意味着)", clause):
                continue
            if any(keyword in clause for keyword in self.NEWS_HOOK_KEYWORDS):
                selected.append(clause[:20])
            if len(selected) == 2:
                break
        if selected:
            return "，".join(selected)
        return ""

    def _extract_news_subject_from_key_points(self, fact_pack: dict[str, Any]) -> str:
        for key_point in fact_pack.get("key_points") or []:
            value = self._normalize_spaces(str(key_point or ""))
            if not value:
                continue
            match = re.match(r"^(.{2,32}?)(?:获|完成|宣布|发布|推出|上线|更新|调整|开源|回应|收购)", value)
            if match:
                return match.group(1).strip("：:，, ")
        return ""

    def _is_valid_title_plan(
        self,
        *,
        article_title: str,
        wechat_title: str,
        topic: dict[str, Any],
        pool: str = "",
        subtype: str = "",
        semantic_mode: str,
    ) -> bool:
        if not self._is_natural_title(article_title) or not self._is_natural_title(wechat_title):
            return False
        if not self._is_news_semantics(pool=pool, subtype=subtype):
            return True
        return self._is_valid_news_title(article_title, topic=topic) and self._is_valid_news_title(wechat_title, topic=topic)

    def _resolve_content_semantics(
        self,
        *,
        pool: str = "",
        subtype: str = "",
        fact_pack: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        resolved_pool = str(pool or "").strip()
        resolved_subtype = str(subtype or "").strip()
        payload = dict(fact_pack or {})
        if not resolved_pool:
            resolved_pool = str(payload.get("primary_pool", "") or payload.get("pool", "") or "").strip()
        if not resolved_subtype:
            resolved_subtype = str(payload.get("subtype", "") or "").strip()
        if resolved_pool == "news":
            resolved_subtype = resolved_subtype or "industry_news"
        elif resolved_pool == "github":
            resolved_subtype = resolved_subtype or "repo_recommendation"
        elif resolved_pool == "deep_dive":
            resolved_subtype = resolved_subtype or "tool_review"
        return resolved_pool, resolved_subtype, self._semantic_title_mode(pool=resolved_pool, subtype=resolved_subtype)

    @staticmethod
    def _semantic_title_mode(*, pool: str = "", subtype: str = "") -> str:
        normalized_pool = str(pool or "").strip()
        normalized_subtype = str(subtype or "").strip()
        if normalized_pool == "news" or normalized_subtype in {"breaking_news", "industry_news", "capital_signal", "controversy_risk"}:
            return "news_analysis"
        if normalized_subtype in {"code_explainer", "stack_analysis", "technical_walkthrough"}:
            return "technical_walkthrough"
        if normalized_subtype == "tutorial":
            return "tutorial"
        if normalized_subtype in {"repo_recommendation", "collection_repo", "tool_review"}:
            return "tool_review"
        return "tool_review"

    @staticmethod
    def _is_news_semantics(*, pool: str = "", subtype: str = "") -> bool:
        normalized_pool = str(pool or "").strip()
        normalized_subtype = str(subtype or "").strip()
        return normalized_pool == "news" or normalized_subtype in {
            "breaking_news",
            "industry_news",
            "capital_signal",
            "controversy_risk",
        }

    def _is_natural_title(self, title: str) -> bool:
        value = self._normalize_spaces(title)
        if not value:
            return False
        return not self._contains_awkward_title_pattern(value)

    def _contains_awkward_title_pattern(self, title: str) -> bool:
        value = self._normalize_spaces(title)
        return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in self.AWKWARD_TITLE_PATTERNS)

    def _is_valid_news_title(self, title: str, *, topic: dict[str, Any]) -> bool:
        value = self._normalize_spaces(title)
        if not value:
            return False
        if any(phrase in value for phrase in self.SUBJECTIVE_TITLE_PHRASES):
            return False
        if any(phrase in value for phrase in self.GENERIC_NEWS_TITLE_PHRASES) and not any(
            keyword in value for keyword in self.NEWS_IMPACT_KEYWORDS
        ):
            return False
        core_title = self._extract_core_title(topic)
        subject = self._extract_news_subject(core_title)
        anchor_terms = self._extract_news_anchor_terms(core_title)
        subject_hit = bool(subject and subject in value)
        anchor_hit = any(term in value for term in anchor_terms)
        event_hit = any(keyword in value for keyword in self.NEWS_EVENT_KEYWORDS)
        return (subject_hit or anchor_hit) and event_hit

    def _extract_news_anchor_terms(self, core_title: str) -> list[str]:
        raw = str(core_title or "").strip()
        terms: list[str] = []
        subject = self._extract_news_subject(raw)
        if subject:
            terms.append(subject)
        for product in self.PRODUCT_HINTS:
            if product.lower() in raw.lower() and product not in terms:
                terms.append(product)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9.+_-]{1,20}|[\u4e00-\u9fff]{2,8}", raw):
            cleaned = str(token).strip()
            if len(cleaned) < 2 or cleaned in terms or cleaned in self.NEWS_EVENT_KEYWORDS:
                continue
            terms.append(cleaned)
        return terms[:8]

    @staticmethod
    def _parse_llm_result(text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            value = json.loads(text[start : end + 1])
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    def validate_title_plan(
        self,
        *,
        article_title: str,
        wechat_title: str,
        topic: dict[str, Any],
        pool: str = "",
        subtype: str = "",
    ) -> dict[str, Any]:
        return self._title_validator().validate_plan(
            article_title=article_title,
            wechat_title=wechat_title,
            topic=topic,
            pool=pool,
            subtype=subtype,
        )

    def _clean_article_title(self, title: str) -> str:
        cleaned = self._polish_title_surface(title)
        for word in self.CLICKBAIT_WORDS:
            cleaned = cleaned.replace(word, "")
        cleaned = cleaned.strip("：:- ")
        cleaned = cleaned[: self.ARTICLE_TITLE_MAX_CHARS].strip()
        return cleaned or "AI 热点：实战解读"

    def _clean_wechat_title(self, title: str) -> str:
        cleaned = self._polish_title_surface(title)
        for word in self.CLICKBAIT_WORDS:
            cleaned = cleaned.replace(word, "")
        cleaned = re.sub(r"(：实战解读|：深度解读|：落地建议|：完整指南)$", "", cleaned).strip()
        cleaned = self._compact_wechat_title(cleaned)
        cleaned = self._truncate_word_boundary(cleaned, self.WECHAT_TITLE_MAX_CHARS)
        cleaned = self._truncate_utf8_bytes(cleaned, self.WECHAT_TITLE_MAX_BYTES)
        cleaned = cleaned.strip("：:- ,.;")
        if not cleaned:
            cleaned = "AI 热点解读"
        return cleaned

    def _compact_wechat_title(self, title: str) -> str:
        value = self._normalize_spaces(title)
        if not value or self._fits_wechat_title_limit(value):
            return value

        candidates: list[str] = []
        seen: set[str] = set()

        def add(candidate: str) -> None:
            normalized = self._normalize_spaces(candidate).strip("：:- ,.;！？?，；")
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)

        add(value)
        add(re.sub(r"[？?！!]+$", "", value))
        add(re.sub(r"\s*[（(][^()（）]{1,24}[)）]\s*$", "", value))

        match = re.match(r"^(?P<head>[^：:]{2,24})[：:](?P<tail>.+)$", value)
        if match:
            head = match.group("head").strip()
            tail = match.group("tail").strip()
            clauses = [item.strip() for item in re.split(r"[，,；;]", tail) if item.strip()]

            add(head)
            add(f"{head}：{self._strip_wechat_question_prefix(tail)}")
            for clause in clauses:
                add(clause)
                add(self._strip_wechat_question_prefix(clause))
                add(f"{head}：{clause}")
                add(f"{head}：{self._strip_wechat_question_prefix(clause)}")

            numeric_phrase = self._extract_numeric_title_phrase(tail)
            if numeric_phrase:
                add(f"{head}：{numeric_phrase}")

        best = value
        best_score = -10**9
        for candidate in candidates:
            score = self._score_compact_wechat_candidate(candidate=candidate, original=value)
            if score > best_score:
                best_score = score
                best = candidate
        return best

    def _score_compact_wechat_candidate(self, *, candidate: str, original: str) -> int:
        score = self._score_title(candidate, prefer_short=True)
        if self._fits_wechat_title_limit(candidate):
            score += 30
        else:
            score -= 45
        original_head = self._title_head_before_colon(original)
        candidate_head = self._title_head_before_colon(candidate)
        if original_head and candidate_head == original_head:
            score += 12
        if re.search(r"\d", original) and re.search(r"\d", candidate):
            score += 6
        if re.search(r"(?:\d+\.\d+|\d+)$", candidate):
            score -= 14
        if candidate.endswith(("：", ":", "，", ",", "（", "(")):
            score -= 18
        if candidate == original:
            score += 2
        return score

    def _fits_wechat_title_limit(self, text: str) -> bool:
        value = str(text or "").strip()
        return len(value) <= self.WECHAT_TITLE_MAX_CHARS and len(value.encode("utf-8")) <= self.WECHAT_TITLE_MAX_BYTES

    @staticmethod
    def _title_head_before_colon(text: str) -> str:
        value = str(text or "").strip()
        if "：" in value:
            return value.split("：", 1)[0].strip()
        if ":" in value:
            return value.split(":", 1)[0].strip()
        return ""

    @staticmethod
    def _strip_wechat_question_prefix(text: str) -> str:
        value = str(text or "").strip()
        value = re.sub(r"^(?:如何|怎么|怎样|为何|为什么|究竟|到底)", "", value)
        value = re.sub(r"^(?:实现|做到|兼顾|融合|平衡|达到|拿到|做到)", "", value)
        return value.strip("：:- ,.;！？?，；")

    @staticmethod
    def _extract_numeric_title_phrase(text: str) -> str:
        match = re.search(
            r"(\d+(?:\.\d+)?%?\s*(?:准确率|成本|延迟|性能|效率|提效|速度|参数|节点|步骤|轮|页|秒|分钟|倍|个)?)",
            str(text or ""),
            flags=re.IGNORECASE,
        )
        return str(match.group(1) or "").strip() if match else ""

    @staticmethod
    def _normalize_spaces(text: str) -> str:
        return " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split()).strip()

    def _polish_title_surface(self, title: str) -> str:
        value = self._normalize_spaces(title)
        if not value:
            return ""

        replacements = (
            (r"\bopen[- ]source(?:d)?\b", "开源"),
            (r"\bzero[- ]trust\b", "零信任"),
            (r"\bruntime\b", "运行时"),
            (r"\bsandbox\b", "沙箱"),
            (r"\bAI\s+agents?\b", "AI Agent"),
            (r"\bagent runtime\b", "Agent 运行时"),
        )
        for pattern, target in replacements:
            value = re.sub(pattern, target, value, flags=re.IGNORECASE)

        value = value.replace("AI代理", "AI Agent")
        value = value.replace("AI 代理", "AI Agent")
        value = value.replace("AI智能体", "AI Agent")
        value = value.replace("AI 智能体", "AI Agent")
        value = value.replace("AI Agent的", "AI Agent 的")
        awkward_rewrite = self._rewrite_awkward_question_title(value)
        if awkward_rewrite:
            value = awkward_rewrite
        value = re.sub(r"(\d+)\s*[- ]?\s*layer", r"\1 层", value, flags=re.IGNORECASE)
        value = re.sub(r"(\d+)\s*层检查防\s*(rm\s*-\s*rf)", r"通过 \1 层检查拦截 \2 等危险命令", value, flags=re.IGNORECASE)
        value = re.sub(
            r"(\d+)\s*层\s*checks?\s+against\s*(rm\s*-\s*rf)",
            r"通过 \1 层检查拦截 \2 等危险命令",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(r"检查防\s*(rm\s*-\s*rf)", r"检查拦截 \1 等危险命令", value, flags=re.IGNORECASE)
        value = re.sub(r"防\s*(rm\s*-\s*rf)", r"拦截 \1 等危险命令", value, flags=re.IGNORECASE)
        value = re.sub(r"(^|[（(])开源(?=[A-Za-z])", r"\1", value)
        value = re.sub(r"^开源\s*(?=[A-Za-z])", "", value)
        value = re.sub(r"^([^：:]{2,40})\s*：\s*(AI Agent 的)", r"\1：面向 \2", value)
        value = re.sub(r"^([^：:]{2,40})\s*：\s*(零信任)", r"\1：\2", value)
        value = re.sub(r"^([^：:]{2,40})\s*：", r"\1：", value)

        tool_name = self._guess_tool_name(value)
        if tool_name and (("开源" in title) or bool(re.search(r"\bopen[- ]source(?:d)?\b", title, flags=re.IGNORECASE))):
            value = re.sub(rf"^{re.escape(tool_name)}(?=[：:])", f"{tool_name} 开源", value)
            if not re.match(rf"^{re.escape(tool_name)} 开源", value):
                value = re.sub(rf"^{re.escape(tool_name)}\b", f"{tool_name} 开源", value)

        value = value.replace("rm-rf", "rm -rf")
        value = re.sub(r"([a-z])([A-Z]{2,})(?=[\u4e00-\u9fff])", r"\1 \2", value)
        value = re.sub(r"([\u4e00-\u9fff])([A-Za-z]{2,})", r"\1 \2", value)
        value = re.sub(r"([A-Za-z]{2,})([\u4e00-\u9fff])", r"\1 \2", value)
        value = re.sub(r"\b(IPO)(预期|上市|升温)", r"\1 \2", value)
        value = value.replace("Open AI", "OpenAI")
        value = value.replace("Chat GPT", "ChatGPT")
        value = self._normalize_spaces(value)
        value = re.sub(r"([：:，,])\s+", r"\1", value)
        value = re.sub(r"\s+(rm -rf)", r" \1", value)
        value = value.replace("等危险命令 等危险命令", "等危险命令")
        value = value.strip("：:- ")
        return value

    def _rewrite_awkward_question_title(self, title: str) -> str:
        value = self._normalize_spaces(title).strip("？?")
        patterns = [
            re.compile(
                r"^(?P<head>[^：:]{2,40})[：:]\s*一个为(?P<audience>[^，,。！？?]{2,30})设计的(?P<object>[^，,。！？?]{2,60})[，,]\s*它是如何(?:构建|实现|设计|搭建)的$",
                flags=re.IGNORECASE,
            ),
            re.compile(
                r"^(?P<head>[^：:]{2,40})[：:]\s*(?P<object>[^，,。！？?]{4,70})[，,]\s*它是如何(?:构建|实现|设计|搭建)的$",
                flags=re.IGNORECASE,
            ),
        ]
        for pattern in patterns:
            match = pattern.match(value)
            if not match:
                continue
            head = self._normalize_title_head(match.group("head"))
            obj = self._normalize_spaces(match.group("object")).strip("，,。 ")
            obj = obj.replace("为AI Agent设计的", "面向 AI Agent 的")
            obj = obj.replace("为 AI Agent 设计的", "面向 AI Agent 的")
            if "audience" in match.groupdict():
                audience = self._normalize_spaces(match.group("audience")).strip("，,。 ")
                obj = f"面向 {audience} 的{obj}"
            obj = obj.replace("面向 AI Agent 的面向", "面向")
            obj = obj.replace("面向AI Agent", "面向 AI Agent")
            return f"{head}：{obj}，架构与实现拆解"
        return ""

    @staticmethod
    def _normalize_title_head(head: str) -> str:
        value = " ".join(str(head or "").split()).strip()
        value = re.sub(r"^(?:一个|这款|这套)\s*", "", value)
        return value.strip("：:- ")

    def _guess_tool_name(self, title: str) -> str:
        raw = self._normalize_spaces(title)
        if not raw:
            return ""
        head = re.split(r"[：:，,]", raw, maxsplit=1)[0].strip()
        head = re.sub(r"^(?:open[- ]source(?:d)?|announcing|introducing|launching|new)\s+", "", head, flags=re.IGNORECASE)
        head = re.sub(r"^(?:开源|发布|推出)\s*", "", head)
        head = self._normalize_spaces(head)
        if not any(char.isalpha() for char in head):
            return ""
        if re.fullmatch(r"[A-Za-z0-9.+_-]+(?:\s+[A-Za-z0-9.+_-]+){0,3}", head):
            return head[:40].strip()
        return ""

    @staticmethod
    def _normalize_command_phrase(command: str) -> str:
        value = " ".join(str(command or "").split())
        value = re.sub(r"rm\s*-\s*rf", "rm -rf", value, flags=re.IGNORECASE)
        return value.strip()

    @staticmethod
    def _mostly_ascii(text: str) -> bool:
        content = str(text or "").strip()
        if not content:
            return False
        ascii_count = sum(1 for char in content if ord(char) < 128)
        return ascii_count / max(len(content), 1) >= 0.75

    def _truncate_word_boundary(self, text: str, max_chars: int) -> str:
        value = str(text or "").strip()
        if len(value) <= max_chars:
            return value
        if self._mostly_ascii(value):
            chunk = value[: max_chars + 1]
            if " " in chunk:
                candidate = chunk.rsplit(" ", 1)[0].strip()
                if len(candidate) >= max(8, max_chars // 2):
                    return candidate
        return value[:max_chars].strip()

    @staticmethod
    def _truncate_utf8_bytes(text: str, max_bytes: int) -> str:
        value = str(text or "").strip()
        if len(value.encode("utf-8")) <= max_bytes:
            return value
        output: list[str] = []
        used_bytes = 0
        for char in value:
            char_bytes = len(char.encode("utf-8"))
            if used_bytes + char_bytes > max_bytes:
                break
            output.append(char)
            used_bytes += char_bytes
        return "".join(output).strip()
