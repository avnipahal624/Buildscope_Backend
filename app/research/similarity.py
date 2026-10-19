"""Hybrid similarity: embeddings + problem + user overlap + feature overlap."""
import math
import re

from app.models import Project

WEIGHTS = {"description": 0.40, "problem": 0.25, "users": 0.15, "features": 0.20}


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def list_overlap(wanted: list[str], found: list[str]) -> float | None:
    """For each wanted item, take its best token-overlap with any found item; average."""
    if not wanted or not found:
        return None
    found_tokens = [_tokens(f) for f in found]
    best = [max(jaccard(_tokens(w), ft) for ft in found_tokens) for w in wanted]
    return sum(best) / len(best)


def score_projects(llm, project: Project, candidates: list[dict]) -> list[tuple[float, dict]]:
    """candidates: dicts with description, problem_solved, target_users, features, name.

    Returns [(score, components)] in the same order. Components set to None are
    unavailable (unknown) and excluded from the weighted average.
    """
    texts: list[str] = []
    index: dict[tuple, int] = {}

    def add(key, text):
        if text and text.strip():
            index[key] = len(texts)
            texts.append(text)

    add(("p", "description"), project.description)
    add(("p", "problem"), project.problem_statement)
    for i, c in enumerate(candidates):
        add((i, "description"), c.get("description") or c.get("name"))
        add((i, "problem"), c.get("problem_solved"))
    vectors = llm.embed(texts) if texts else []

    def sim(i, field):
        a, b = index.get(("p", field)), index.get((i, field))
        if a is None or b is None:
            return None
        return max(0.0, cosine(vectors[a], vectors[b]))

    out = []
    for i, c in enumerate(candidates):
        users_a = [u.lower() for u in (project.target_users or [])]
        users_b = [u.lower() for u in (c.get("target_users") or [])]
        comps = {
            "description": sim(i, "description"),
            "problem": sim(i, "problem"),
            "users": list_overlap(users_a, users_b),
            "features": list_overlap(project.planned_features or [], c.get("features") or []),
        }
        avail = {k: v for k, v in comps.items() if v is not None}
        total_w = sum(WEIGHTS[k] for k in avail)
        score = sum(WEIGHTS[k] * v for k, v in avail.items()) / total_w if total_w else 0.0
        out.append((round(score, 4), {k: (None if v is None else round(v, 4)) for k, v in comps.items()}))
    return out
