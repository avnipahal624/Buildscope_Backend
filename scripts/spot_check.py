import sys
import httpx

BASE = "http://localhost:8000/api"
pid = sys.argv[1]
c = httpx.Client(timeout=60)
needs = {n["id"]: n for n in c.get(f"{BASE}/projects/{pid}/needs").json()}
for e in c.get(f"{BASE}/projects/{pid}/evidence").json():
    n = needs.get(e["need_id"])
    if not n:
        continue
    print("NEED    :", n["need_text"])
    print("STATUS  :", n["evidence_status"])
    print("RELATION:", e["relation"])
    print("QUOTE   :", e["excerpt"])
    print("SOURCE  :", e["source_url"])
    print("-" * 70)