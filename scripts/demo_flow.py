"""Drives a running server end-to-end. Usage: python -m scripts.demo_flow  (server on :8000)"""
import json
import time

import httpx

BASE = "http://localhost:8000/api"
c = httpx.Client(timeout=60)


def wait(job_id):
    while True:
        job = c.get(f"{BASE}/jobs/{job_id}").json()
        print(f"  {job['kind']}: {job['status']} (stage: {job['scope'].get('stage')})")
        if job["status"] not in ("pending", "running"):
            return job
        time.sleep(4)


project = c.post(f"{BASE}/projects", json={
    "name": "AssignMate",
    "description": "An AI application that helps students manage assignments.",
    "problem_statement": "Students struggle to prioritise assignments across several subjects.",
    "target_users": ["students"],
    "keywords": ["assignment manager", "student planner"],
    "planned_features": ["due date reminders", "workload planning"],
}).json()
pid = project["id"]
print("project:", pid)

print("research...")
job = wait(c.post(f"{BASE}/projects/{pid}/research").json()["job_id"])
if job["error"]:
    print("ERROR:", job["error"])
print("stakeholder analysis...")
job = wait(c.post(f"{BASE}/projects/{pid}/stakeholders/analyze").json()["job_id"])
if job["error"]:
    print("ERROR:", job["error"])

report = c.get(f"{BASE}/projects/{pid}/report").json()
print(json.dumps({k: report[k] for k in ("research_scope", "stakeholder_scope")}, indent=2))
for s in report["similar_projects"][:5]:
    print(f"- {s['name']} ({s['similarity_score']}) {s['source_url']}")
for n in report["needs"]:
    print(f"* [{n['evidence_status']}] {n['need_text']}")
open("report.json", "w").write(json.dumps(report, indent=2, default=str))
print("full report saved to report.json")
