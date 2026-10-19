"""Show the most recent jobs and why they failed. Usage: python -m scripts.show_runs"""
import json
import sqlite3

con = sqlite3.connect("buildscope.db")
rows = con.execute(
    "select id, project_id, kind, status, error, log, scope from research_runs order by created_at desc limit 4"
)
for run_id, project_id, kind, status, error, log, scope in rows:
    print("=" * 60)
    print(kind, "->", status, "| project:", project_id, "| job:", run_id)
    print("error:", error)
    print("stage reached:", (json.loads(scope) if scope else {}).get("stage"))
    for entry in (json.loads(log) if log else [])[:15]:
        print(" -", entry["level"], entry["message"][:200])
