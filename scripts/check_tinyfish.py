"""LIVE check of your TinyFish key + adapter. Usage: python -m scripts.check_tinyfish "assignment manager app" """
import sys

from app.research.adapter import TinyFishAdapter

query = sys.argv[1] if len(sys.argv) > 1 else "student assignment manager app"
adapter = TinyFishAdapter()
hits = adapter.search(query)
print(f"{len(hits)} search results for {query!r}")
for h in hits[:5]:
    print(f"  {h.position}. {h.title[:70]}  {h.url}\n     {h.snippet[:100]}")
if hits:
    pages, failures = adapter.fetch([h.url for h in hits[:2]])
    for p in pages:
        print(f"\nFETCHED {p.url}: {len(p.text)} chars\n{p.text[:300]!r}")
    for f in failures:
        print(f"\nFAILED {f.url}: {f.error}")
