"""Re-run ONLY the stakeholder analysis for an existing project (saves quota).

Usage:  python -m scripts.run_stakeholders <project_id>
The server must be running, and the project must already have a completed research run.
"""
import json
import sys
import time

import httpx

if len(sys.argv) != 2:
    sys.exit("usage: python -m scripts.run_stakeholders <project_id>")
BASE = "http://localhost:8000/api"
pid = sys.argv[1]
c = httpx.Client(timeout=60)

job_id = c.post(f"{BASE}/projects/{pid}/stakeholders/analyze").json()["job_id"]
last = None
while True:
    job = c.get(f"{BASE}/jobs/{job_id}").json()
    stage = (job["status"], job["scope"].get("stage"))
    if stage != last:
        print(f"  stakeholders: {job['status']} (stage: {job['scope'].get('stage')})")
        last = stage
    if job["status"] not in ("pending", "running"):
        break
    time.sleep(4)

if job["error"]:
    print("ERROR:", job["error"])
for e in job["log"][:15]:
    print(f" - {e['level']}: {e['message'][:200]}")
for n in c.get(f"{BASE}/projects/{pid}/needs").json():
    print(f"* [{n['evidence_status']}] {n['need_text']}  "
          f"(supports={n['supporting_count']}, contradicts={n['contradicting_count']})")
report = c.get(f"{BASE}/projects/{pid}/report").json()
open("report.json", "w").write(json.dumps(report, indent=2, default=str))
print("full report saved to report.json")