from __future__ import annotations

import re
from typing import Any


_PROJECT_SIGNAL_PATTERNS = (
    r"github\.com/",
    r"\brepo(?:sitory)?\b",
    r"\bframework\b",
    r"\blibrary\b",
    r"\bsystem\b",
    r"\bengine\b",
    r"\bplatform\b",
    r"\bworkflow\b",
    r"\bpipeline\b",
    r"\bcontext layer\b",
    r"\bcontext engine\b",
    r"仓库",
    r"项目",
    r"系统",
    r"框架",
    r"引擎",
    r"上下文层",
)

_IMPLEMENTATION_SIGNAL_PATTERNS = (
    r"\bcomponent\b",
    r"\bmodule\b",
    r"\barchitecture\b",
    r"\bworkflow\b",
    r"\bpipeline\b",
    r"\brerank\b",
    r"\bcache\b",
    r"\bmemory\b",
    r"\bretrieval\b",
    r"\bgraph\b",
    r"\bagent\b",
    r"\bcode\b",
    r"\bimplementation\b",
    r"\bbuild\b",
    r"组件",
    r"模块",
    r"架构",
    r"流程",
    r"链路",
    r"实现",
    r"代码",
    r"缓存",
    r"检索",
    r"记忆",
    r"重排",
)

_EVALUATION_SIGNAL_PATTERNS = (
    r"\bbenchmark\b",
    r"\bevaluation\b",
    r"\bcompare\b",
    r"\bcomparison\b",
    r"\btrade[- ]?off\b",
    r"\blatency\b",
    r"\bperformance\b",
    r"\baccuracy\b",
    r"\bfailure\b",
    r"\bboundary\b",
    r"\blimitation\b",
    r"\bablation\b",
    r"评测",
    r"对比",
    r"基准",
    r"延迟",
    r"性能",
    r"准确率",
    r"边界",
    r"限制",
    r"失败",
    r"取舍",
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
    r"融资",
    r"投资",
    r"估值",
    r"并购",
    r"收购",
    r"事故",
    r"回应",
    r"舆情",
)

_GITHUB_REPO_URL_RE = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:[/?#][^\s)]*)?",
    flags=re.IGNORECASE,
)


def classify_article_variant(*, topic: dict[str, Any], fact_pack: dict[str, Any]) -> dict[str, Any]:
    pool = str(fact_pack.get("primary_pool", "") or fact_pack.get("pool", "") or "").strip()
    if pool != "deep_dive":
        return {
            "article_variant": "standard",
            "matched_features": [],
            "blocked_by": [],
            "reason": "non_deep_dive_pool",
        }

    fields = [
        str(topic.get("title", "") or "").strip(),
        str(topic.get("summary", "") or "").strip(),
        str(fact_pack.get("topic_title", "") or "").strip(),
        str(fact_pack.get("topic_summary", "") or "").strip(),
        str(fact_pack.get("source_lead", "") or "").strip(),
        str(fact_pack.get("primary_excerpt", "") or "").strip(),
        str(fact_pack.get("github_repo_url", "") or "").strip(),
    ]
    for item in list(fact_pack.get("section_blueprint") or [])[:8]:
        if not isinstance(item, dict):
            continue
        fields.append(str(item.get("heading", "") or "").strip())
        fields.append(str(item.get("summary", "") or "").strip())
        fields.append(str(item.get("source_heading", "") or "").strip())
    for item in list(fact_pack.get("implementation_steps") or [])[:6]:
        if not isinstance(item, dict):
            continue
        fields.append(str(item.get("title", "") or "").strip())
        fields.append(str(item.get("summary", "") or "").strip())
    for item in list(fact_pack.get("architecture_points") or [])[:6]:
        if not isinstance(item, dict):
            continue
        fields.append(str(item.get("component", "") or "").strip())
        fields.append(str(item.get("responsibility", "") or "").strip())
    for item in list(fact_pack.get("code_artifacts") or [])[:6]:
        if not isinstance(item, dict):
            continue
        fields.append(str(item.get("section", "") or "").strip())
        fields.append(str(item.get("summary", "") or "").strip())
    haystack = " ".join(part for part in fields if part)
    lowered = haystack.lower()

    matched_features: list[str] = []
    blocked_by: list[str] = []

    project_hit = _matches(lowered, _PROJECT_SIGNAL_PATTERNS)
    implementation_hit = _matches(lowered, _IMPLEMENTATION_SIGNAL_PATTERNS) or any(
        (
            len(list(fact_pack.get("implementation_steps") or [])) >= 2,
            len(list(fact_pack.get("architecture_points") or [])) >= 2,
            len(list(fact_pack.get("code_artifacts") or [])) >= 1,
            len(list(fact_pack.get("github_source_code_blocks") or [])) >= 1,
        )
    )
    evaluation_hit = _matches(lowered, _EVALUATION_SIGNAL_PATTERNS) or bool(list(fact_pack.get("numbers") or []))
    blocker_hits = _collect_matches(lowered, _BLOCKER_PATTERNS)

    if project_hit:
        matched_features.append("project_signal")
    if implementation_hit:
        matched_features.append("implementation_signal")
    if evaluation_hit:
        matched_features.append("evaluation_signal")

    if blocker_hits:
        blocked_by.extend(blocker_hits)
        return {
            "article_variant": "standard",
            "matched_features": matched_features,
            "blocked_by": blocked_by,
            "reason": "blocked_by_news_like_signals",
        }

    if project_hit and implementation_hit and (evaluation_hit or len(list(fact_pack.get("section_blueprint") or [])) >= 4):
        return {
            "article_variant": "project_explainer",
            "matched_features": matched_features,
            "blocked_by": [],
            "reason": "project_and_implementation_signals_present",
        }

    return {
        "article_variant": "standard",
        "matched_features": matched_features,
        "blocked_by": [],
        "reason": "missing_project_or_implementation_signal",
    }


