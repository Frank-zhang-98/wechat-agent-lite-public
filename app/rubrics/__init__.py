from __future__ import annotations

from app.rubrics.base_rubric import BaseRubric, RubricRegistry
from app.rubrics.deep_dive_rubric import DeepDiveRubric
from app.rubrics.github_rubric import GithubRubric
from app.rubrics.news_rubric import NewsRubric

__all__ = [
    "BaseRubric",
    "DeepDiveRubric",
    "GithubRubric",
    "NewsRubric",
    "RubricRegistry",
]

