from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImageSearchHit:
    source_page: str
    title: str = ""
    snippet: str = ""
    domain: str = ""
    provider: str = ""
    image_url: str = ""
    thumbnail_url: str = ""


class ImageSearchProvider:
    def is_available(self) -> bool:
        raise NotImplementedError

    def search_images(self, query: str, *, limit: int = 5) -> list[ImageSearchHit]:
        raise NotImplementedError