def detect_article_variant(*, topic: dict[str, Any], fact_pack: dict[str, Any]) -> str:
    return str(classify_article_variant(topic=topic, fact_pack=fact_pack).get("article_variant", "standard"))


def extract_repo_url(*, topic: dict[str, Any], fact_pack: dict[str, Any]) -> str:
    explicit = str(fact_pack.get("github_repo_url", "") or "").strip()
    if _looks_like_repo_url(explicit):
        return _normalize_repo_url(explicit)

    text_parts = [
        str(topic.get("url", "") or "").strip(),
        str(topic.get("title", "") or "").strip(),
        str(topic.get("summary", "") or "").strip(),
        str(fact_pack.get("topic_url", "") or "").strip(),
        str(fact_pack.get("topic_title", "") or "").strip(),
        str(fact_pack.get("topic_summary", "") or "").strip(),
        str(fact_pack.get("source_lead", "") or "").strip(),
        str(fact_pack.get("primary_excerpt", "") or "").strip(),
    ]
    for key in (
        "grounded_hard_facts",
        "grounded_official_facts",
        "grounded_context_facts",
        "key_points",
        "repo_assets",
    ):
        text_parts.extend(str(item or "").strip() for item in (fact_pack.get(key) or [])[:8])
    for item in list(fact_pack.get("section_blueprint") or [])[:8]:
        if not isinstance(item, dict):
            continue
        text_parts.append(str(item.get("heading", "") or "").strip())
        text_parts.append(str(item.get("summary", "") or "").strip())

    match = _GITHUB_REPO_URL_RE.search(" ".join(part for part in text_parts if part))
    if not match:
        return ""
    owner, repo = match.group(1), match.group(2)
    return f"https://github.com/{owner}/{repo}"


def extract_project_subject(*, topic: dict[str, Any], fact_pack: dict[str, Any]) -> str:
    repo_url = extract_repo_url(topic=topic, fact_pack=fact_pack)
    if _looks_like_repo_url(repo_url):
        parts = [part for part in _normalize_repo_url(repo_url).split("/") if part]
        if len(parts) >= 2:
            return parts[-1]
    candidate_text = " ".join(
        [
            str(topic.get("title", "") or "").strip(),
            str(topic.get("summary", "") or "").strip(),
            str(fact_pack.get("source_lead", "") or "").strip(),
            str(fact_pack.get("primary_excerpt", "") or "").strip()[:400],
        ]
    )
    for pattern in (
        r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})\b",
        r"\b([A-Za-z][A-Za-z0-9._+-]{3,})\b",
    ):
        for match in re.finditer(pattern, candidate_text):
            value = str(match.group(1) or "").strip()
            lowered = value.lower()
            if lowered in {"rag", "llm", "api", "github", "readme", "docs"}:
                continue
            return value
    return ""


def _looks_like_repo_url(url: str) -> bool:
    return bool(_GITHUB_REPO_URL_RE.search(str(url or "").strip()))


def _normalize_repo_url(url: str) -> str:
    match = _GITHUB_REPO_URL_RE.search(str(url or "").strip())
    if not match:
        return ""
    return f"https://github.com/{match.group(1)}/{match.group(2)}"


def _matches(haystack: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in patterns)


def _collect_matches(haystack: str, patterns: tuple[str, ...]) -> list[str]:
    matched: list[str] = []
    for pattern in patterns:
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            matched.append(pattern)
    return matched
