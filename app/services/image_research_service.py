from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.services.image_search_providers.base import ImageSearchProvider
from app.services.image_search_providers.search_backed_provider import SearchBackedImageProvider
from app.services.article_variant_policy import detect_article_variant
from app.services.news_visual_policy import (
    classify_news_visual_variant,
    collect_official_hosts,
    extract_host,
    extract_release_subject,
    infer_source_role,
    is_official_host,
)
from app.services.search_providers.anspire_provider import AnspireSearchProvider
from app.services.search_providers.base import SearchProvider
from app.services.settings_service import SettingsService


class ImageResearchService:
    def __init__(self, settings: SettingsService, fetch: Any, image_search_provider: ImageSearchProvider | None = None) -> None:
        self.settings = settings
        self.fetch = fetch
        self.image_search_provider = image_search_provider

    def build_candidates(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        web_enrich: dict[str, Any],
        source_structure: dict[str, Any],
    ) -> list[dict[str, Any]]:
        article_title = str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip()
        article_hint = " ".join(
            str(item.get("summary", "") or "").strip()
            for item in list(fact_pack.get("section_blueprint") or [])[:3]
            if isinstance(item, dict)
        ).strip()
        variant = str(classify_news_visual_variant(topic=topic, fact_pack=fact_pack).get("variant", "standard_news"))
        article_variant = str(fact_pack.get("article_variant", "") or "").strip() or str(
            detect_article_variant(topic=topic, fact_pack=fact_pack) or "standard"
        )
        official_hosts = collect_official_hosts(web_enrich=web_enrich)
        candidates: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        def add(candidate: dict[str, Any]) -> None:
            normalized_url = str(candidate.get("url", "") or "").strip()
            if not normalized_url or normalized_url in seen_urls:
                return
            seen_urls.add(normalized_url)
            candidates.append(candidate)

        primary_url = str(topic.get("url", "") or "").strip()
        if primary_url:
            for candidate in self.fetch.extract_lightweight_image_candidates(
                primary_url,
                max_items=3,
                article_title=article_title,
                article_hint=article_hint,
            ):
                add(
                    self._normalize_candidate(
                        candidate=dict(candidate),
                        source_page=primary_url,
                        origin_type="primary",
                        query_source="topic_url",
                        official_hosts=official_hosts,
                        article_variant=article_variant,
                        )
                    )

        if article_variant == "project_explainer":
            for repo_page in self._project_visual_pages(fact_pack=fact_pack):
                for candidate in self.fetch.extract_lightweight_image_candidates(
                    repo_page,
                    max_items=2,
                    article_title=article_title,
                    article_hint=article_hint,
                ):
                    add(
                        self._normalize_candidate(
                            candidate=dict(candidate),
                            source_page=repo_page,
                            origin_type="official",
                            query_source="repo_visual_page",
                            official_hosts=official_hosts,
                            article_variant=article_variant,
                        )
                    )

        for source_type, entries in (
            ("official", list(web_enrich.get("official_sources") or [])),
            ("context", list(web_enrich.get("context_sources") or [])),
        ):
            for entry in entries[:4]:
                if not isinstance(entry, dict):
                    continue
                entry_url = str(entry.get("url", "") or "").strip()
                query_label = str(entry.get("query", "") or entry.get("title", "") or "").strip()
                for image in list(entry.get("images") or [])[:3]:
                    if not isinstance(image, dict):
                        continue
                    add(
                        self._normalize_candidate(
                            candidate=dict(image),
                            source_page=entry_url,
                            origin_type=source_type,
                            query_source=query_label or source_type,
                            official_hosts=official_hosts,
                            article_variant=article_variant,
                        )
                    )
                if entry_url:
                    for candidate in self.fetch.extract_lightweight_image_candidates(
                        entry_url,
                        max_items=2,
                        article_title=article_title,
                        article_hint=article_hint,
                    ):
                        add(
                            self._normalize_candidate(
                                candidate=dict(candidate),
                                source_page=entry_url,
                                origin_type=source_type,
                                query_source=query_label or source_type,
                                official_hosts=official_hosts,
                                article_variant=article_variant,
                            )
                        )

        provider = self._build_image_search_provider()
        if provider is not None and provider.is_available():
            for query in self._search_queries(
                topic=topic,
                fact_pack=fact_pack,
                source_structure=source_structure,
                variant=variant,
                article_variant=article_variant,
            ):
                for hit in provider.search_images(
                    query,
                    limit=self.settings.get_int("visual.image_research.max_results_per_query", 4),
                ):
                    for candidate in self.fetch.extract_lightweight_image_candidates(
                        hit.source_page,
                        max_items=2,
                        article_title=article_title,
                        article_hint=article_hint,
                    ):
                        merged_candidate = {
                            **dict(candidate),
                            "context": " ".join(
                                part
                                for part in (
                                    str(candidate.get("context", "") or "").strip(),
                                    str(hit.title or "").strip(),
                                    str(hit.snippet or "").strip(),
                                )
                                if part
                            ),
                        }
                        add(
                            self._normalize_candidate(
                                candidate=merged_candidate,
                                source_page=hit.source_page,
                                origin_type="search",
                                query_source=query,
                                official_hosts=official_hosts,
                                article_variant=article_variant,
                            )
                        )
                    if len(candidates) >= self.settings.get_int("visual.image_research.max_candidates", 18):
                        break
                if len(candidates) >= self.settings.get_int("visual.image_research.max_candidates", 18):
                    break

        candidates.sort(
            key=lambda item: (
                -int(item.get("provenance_score", 0) or 0),
                -int(item.get("score", 0) or 0),
                -int(item.get("relevance_hits", 0) or 0),
                item.get("url", ""),
            )
        )
        return candidates[: self.settings.get_int("visual.image_research.max_candidates", 18)]

    @staticmethod
    def _project_visual_pages(*, fact_pack: dict[str, Any]) -> list[str]:
        repo_url = str(fact_pack.get("github_repo_url", "") or "").strip()
        if not repo_url:
            return []
        candidates = [
            repo_url,
            f"{repo_url}#readme",
            f"{repo_url}/tree/main/docs",
            f"{repo_url}/tree/main/examples",
            f"{repo_url}/tree/main/demo",
            f"{repo_url}/tree/main/playground",
        ]
        deduped: list[str] = []
        seen: set[str] = set()
        for value in candidates:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped[:4]

    def _build_image_search_provider(self) -> ImageSearchProvider | None:
        if self.image_search_provider is not None:
            return self.image_search_provider
        provider_name = self.settings.get("visual.image_search.provider", "search_backed").strip().lower()
        if provider_name == "search_backed":
            return SearchBackedImageProvider(self._build_page_search_provider())
        return None

    def _build_page_search_provider(self) -> SearchProvider | None:
        provider_name = self.settings.get("search.provider", "anspire").strip().lower()
        if provider_name == "anspire":
            return AnspireSearchProvider(
                api_key=self.settings.get("search.anspire.api_key", ""),
                base_url=self.settings.get("search.anspire.base_url", ""),
                timeout_seconds=self.settings.get_int("search.request_timeout_seconds", 20),
            )
        return None

    def _search_queries(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        source_structure: dict[str, Any],
        variant: str,
        article_variant: str,
    ) -> list[str]:
        pool = str(fact_pack.get("primary_pool", "") or "").strip()
        title = str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip()
        repo_slug = str((source_structure.get("github_repo_context") or {}).get("repo_slug", "") or "").strip()
        queries: list[str] = []
        if title:
            queries.append(title)
        if article_variant == "project_explainer":
            project_subject = str(
                fact_pack.get("project_subject", "")
                or repo_slug
                or str(fact_pack.get("github_repo_slug", "") or "").strip()
                or title
            ).strip()
            if project_subject:
                queries.extend(
                    [
                        f"{project_subject} github readme",
                        f"{project_subject} docs",
                        f"{project_subject} architecture",
                        f"{project_subject} benchmark",
                    ]
                )
        if pool == "github":
            subject = repo_slug or title
            if subject:
                queries.extend([f"{subject} screenshot", f"{subject} github readme"])
        elif pool == "news":
            if variant == "product_release_news":
                subject = extract_release_subject(title) or title
                queries.extend(
                    [
                        f"{title} 官方 发布",
                        f"{subject} API 官方",
                        f"{subject} docs",
                        f"{subject} 发布页",
                        f"{subject} 产品页",
                    ]
                )
            else:
                queries.extend([f"{title} 官方 图片", f"{title} 现场 图"])
        else:
            queries.extend([f"{title} 官方 产品 图", f"{title} 架构 图"])
        seen: set[str] = set()
        deduped: list[str] = []
        for query in queries:
            normalized = re.sub(r"\s+", " ", str(query or "").strip())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped[: self.settings.get_int("visual.image_research.max_queries", 3)]

    @staticmethod
    def _normalize_candidate(
        *,
        candidate: dict[str, Any],
        source_page: str,
        origin_type: str,
        query_source: str,
        official_hosts: set[str],
        article_variant: str,
    ) -> dict[str, Any]:
        alt = str(candidate.get("alt", "") or "").strip()
        caption = str(candidate.get("caption", "") or "").strip()
        context = str(candidate.get("context", "") or "").strip()
        page_host = extract_host(str(source_page or "").strip())
        official_flag = is_official_host(host=page_host, official_hosts=official_hosts)
        image_kind = ImageResearchService._infer_image_kind(
            text=" ".join([alt, caption, context, str(candidate.get("url", "") or "")]),
            source=str(candidate.get("source", "") or ""),
        )
        source_role = (
            ImageResearchService._infer_project_source_role(
                source_page=source_page,
                origin_type=origin_type,
                image_kind=image_kind,
                fallback_role=infer_source_role(origin_type=origin_type, host=page_host, official_hosts=official_hosts),
            )
            if str(article_variant or "").strip() == "project_explainer"
            else infer_source_role(origin_type=origin_type, host=page_host, official_hosts=official_hosts)
        )
        return {
            "url": str(candidate.get("url", "") or "").strip(),
            "source_page": str(source_page or "").strip(),
            "origin_type": str(origin_type or "").strip(),
            "query_source": str(query_source or "").strip(),
            "source_role": source_role,
            "page_host": page_host,
            "is_official_host": official_flag,
            "image_kind": image_kind,
            "alt": alt[:160],
            "caption": caption[:220],
            "context_snippet": context[:260],
            "host": str(candidate.get("host", "") or "").strip(),
            "score": int(candidate.get("score", 0) or 0),
            "relevance_hits": int(candidate.get("relevance_hits", 0) or 0),
            "provenance_score": ImageResearchService._provenance_score(origin_type=origin_type, image_kind=image_kind),
            "relevance_features": {
                "source": str(candidate.get("source", "") or "").strip(),
                "score": int(candidate.get("score", 0) or 0),
                "relevance_hits": int(candidate.get("relevance_hits", 0) or 0),
            },
        }

    @staticmethod
    def _infer_image_kind(*, text: str, source: str) -> str:
        haystack = " ".join([str(text or "").lower(), str(source or "").lower()])
        if any(token in haystack for token in ("screenshot", "ui", "dashboard", "interface", "readme", "demo")):
            return "screenshot"
        if any(token in haystack for token in ("chart", "graph", "infographic", "diagram", "workflow", "architecture")):
            return "diagram"
        if any(token in haystack for token in ("logo", "brandmark", "favicon")):
            return "logo"
        if any(token in haystack for token in ("portrait", "headshot", "avatar", "speaker", "ceo", "founder")):
            return "portrait"
        if any(token in haystack for token in ("photo", "image", "hero", "press", "event")):
            return "photo"
        return "unknown"

    @staticmethod
    def _infer_project_source_role(
        *,
        source_page: str,
        origin_type: str,
        image_kind: str,
        fallback_role: str,
    ) -> str:
        normalized_page = str(source_page or "").strip().lower()
        host = urlparse(normalized_page).netloc.lower()
        path = urlparse(normalized_page).path.lower()
        is_repo_page = any(
            token in normalized_page
            for token in (
                "github.com/",
                "raw.githubusercontent.com/",
                "/readme",
                "/docs",
                "/doc/",
                "/demo",
                "/examples",
                "/playground",
            )
        ) or host.startswith("docs.") or any(token in path for token in ("/docs", "/demo", "/examples", "/playground"))
        if str(origin_type or "").strip().lower() == "primary" and image_kind in {"diagram", "screenshot"}:
            return "source_article_tech_visual"
        if is_repo_page:
            return "repo_readme_or_docs_visual"
        return str(fallback_role or "").strip() or "search_page"

    @staticmethod
    def _provenance_score(*, origin_type: str, image_kind: str) -> int:
        base = {"primary": 92, "official": 86, "context": 72, "search": 66}.get(str(origin_type or "").strip(), 60)
        if image_kind == "logo":
            base -= 18
        if image_kind == "portrait":
            base -= 10
        return max(0, min(base, 100))
