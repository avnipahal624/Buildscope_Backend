"""Show the items you labelled 'n' (with their text), so you can see what went wrong.

Usage (server running):  python -m scripts.show_failures <project_id>
"""
import json
import os
import sys
import textwrap

import httpx

LABELS_FILE = "labels.json"


def wrap(text, indent="    ", width=88):
    return textwrap.fill(str(text), width=width, initial_indent=indent, subsequent_indent=indent)


def failures(get, pid, path=LABELS_FILE) -> dict:
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found. Run 'python -m scripts.label_review {pid}' first.")
    data = json.load(open(path, encoding="utf-8"))
    projects = {p["id"]: p for p in get(f"/api/projects/{pid}/similar-projects")}
    needs = {n["id"]: n for n in get(f"/api/projects/{pid}/needs")}
    evidence = {e["id"]: e for e in get(f"/api/projects/{pid}/evidence")}
    out = {"projects": [], "not_real": [], "not_supporting": [], "missing": 0}
    for pid_, label in data["projects"].items():
        if label is False and pid_ in projects:
            out["projects"].append(projects[pid_])
        elif pid_ not in projects:
            out["missing"] += 1
    for eid, lab in data["evidence"].items():
        e = evidence.get(eid)
        if not e:
            out["missing"] += 1
            continue
        if lab.get("real") is False:
            out["not_real"].append(e)
        if lab.get("supports") is False:
            out["not_supporting"].append(e)
    out["needs"] = needs
    return out


def show(out):
    print(f"\n=== PROJECTS YOU MARKED NOT RELEVANT ({len(out['projects'])}) ===")
    for p in out["projects"]:
        print(f"- {p['name']}  (score {p['similarity_score']}, rank by score)\n    {p['source_url']}")
        if p.get("description"):
            print(wrap(p["description"][:250]))
    print(f"\n=== QUOTES THAT DID NOT SUPPORT THEIR NEED ({len(out['not_supporting'])}) ===")
    for e in out["not_supporting"]:
        n = out["needs"].get(e["need_id"], {})
        print(f"NEED ({n.get('evidence_status')}): {n.get('need_text')}")
        print(wrap(f"QUOTE ({e['relation']}): \"{e['excerpt']}\""))
        print(f"    {e.get('source_url')}")
        if e["relation"] == "contradicts":
            print("    NOTE: this quote DISPUTES the need. An 'n' to 'supports' is expected if you "
                  "answered with the old wording; it may not be an error.")
        print()
    print(f"=== QUOTES NOT FROM A REAL STAKEHOLDER ({len(out['not_real'])}) ===")
    for e in out["not_real"]:
        n = out["needs"].get(e["need_id"], {})
        print(f"NEED: {n.get('need_text')}")
        print(wrap(f"QUOTE: \"{e['excerpt']}\""))
        print(f"    {e.get('source_url')}\n")
    if out["missing"]:
        print(f"({out['missing']} labelled item(s) no longer exist in the latest results, "
              "for example after a re-run, so they are not shown.)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m scripts.show_failures <project_id>")
    client = httpx.Client(base_url="http://localhost:8000", timeout=60)
    try:
        show(failures(lambda p: client.get(p).json(), sys.argv[1]))
    except httpx.ConnectError:
        sys.exit("Cannot reach the server. Start it with: uvicorn app.main:app --reload")