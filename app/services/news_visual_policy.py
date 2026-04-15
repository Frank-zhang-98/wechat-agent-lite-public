from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


NEWS_PRODUCT_RELEASE_SOURCE_ORDER = (
    "primary_source",
    "object_official",
    "official_capture",
    "official_logo",
    "none",
)

_RELEASE_SIGNAL_PATTERNS = (
    r"\blaunch(?:ed|es)?\b",
    r"\brelease(?:d|s)?\b",
    r"\bopen(?:ed)?\b",
    r"\bavailable\b",
    r"\broll(?:ed)?\s*out\b",
    r"发布",
    r"上线",
    r"开放",
    r"推出",
    r"开源",
    r"可调用",
    r"正式提供",
)

_PRODUCT_SIGNAL_PATTERNS = (
    r"\bapi\b",
    r"\bsdk\b",
    r"\bdocs?\b",
    r"\bdocumentation\b",
    r"\bdeveloper\b",
    r"\bportal\b",
    r"\bconsole\b",
    r"\bplatform\b",
    r"\bmodel\b",
    r"\bservice\b",
    r"接口",
    r"文档",
    r"开发者",
    r"控制台",
    r"产品页",
    r"平台能力",
    r"模型",
    r"服务",
)

_POSITIVE_SIGNAL_PATTERNS = (
    r"\bofficial\b",
    r"\bdocs?\b",
    r"\bdeveloper\b",
    r"\bportal\b",
    r"\bconsole\b",
    r"\bproduct\b",
    r"官方",
    r"官网",
    r"文档",
    r"开发者",
    r"控制台",
    r"产品页",
)

_BLOCKER_PATTERNS = (
    r"\bfunding\b",
    r"\binvest(?:ed|ment|or)?\b",
    r"\bvaluation\b",
    r"\bipo\b",
    r"\bacqui(?:re|sition)\b",
    r"\bmerger\b",
    r"\bincident\b",
    r"\bresponse\b",
    r"\bcontrovers(?:y|ial)\b",
    r"\blayoff\b",
    r"融资",
    r"投资",
    r"估值",
    r"并购",
    r"收购",
    r"回应",
    r"事故",
    r"舆情",
    r"裁员",
    r"贷款",
)

_RELEASE_SIGNAL_TERMS = (
    "发布",
    "上线",
    "开放",
    "推出",
    "开源",
    "可调用",
    "正式提供",
    "接入",
)

_PRODUCT_SIGNAL_TERMS = (
    "api",
    "sdk",
    "docs",
    "documentation",
    "developer",
    "portal",
    "console",
    "platform",
    "model",
    "service",
    "接口",
    "文档",
    "开发者",
    "控制台",
    "产品页",
    "平台能力",
    "模型",
    "服务",
    "开发平台",
)

_POSITIVE_SIGNAL_TERMS = (
    "official",
    "docs",
    "developer",
    "portal",
    "console",
    "product",
    "官网",
    "官方",
    "文档",
    "开发者",
    "控制台",
    "产品页",
    "开发平台",
)

_BLOCKER_TERMS = (
    "funding",
    "invest",
    "valuation",
    "ipo",
    "acqui",
    "merger",
    "incident",
    "response",
    "controvers",
    "layoff",
    "融资",
    "投资",
    "估值",
    "并购",
    "收购",
    "回应",
    "事故",
    "舆情",
    "裁员",
    "贷款",
)

_OFFICIAL_HOST_ALIASES = {
    "developers.openai.com": "openai.com",
    "platform.openai.com": "openai.com",
    "docs.anthropic.com": "anthropic.com",
}


