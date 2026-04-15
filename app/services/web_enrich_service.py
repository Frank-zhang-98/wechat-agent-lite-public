from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from app.services.fetch_service import FetchService
from app.services.llm_gateway import LLMGateway
from app.services.search_providers.anspire_provider import AnspireSearchProvider
from app.services.search_providers.base import SearchHit, SearchProvider
from app.services.settings_service import SettingsService


class WebEnrichService:
    def __init__(self, settings: SettingsService, fetch: FetchService) -> None:
        self.settings = settings
        self.fetch = fetch

    def is_enabled(self) -> bool:
        return self.settings.get_bool("web_enrich.enabled", True)

    def build_search_plan(
        self,
        *,
        run_id: str,
        topic: dict[str, Any],
        source_pack: dict[str, Any],
        source_structure: dict[str, Any],
        evidence_score: float,
        llm: LLMGateway,
        primary_pool: str = "",
        subtype: str = "",
    ) -> dict[str, Any]:
        threshold = float(self.settings.get_float("web_enrich.min_evidence_score_to_skip", 60.0))
        if not self.is_enabled():
            return {
                "enabled": False,
                "should_search": False,
                "reason": "web_enrich_disabled",
                "queries": [],
                "official_domains": [],
            }

        inferred_pool = str(primary_pool or topic.get("primary_pool") or topic.get("pool") or "").strip().lower()
        if inferred_pool == "github" or "github.com/" in str(topic.get("url", "") or "").lower():
            github_repo_archetype = self._infer_github_repo_archetype(topic=topic, source_structure=source_structure)
            github_plan = self._build_github_repo_plan(
                topic=topic,
                source_pack=source_pack,
                source_structure=source_structure,
                archetype=github_repo_archetype,
            )
            if github_plan.get("should_search"):
                github_plan["enabled"] = True
                return github_plan

        if inferred_pool == "news" and self._should_backfill_news_images(source_pack=source_pack):
            return {
                "enabled": True,
                **self._build_news_image_backfill_plan(topic=topic, source_pack=source_pack),
            }

        if evidence_score >= threshold:
            return {
                "enabled": True,
                "should_search": False,
                "reason": f"evidence_score_{evidence_score}_above_threshold_{threshold}",
                "queries": [],
                "official_domains": [],
            }

        prompt = (
            "You are a search planner for factual article enrichment.\n"
            "Return strict JSON only.\n"
            "Decide whether web search is needed, then propose at most 3 focused queries.\n"
            "Search goals: verify official facts, find official docs, and collect context only when needed.\n"
            "Do not suggest speculative internal architecture searches unless the source already mentions them.\n"
            "Output schema:\n"
            "{\n"
            '  "should_search": true,\n'
            '  "reason": "...",\n'
            '  "official_domains": ["example.com"],\n'
            '  "queries": [\n'
            '    {"q": "...", "intent": "...", "source_type": "official|context", "must_include": [], "must_exclude": []}\n'
            "  ]\n"
            "}\n\n"
            f"Topic:\n{json.dumps(topic, ensure_ascii=False)}\n"
            f"Primary Pool: {primary_pool or topic.get('primary_pool') or topic.get('pool') or ''}\n"
            f"Subtype: {subtype}\n"
            f"Evidence Score: {evidence_score}\n"
            f"Source Pack:\n{json.dumps(source_pack, ensure_ascii=False)[:2500]}\n"
            f"Source Structure:\n{json.dumps(source_structure, ensure_ascii=False)[:2500]}"
        )
        result = llm.call(run_id, "WEB_SEARCH_PLAN", "decision", prompt, temperature=0.1)
        parsed = self._parse_plan(result.text)
        if parsed:
            parsed["enabled"] = True
            return parsed
        fallback_query = str(topic.get("title", "") or "").strip()
        return {
            "enabled": True,
            "should_search": bool(fallback_query),
            "reason": "fallback_topic_title_query",
            "official_domains": [],
            "queries": (
                [{"q": fallback_query, "intent": "verify public facts", "source_type": "context", "must_include": [], "must_exclude": []}]
                if fallback_query
                else []
            ),
        }

    def fetch_search_results(self, *, plan: dict[str, Any]) -> dict[str, Any]:
        if not self.is_enabled():
            return {"status": "skipped", "reason": "web_enrich_disabled", "official_sources": [], "context_sources": [], "queries": []}
        if not plan.get("should_search"):
            return {"status": "skipped", "reason": plan.get("reason", "planner_skip"), "official_sources": [], "context_sources": [], "queries": []}
        provider = self._build_provider()
        if provider is None or not provider.is_available():
            return {"status": "skipped", "reason": "search_provider_unavailable", "official_sources": [], "context_sources": [], "queries": []}

        max_queries = max(1, self.settings.get_int("web_enrich.max_queries", 3))
        max_results = max(1, self.settings.get_int("web_enrich.max_results_per_query", 5))
        max_fetch_per_query = max(1, self.settings.get_int("web_enrich.max_fetch_per_query", 2))
        official_domains = {str(item).strip().lower() for item in (plan.get("official_domains") or []) if str(item).strip()}

        official_sources: list[dict[str, Any]] = []
        context_sources: list[dict[str, Any]] = []
        audit_queries: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for query_item in list(plan.get("queries") or [])[:max_queries]:
            query = str(query_item.get("q", "") or "").strip()
            if not query:
                continue
            source_type = str(query_item.get("source_type", "context") or "context").strip().lower()
            must_include = [str(item).strip().lower() for item in (query_item.get("must_include") or []) if str(item).strip()]
            must_exclude = [str(item).strip().lower() for item in (query_item.get("must_exclude") or []) if str(item).strip()]
            hits = provider.search(query, limit=max_results)
            accepted: list[SearchHit] = []
            for hit in hits:
                if not hit.url or hit.url in seen_urls:
                    continue
                haystack = " ".join((hit.title or "", hit.snippet or "", hit.url or "", hit.domain or "")).lower()
                if must_include and not all(token in haystack for token in must_include):
                    continue
                if must_exclude and any(token in haystack for token in must_exclude):
                    continue
                if source_type == "official" and official_domains:
                    if not any(hit.domain.endswith(domain) for domain in official_domains):
                        continue
                seen_urls.add(hit.url)
                accepted.append(hit)
                if len(accepted) >= max_fetch_per_query:
                    break

            normalized_hits: list[dict[str, Any]] = []
            for hit in accepted:
                extract = self.fetch.extract_article_content(hit.url, max_chars=2500)
                entry = {
                    "title": hit.title,
                    "url": hit.url,
                    "snippet": hit.snippet,
                    "domain": hit.domain,
                    "source_type": source_type,
                    "status": extract.get("status", "failed"),
                    "reason": extract.get("reason", ""),
                    "content_text": extract.get("content_text", ""),
                    "images": [dict(item) for item in (extract.get("images") or []) if isinstance(item, dict)],
                }
                normalized_hits.append(entry)
                if source_type == "official":
                    official_sources.append(entry)
                else:
                    context_sources.append(entry)

            audit_queries.append(
                {
                    "q": query,
                    "intent": str(query_item.get("intent", "") or ""),
                    "source_type": source_type,
                    "accepted": len(normalized_hits),
                }
            )

        return {
            "status": "ok" if (official_sources or context_sources) else "empty",
            "reason": "",
            "official_sources": official_sources,
            "context_sources": context_sources,
            "queries": audit_queries,
        }

    @classmethod
    def _build_github_repo_plan(
        cls,
        *,
        topic: dict[str, Any],
        source_pack: dict[str, Any],
        source_structure: dict[str, Any],
        archetype: str,
    ) -> dict[str, Any]:
        repo_url = str(topic.get("url", "") or "").strip()
        repo_slug = cls._github_repo_slug(repo_url)
        repo_name = repo_slug.split("/")[-1] if repo_slug else ""
        if not repo_slug or not repo_name:
            return {
                "should_search": False,
                "reason": "github_repo_plan_missing_repo_slug",
                "official_domains": [],
                "queries": [],
            }
        official_domains = ["github.com"] + cls._extract_domain_hints(topic=topic, source_pack=source_pack, source_structure=source_structure)
        return {
            "should_search": True,
            "reason": f"github_repo_background_required:{archetype}",
            "github_repo_archetype": archetype,
            "official_domains": official_domains[:6],
            "queries": cls._build_github_repo_queries(repo_name=repo_name, archetype=archetype),
        }

    def _build_provider(self) -> SearchProvider | None:
        provider_name = self.settings.get("search.provider", "anspire").strip().lower()
        if provider_name == "anspire":
            return AnspireSearchProvider(
                api_key=self.settings.get("search.anspire.api_key", ""),
                base_url=self.settings.get("search.anspire.base_url", ""),
                timeout_seconds=self.settings.get_int("search.request_timeout_seconds", 20),
            )
        return None

    @staticmethod
    def _parse_plan(text: str) -> dict[str, Any] | None:
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return None
            data = json.loads(text[start : end + 1])
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        queries: list[dict[str, Any]] = []
        for item in data.get("queries", []) or []:
            if not isinstance(item, dict):
                continue
            q = str(item.get("q", "") or "").strip()
            if not q:
                continue
            queries.append(
                {
                    "q": q,
                    "intent": str(item.get("intent", "") or "").strip(),
                    "source_type": str(item.get("source_type", "context") or "context").strip().lower(),
                    "must_include": [str(x).strip() for x in (item.get("must_include") or []) if str(x).strip()],
                    "must_exclude": [str(x).strip() for x in (item.get("must_exclude") or []) if str(x).strip()],
                }
            )
        return {
            "should_search": bool(data.get("should_search", False)),
            "reason": str(data.get("reason", "") or ""),
            "official_domains": [
                urlparse(str(item).strip()).netloc.lower().split("@")[-1] if "://" in str(item) else str(item).strip().lower()
                for item in (data.get("official_domains") or [])
                if str(item).strip()
            ],
            "queries": queries[:3],
        }

    @staticmethod
    def _should_backfill_news_images(*, source_pack: dict[str, Any]) -> bool:
        primary = dict(source_pack.get("primary") or {})
        primary_images = [item for item in (primary.get("images") or []) if isinstance(item, dict) and str(item.get("url", "") or "").strip()]
        return len(primary_images) < 2

    @classmethod
    def _build_news_image_backfill_plan(cls, *, topic: dict[str, Any], source_pack: dict[str, Any]) -> dict[str, Any]:
        title = str(topic.get("title", "") or "").strip()
        if not title:
            return {
                "should_search": False,
                "reason": "news_image_backfill_missing_title",
                "official_domains": [],
                "queries": [],
            }
        official_domains = cls._extract_domain_hints(topic=topic, source_pack=source_pack, source_structure={})[:3]
        queries = [
            {
                "q": f"\"{title}\"",
                "intent": "Find source-backed article pages with reusable news images.",
                "source_type": "official" if official_domains else "context",
                "must_include": [token for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{2,}", title)[:2]],
                "must_exclude": ["github", "docs"] if "github" not in str(topic.get("url", "") or "").lower() else [],
            },
            {
                "q": f"\"{title}\" image photo",
                "intent": "Find additional article pages that carry relevant news photos.",
                "source_type": "context",
                "must_include": [],
                "must_exclude": ["stock photo", "shutterstock", "getty images"],
            },
        ]
        return {
            "should_search": True,
            "reason": "news_image_backfill_low_primary_images",
            "official_domains": official_domains,
            "queries": queries[:3],
        }

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

    @staticmethod
    def _infer_github_repo_archetype(*, topic: dict[str, Any], source_structure: dict[str, Any]) -> str:
        github_repo_context = dict(source_structure.get("github_repo_context") or {})
        if bool(github_repo_context.get("is_collection_repo")):
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
        repo_haystack = " ".join(repo_level_parts).lower()
        haystack = " ".join(text_parts).lower()
        if re.search(
            r"\b(cli|command line|sdk|framework|runtime|toolkit|starter|template|boilerplate|scaffold|library|plugin|extension)\b",
            haystack,
        ):
            return "tooling_repo"
        if re.search(r"\b(awesome|collection|curated|examples?|showcase|playground)\b", repo_haystack):
            return "collection_repo"
        return "single_repo"

    @staticmethod
    def _build_github_repo_queries(*, repo_name: str, archetype: str) -> list[dict[str, Any]]:
        if archetype == "collection_repo":
            return [
                {
                    "q": f'"{repo_name}" GitHub README examples categories representative project',
                    "intent": "Confirm how the repository organizes examples and categories.",
                    "source_type": "official",
                    "must_include": [repo_name],
                    "must_exclude": [],
                },
                {
                    "q": f'"{repo_name}" representative example deployment walkthrough',
                    "intent": "Find a representative example and its deployment or usage path.",
                    "source_type": "context",
                    "must_include": [repo_name],
                    "must_exclude": [],
                },
                {
                    "q": f'"{repo_name}" ai app examples ecosystem comparison',
                    "intent": "Gather ecosystem background for why this collection matters.",
                    "source_type": "context",
                    "must_include": [repo_name],
                    "must_exclude": [],
                },
            ]
        if archetype == "tooling_repo":
            return [
                {
                    "q": f'"{repo_name}" GitHub README cli usage commands install self host',
                    "intent": "Confirm official install, CLI usage, and self-host guidance.",
                    "source_type": "official",
                    "must_include": [repo_name],
                    "must_exclude": [],
                },
                {
                    "q": f'"{repo_name}" docs configuration workflow template starter',
                    "intent": "Collect docs and workflow details for practical onboarding.",
                    "source_type": "context",
                    "must_include": [repo_name],
                    "must_exclude": [],
                },
                {
                    "q": f'"{repo_name}" alternatives comparison cli tool framework',
                    "intent": "Find comparable tools or frameworks for positioning.",
                    "source_type": "context",
                    "must_include": [repo_name],
                    "must_exclude": [],
                },
            ]
        return [
            {
                "q": f'"{repo_name}" GitHub README architecture deployment docs',
                "intent": "Confirm official architecture, deployment, and documentation entry points.",
                "source_type": "official",
                "must_include": [repo_name],
                "must_exclude": [],
            },
            {
                "q": f'"{repo_name}" use cases deployment self host docs',
                "intent": "Gather usage scenarios and deployment background.",
                "source_type": "context",
                "must_include": [repo_name],
                "must_exclude": [],
            },
            {
                "q": f'"{repo_name}" alternatives comparison ai agents',
                "intent": "Find comparison context against similar systems.",
                "source_type": "context",
                "must_include": [repo_name],
                "must_exclude": [],
            },
        ]

    @staticmethod
    def _extract_domain_hints(
        *,
        topic: dict[str, Any],
        source_pack: dict[str, Any],
        source_structure: dict[str, Any],
    ) -> list[str]:
        texts = [
            str(topic.get("title", "") or ""),
            str(topic.get("summary", "") or ""),
            str((source_pack.get("primary") or {}).get("content_text", "") or "")[:2500],
            str(source_structure.get("lead", "") or ""),
        ]
        texts.extend(str(section.get("heading", "") or "") for section in (source_structure.get("sections") or [])[:8] if isinstance(section, dict))
        texts.extend(str(section.get("summary", "") or "") for section in (source_structure.get("sections") or [])[:8] if isinstance(section, dict))
        seen: set[str] = set()
        output: list[str] = []
        for text in texts:
            for match in re.findall(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", str(text or "").lower()):
                cleaned = match.strip(".")
                if not cleaned or cleaned in seen:
                    continue
                seen.add(cleaned)
                output.append(cleaned)
                if len(output) >= 5:
                    return output
        return output
