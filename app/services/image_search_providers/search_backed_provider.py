from __future__ import annotations

from app.services.image_search_providers.base import ImageSearchHit, ImageSearchProvider
from app.services.search_providers.base import SearchProvider


class SearchBackedImageProvider(ImageSearchProvider):
    def __init__(self, page_search_provider: SearchProvider | None) -> None:
        self.page_search_provider = page_search_provider

    def is_available(self) -> bool:
        return self.page_search_provider is not None and self.page_search_provider.is_available()

    def search_images(self, query: str, *, limit: int = 5) -> list[ImageSearchHit]:
        if not self.is_available():
            return []
        hits = self.page_search_provider.search(query, limit=limit)
        return [
            ImageSearchHit(
                source_page=str(hit.url or "").strip(),
                title=str(hit.title or "").strip(),
                snippet=str(hit.snippet or "").strip(),
                domain=str(hit.domain or "").strip(),
                provider="search_backed",
            )
            for hit in hits
            if str(hit.url or "").strip()
        ]