def classify_news_visual_variant(*, topic: dict[str, Any], fact_pack: dict[str, Any]) -> dict[str, Any]:
    pool = str(fact_pack.get("primary_pool", "") or fact_pack.get("pool", "") or "").strip()
    if pool != "news":
        return {
            "variant": "standard_news",
            "matched_features": [],
            "blocked_by": [],
            "reason": "non_news_pool",
        }

    fields = [
        str(topic.get("title", "") or "").strip(),
        str(topic.get("summary", "") or "").strip(),
        str(fact_pack.get("topic_title", "") or "").strip(),
    ]
    for item in list(fact_pack.get("section_blueprint") or [])[:4]:
        if not isinstance(item, dict):
            continue
        fields.append(str(item.get("heading", "") or "").strip())
        fields.append(str(item.get("summary", "") or "").strip())
    haystack = " ".join(part for part in fields if part)
    lowered = haystack.lower()

    matched_features: list[str] = []
    blocked_by: list[str] = []

    release_hit = _match_any(lowered, _RELEASE_SIGNAL_PATTERNS) or _contains_any(haystack, _RELEASE_SIGNAL_TERMS)
    product_hit = _match_any(lowered, _PRODUCT_SIGNAL_PATTERNS) or _contains_any(lowered, _PRODUCT_SIGNAL_TERMS)
    positive_hit = _match_all(lowered, _POSITIVE_SIGNAL_PATTERNS)
    positive_terms = _collect_terms(lowered, _POSITIVE_SIGNAL_TERMS)
    blocker_hit = _match_all(lowered, _BLOCKER_PATTERNS)
    blocker_terms = _collect_terms(lowered, _BLOCKER_TERMS)

    if release_hit:
        matched_features.append("release_signal")
    if product_hit:
        matched_features.append("product_signal")
    matched_features.extend(positive_hit)
    matched_features.extend(item for item in positive_terms if item not in matched_features)

    if blocker_hit:
        blocked_by.extend(blocker_hit)
    blocked_by.extend(item for item in blocker_terms if item not in blocked_by)

    if blocker_hit:
        return {
            "variant": "standard_news",
            "matched_features": matched_features,
            "blocked_by": blocked_by,
            "reason": "blocked_by_non_release_news_signals",
        }
    if release_hit and product_hit:
        return {
            "variant": "product_release_news",
            "matched_features": matched_features,
            "blocked_by": [],
            "reason": "release_and_product_signals_present",
        }
    return {
        "variant": "standard_news",
        "matched_features": matched_features,
        "blocked_by": [],
        "reason": "missing_release_or_product_signal",
    }


def detect_news_visual_variant(*, topic: dict[str, Any], fact_pack: dict[str, Any]) -> str:
    return str(classify_news_visual_variant(topic=topic, fact_pack=fact_pack).get("variant", "standard_news"))


def collect_official_hosts(*, web_enrich: dict[str, Any]) -> set[str]:
    hosts: set[str] = set()
    for entry in list((web_enrich or {}).get("official_sources") or []):
        if not isinstance(entry, dict):
            continue
        host = extract_host(str(entry.get("url", "") or "").strip())
        if host:
            hosts.add(host)
            alias = _OFFICIAL_HOST_ALIASES.get(host)
            if alias:
                hosts.add(alias)
    return hosts


def extract_host(url: str) -> str:
    raw = str(url or "").strip().lower()
    if not raw:
        return ""
    host = urlparse(raw).netloc.lower()
    if not host and "/" not in raw and "://" not in raw:
        host = raw
    if host.startswith("www."):
        host = host[4:]
    return host


def is_official_host(*, host: str, official_hosts: set[str]) -> bool:
    normalized = extract_host(str(host or "").strip())
    if not normalized or not official_hosts:
        return False
    candidate_hosts = {normalized}
    alias = _OFFICIAL_HOST_ALIASES.get(normalized)
    if alias:
        candidate_hosts.add(alias)
    for candidate in candidate_hosts:
        for official in official_hosts:
            if candidate == official or candidate.endswith(f".{official}") or official.endswith(f".{candidate}"):
                return True
    return False


def infer_source_role(*, origin_type: str, host: str, official_hosts: set[str]) -> str:
    normalized_origin = str(origin_type or "").strip().lower()
    if normalized_origin == "primary":
        return "primary_source"
    if normalized_origin == "official":
        return "object_official"
    if normalized_origin == "context":
        return "third_party_context"
    if normalized_origin == "search" and is_official_host(host=host, official_hosts=official_hosts):
        return "object_official"
    return "search_page"


def extract_release_subject(title: str) -> str:
    value = str(title or "").strip()
    patterns = (
        r"([A-Za-z][A-Za-z0-9.+_-]*(?:\s+\d+(?:\.\d+)*)?)\s*(?:API|SDK|Docs?|Model)",
        r"([\u4e00-\u9fffA-Za-z0-9.+_-]{2,24})\s*(?:API|SDK|接口|模型|服务)",
    )
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return str(match.group(1) or "").strip()
    return ""


def _match_any(haystack: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in patterns)


def _match_all(haystack: str, patterns: tuple[str, ...]) -> list[str]:
    matched: list[str] = []
    for pattern in patterns:
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            matched.append(pattern)
    return matched


def _contains_any(haystack: str, terms: tuple[str, ...]) -> bool:
    lowered = haystack.lower()
    for term in terms:
        value = str(term)
        if not value:
            continue
        if value.isascii():
            if value.lower() in lowered:
                return True
        elif value in haystack:
            return True
    return False


def _collect_terms(haystack: str, terms: tuple[str, ...]) -> list[str]:
    lowered = haystack.lower()
    matched: list[str] = []
    for term in terms:
        value = str(term)
        if not value:
            continue
        if value.isascii():
            if value.lower() in lowered:
                matched.append(term)
        elif value in haystack:
            matched.append(term)
    return matched
