"""Export results to CSV files you can open in Excel and label by hand.

Usage:  python -m scripts.export_review <project_id>
Creates review_projects.csv and review_needs.csv in the current folder.
Fill the blank columns with y or n, save, then run:  python -m scripts.score_review
"""
import csv
import sys

import httpx


def export(get, pid: str, out_dir: str = ".") -> tuple[int, int]:
    projects = get(f"/api/projects/{pid}/similar-projects")
    needs = {n["id"]: n for n in get(f"/api/projects/{pid}/needs")}
    evidence = get(f"/api/projects/{pid}/evidence")

    with open(f"{out_dir}/review_projects.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rank", "name", "url", "score", "extraction_confidence", "excerpt_verified",
                    "features", "limitations", "RELEVANT (y/n)"])
        for i, p in enumerate(projects, start=1):
            w.writerow([i, p["name"], p["source_url"], p["similarity_score"], p["extraction_confidence"],
                        p["excerpt_verified"], "; ".join(p["features"]), "; ".join(p["limitations"]), ""])

    rows = 0
    with open(f"{out_dir}/review_needs.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["need", "status", "relation", "quote", "source_url",
                    "REAL STAKEHOLDER, not vendor marketing (y/n)", "QUOTE SUPPORTS THE NEED (y/n)"])
        for e in evidence:
            n = needs.get(e["need_id"])
            if n:
                w.writerow([n["need_text"], n["evidence_status"], e["relation"], e["excerpt"],
                            e["source_url"], "", ""])
                rows += 1
    return len(projects), rows


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m scripts.export_review <project_id>")
    client = httpx.Client(base_url="http://localhost:8000", timeout=60)
    p, n = export(lambda path: client.get(path).json(), sys.argv[1])
    print(f"wrote review_projects.csv ({p} projects) and review_needs.csv ({n} evidence rows)")
    print("Label a SAMPLE (about 10 projects, 15 quotes), save, then run: python -m scripts.score_review")