"""Shared by both modules: search -> filter -> fetch -> store -> deduplicate."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Source
from app.research.adapter import ResearchAdapter, SearchHit
from app.research.cleaning import (classify_source, clean_text, content_hash, near_duplicate,
                                   normalize_url, should_skip_domain)
from app.research.safety import is_safe_url
from app.runlog import RunLog


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def discover(adapter: ResearchAdapter, queries: list[str], log: RunLog) -> tuple[list[SearchHit], int]:
    """Run every query. Returns (deduplicated hits, number of failed searches)."""
    seen: dict[str, SearchHit] = {}
    failed = 0
    for q in queries:
        try:
            hits = adapter.search(q)
        except Exception as e:                      # one bad query must not kill the run
            failed += 1
            log.error(f"search failed for '{q}': {e}")
            continue
        for h in hits:
            seen.setdefault(normalize_url(h.url), h)
    return list(seen.values()), failed


def select(hits: list[SearchHit], settings: Settings, log: RunLog) -> list[SearchHit]:
    chosen: list[SearchHit] = []
    for h in hits:
        if should_skip_domain(h.url):
            continue
        ok, reason = is_safe_url(h.url)
        if not ok:
            log.warn(f"skipped {h.url}: {reason}")
            continue
        chosen.append(h)
        if len(chosen) >= settings.max_sources_per_run:
            break
    return chosen


def fetch_and_store(db: Session, adapter: ResearchAdapter, hits: list[SearchHit],
                    settings: Settings, log: RunLog) -> tuple[list[Source], dict]:
    """Return usable, content-deduplicated Source rows (fetching only what is not cached)."""
    now = datetime.now(timezone.utc)
    fresh_after = now - timedelta(days=settings.fetch_cache_days)
    stats = {"selected": len(hits), "cached": 0, "fetched": 0, "failed": 0, "duplicates": 0}

    by_norm: dict[str, Source] = {}
    to_fetch: list[tuple[str, SearchHit]] = []
    for h in hits:
        n = normalize_url(h.url)
        src = db.query(Source).filter(Source.url_normalized == n).first()
        retrieved = _aware(src.retrieved_at) if src else None
        if src and src.fetch_status == "ok" and src.content and retrieved and retrieved > fresh_after:
            by_norm[n] = src
            stats["cached"] += 1
        else:
            if not src:
                src = Source(url=h.url, url_normalized=n, title=h.title or None,
                             source_type=classify_source(h.url))
                db.add(src)
            to_fetch.append((n, h))
    db.flush()

    if to_fetch:
        urls = [h.url for _, h in to_fetch]
        try:
            pages, failures = adapter.fetch(urls)
        except Exception as e:
            pages, failures = [], []
            log.error(f"fetch call failed: {e}")
            for u in urls:
                failures.append(type("F", (), {"url": u, "error": str(e)})())
        page_by_norm = {normalize_url(p.url): p for p in pages}
        fail_by_norm = {normalize_url(f.url): f for f in failures}
        for n, h in to_fetch:
            src = db.query(Source).filter(Source.url_normalized == n).first()
            page = page_by_norm.get(n)
            if page:
                text = clean_text(page.text)
                src.content = text
                src.content_hash = content_hash(text)
                src.fetch_status = "ok"
                src.fetch_error = None
                src.retrieved_at = now
                if page.title and not src.title:
                    src.title = page.title
                by_norm[n] = src
                stats["fetched"] += 1
            else:
                err = fail_by_norm[n].error if n in fail_by_norm else "no result returned"
                src.fetch_status = "failed"
                src.fetch_error = err
                src.retrieved_at = now
                stats["failed"] += 1
                log.error(f"fetch failed for {h.url}: {err}")
        db.commit()

    # ---- content-level deduplication (exact hash, then near-duplicate) ----
    unique: list[Source] = []
    for src in by_norm.values():
        dup = next((u for u in unique
                    if u.content_hash == src.content_hash or near_duplicate(u.content, src.content)), None)
        if dup:
            stats["duplicates"] += 1
            log.warn(f"duplicate content skipped: {src.url} ~ {dup.url}")
        else:
            unique.append(src)
    return unique, stats
