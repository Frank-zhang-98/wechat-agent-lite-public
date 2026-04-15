from __future__ import annotations

from app.policies.base_policy import BasePolicy, PolicyRegistry
from app.policies.deep_dive_policy import DeepDivePolicy
from app.policies.github_policy import GithubPolicy
from app.policies.news_policy import NewsPolicy

__all__ = [
    "BasePolicy",
    "DeepDivePolicy",
    "GithubPolicy",
    "NewsPolicy",
    "PolicyRegistry",
]

