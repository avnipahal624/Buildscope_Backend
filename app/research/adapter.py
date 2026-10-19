"""Research adapter: the ONLY place that knows about TinyFish.

If you switch provider later, implement the same two methods (search, fetch).

TinyFish contract (from https://docs.tinyfish.ai, verify before relying on it):
  Search: GET  https://api.search.tinyfish.ai?query=...   header X-API-Key
          -> {"query":..., "results":[{"position","site_name","title","url","snippet"}], ...}
  Fetch:  POST https://api.fetch.tinyfish.ai  {"urls":[<=10], "format":"markdown"}
          -> {"results":[{"url","text",...}], "errors":[{"url","error"}]}
"""
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings, get_settings
from app.research.cleaning import normalize_url


class AdapterError(RuntimeError):
    pass


@dataclass
class SearchHit:
    url: str
    title: str = ""
    snippet: str = ""
    position: int = 0


@dataclass
class FetchedPage:
    url: str
    text: str
    title: str = ""


@dataclass
class FetchFailure:
    url: str
    error: str


class ResearchAdapter(Protocol):
    def search(self, query: str) -> list[SearchHit]: ...
    def fetch(self, urls: list[str]) -> tuple[list[FetchedPage], list[FetchFailure]]: ...


class TinyFishAdapter:
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.s = settings or get_settings()
        self.http = client or httpx.Client(timeout=170)
        self._sleep = time.sleep

    def _request(self, method: str, url: str, **kwargs) -> dict:
        if not self.s.tinyfish_api_key:
            raise AdapterError("TINYFISH_API_KEY is not configured")
        headers = {"X-API-Key": self.s.tinyfish_api_key}
        last = "unknown error"
        for attempt in range(3):
            try:
                r = self.http.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as e:
                last = f"network error: {e}"
                self._sleep(2 ** attempt)
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                self._sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise AdapterError(f"HTTP {r.status_code}: {r.text[:300]}")
            return r.json()
        raise AdapterError(last)

    def search(self, query: str) -> list[SearchHit]:
        data = self._request("GET", self.s.tinyfish_search_url, params={"query": query})
        hits = []
        for i, item in enumerate(data.get("results", []), start=1):
            url = item.get("url")
            if not url:
                continue
            hits.append(SearchHit(
                url=url,
                title=item.get("title") or "",
                snippet=item.get("snippet") or item.get("description") or "",
                position=item.get("position") or i,
            ))
        return hits

    def fetch(self, urls: list[str]) -> tuple[list[FetchedPage], list[FetchFailure]]:
        pages: list[FetchedPage] = []
        failures: list[FetchFailure] = []
        for i in range(0, len(urls), 10):          # API accepts at most 10 URLs per call
            batch = urls[i:i + 10]
            try:
                data = self._request("POST", self.s.tinyfish_fetch_url,
                                     json={"urls": batch, "format": "markdown"})
            except AdapterError as e:
                failures.extend(FetchFailure(u, str(e)) for u in batch)
                continue
            requested = {normalize_url(u): u for u in batch}
            batch_pages: list[FetchedPage] = []
            returned: set[str] = set()
            for item in data.get("results", []):
                text = item.get("text") or item.get("content") or ""
                url = item.get("url") or ""
                if text.strip():
                    batch_pages.append(FetchedPage(url=url, text=text, title=item.get("title") or ""))
                else:
                    failures.append(FetchFailure(url, "empty content"))
                    returned.add(normalize_url(url))
            for item in data.get("errors", []):
                url = item.get("url") or ""
                returned.add(normalize_url(url))
                failures.append(FetchFailure(url, str(item.get("error") or item.get("message") or "fetch error")))
            # Redirects: a page may come back under its final URL. If exactly as many
            # unmatched pages as unmatched requests remain, pair them in order.
            unmatched_pages = [p for p in batch_pages if normalize_url(p.url) not in requested]
            for p in batch_pages:
                if normalize_url(p.url) in requested:
                    returned.add(normalize_url(p.url))
            unmatched_requests = [u for n, u in requested.items() if n not in returned]
            if unmatched_pages and len(unmatched_pages) == len(unmatched_requests):
                for page, original in zip(unmatched_pages, unmatched_requests):
                    page.url = original
                    returned.add(normalize_url(original))
            pages.extend(batch_pages)
            for n, u in requested.items():       # silently-missing URLs are failures too
                if n not in returned:
                    failures.append(FetchFailure(u, "no result returned"))
        return pages, failures
