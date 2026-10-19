"""Label results in the terminal (no Excel). Answers are saved after every item.

Usage (server must be running):
    python -m scripts.label_review <project_id> [--projects 10] [--needs 15]

For each item type  y  or  n  and press Enter.   s = skip,  o = open the link in your browser,
q = quit (your answers are kept; run the same command again to continue).
"""
import argparse
import json
import os
import sys
import textwrap
import webbrowser

import httpx

LABELS_FILE = "labels.json"


def load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"projects": {}, "evidence": {}}


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def wrap(text, indent="    ", width=88):
    return textwrap.fill(str(text), width=width, initial_indent=indent, subsequent_indent=indent)


def ask(question, opener=None, url=None, input_fn=input):
    """Return True/False for y/n, None for skip, 'quit' for q."""
    while True:
        answer = input_fn(f"  {question} [y/n/s=skip/o=open link/q=quit]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        if answer in ("s", "skip", ""):
            return None
        if answer in ("q", "quit"):
            return "quit"
        if answer in ("o", "open") and url:
            (opener or webbrowser.open)(url)
            print("    (opened in your browser)")
            continue
        print("    Please type y, n, s, o or q.")


def pick_evidence(evidence, needs, limit):
    """Round-robin over needs so the sample covers different needs, supporting quotes first."""
    by_need = {}
    for e in evidence:
        if e.get("need_id") in needs:
            by_need.setdefault(e["need_id"], []).append(e)
    for items in by_need.values():
        items.sort(key=lambda e: e["relation"] != "supports")
    picked, round_ = [], 0
    while len(picked) < limit and any(len(v) > round_ for v in by_need.values()):
        for items in by_need.values():
            if len(items) > round_ and len(picked) < limit:
                picked.append(items[round_])
        round_ += 1
    return picked


def rate(values):
    vals = [v for v in values if v is not None]
    return (sum(vals) / len(vals), len(vals)) if vals else None


def summarise(data, ranked_project_ids):
    labels = [data["projects"].get(pid) for pid in ranked_project_ids]
    out = {f"precision@{k}": rate(labels[:k]) for k in (3, 5, 10)}
    ev = list(data["evidence"].values())
    out["real_stakeholder"] = rate([e.get("real") for e in ev])
    out["quote_supports_need"] = rate([e.get("supports") for e in ev])
    return out


def run(get, pid, n_projects=10, n_needs=15, path=LABELS_FILE, input_fn=input, opener=None):
    data = load(path)
    projects = get(f"/api/projects/{pid}/similar-projects")            # already ranked best-first
    needs = {n["id"]: n for n in get(f"/api/projects/{pid}/needs")}
    evidence = pick_evidence(get(f"/api/projects/{pid}/evidence"), needs, n_needs)
    ranked_ids = [p["id"] for p in projects[:max(n_projects, 10)]]

    print(f"\n=== PART 1: top {min(n_projects, len(projects))} discovered projects ===")
    print("Question: is this a real project/product SIMILAR to your idea?\n")
    for rank, p in enumerate(projects[:n_projects], start=1):
        if p["id"] in data["projects"]:
            continue
        print(f"[{rank}/{min(n_projects, len(projects))}] {p['name']}   (score {p['similarity_score']}, "
              f"extraction confidence: {p['extraction_confidence']})")
        print(f"    {p['source_url']}")
        if p.get("description"):
            print(wrap(p["description"][:300]))
        if p.get("features"):
            print(wrap("Features: " + "; ".join(p["features"][:5])))
        a = ask("Relevant to your idea?", opener, p["source_url"], input_fn)
        if a == "quit":
            save(path, data)
            return summarise(data, ranked_ids)
        if a is not None:
            data["projects"][p["id"]] = a
            save(path, data)
        print()

    print(f"\n=== PART 2: {len(evidence)} quotes (one or two per need) ===")
    print("Q1: is the quote from a REAL stakeholder (a user, review, survey), not a company's marketing?")
    print("Q2: does the quote really SUPPORT the need written above it?\n")
    for i, e in enumerate(evidence, start=1):
        if e["id"] in data["evidence"]:
            continue
        n = needs[e["need_id"]]
        print(f"[{i}/{len(evidence)}] NEED ({n['evidence_status']}): {n['need_text']}")
        print(wrap(f"QUOTE ({e['relation']}): \"{e['excerpt']}\""))
        print(f"    {e.get('source_url')}")
        real = ask("Q1 real stakeholder?", opener, e.get("source_url"), input_fn)
        if real == "quit":
            save(path, data)
            return summarise(data, ranked_ids)
        supports = ask("Q2 quote supports the need?", opener, e.get("source_url"), input_fn)
        if supports == "quit":
            save(path, data)
            return summarise(data, ranked_ids)
        if real is not None or supports is not None:
            data["evidence"][e["id"]] = {"real": real, "supports": supports}
            save(path, data)
        print()
    return summarise(data, ranked_ids)


def show(results):
    print("\n=== YOUR QUALITY NUMBERS ===")
    for name, r in results.items():
        print(f"{name:22s}", "no answers yet" if r is None else f"{r[0]:.0%}  (from {r[1]} labelled)")
    print("\nReport these as 'manual check of N items', never as a general accuracy figure.")
    print(f"Your answers are saved in {LABELS_FILE}. Run the same command again to continue or add more.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project_id")
    ap.add_argument("--projects", type=int, default=10)
    ap.add_argument("--needs", type=int, default=15)
    a = ap.parse_args()
    client = httpx.Client(base_url="http://localhost:8000", timeout=60)
    try:
        show(run(lambda path: client.get(path).json(), a.project_id, a.projects, a.needs))
    except httpx.ConnectError:
        sys.exit("Cannot reach the server on http://localhost:8000. Start it with: uvicorn app.main:app --reload")
