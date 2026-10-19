"""Collect needs from pages, verify excerpts, and cluster them into candidate needs."""
from dataclasses import dataclass, field

from app.config import Settings
from app.llm.prompts import NEED_EXTRACT_SYSTEM
from app.llm.schemas import ExtractedNeed, ExtractedNeedList
from app.models import Project, Source, Stakeholder
from app.research.cleaning import excerpt_in_text, normalize_for_match
from app.research.similarity import cosine
from app.runlog import RunLog


def build_queries(project: Project, groups: list[Stakeholder], settings: Settings) -> list[str]:
    topic = " ".join((project.keywords or [])[:3]) or project.name
    templates = ["{g} problems with {t}", "{g} frustrations {t} reddit", "{g} survey challenges {t}"]
    queries = []
    for g in groups:
        for t in templates[:settings.queries_per_group]:
            queries.append(t.format(g=g.name, t=topic))
    return queries


def extract_needs(llm, source: Source, project: Project, groups: list[Stakeholder],
                  settings: Settings, log: RunLog) -> list[ExtractedNeed]:
    text = source.content or ""
    names = [g.name for g in groups]
    user = (f"Project context: {project.name} - {project.problem_statement or project.description}\n"
            f"Stakeholder groups (use these exact names): {names}\n"
            f"Source URL: {source.url}\n\n<document>\n{text[:settings.max_page_chars_for_llm]}\n</document>")
    out = llm.complete_json(NEED_EXTRACT_SYSTEM, user, ExtractedNeedList)
    valid_names = {n.lower(): n for n in names}
    kept = []
    for n in out.needs:
        group = valid_names.get(n.stakeholder_group.strip().lower())
        if not group:
            log.warn(f"{source.url}: need for unknown group '{n.stakeholder_group}' ignored")
            continue
        if not excerpt_in_text(n.excerpt, text):
            log.warn(f"{source.url}: excerpt not found in page, need discarded: {n.excerpt[:60]!r}")
            continue
        n.stakeholder_group = group
        kept.append(n)
    return kept


@dataclass
class NeedCluster:
    group: str
    need_text: str
    vector: list[float]
    items: list[tuple[Source, ExtractedNeed, str]] = field(default_factory=list)  # (source, item, relation)


def cluster_needs(llm, raw: list[tuple[Source, ExtractedNeed]], settings: Settings) -> list[NeedCluster]:
    """Group similar need statements per stakeholder group.

    Supporting statements are clustered first; disputing statements are then attached to the
    closest cluster (lower threshold) so contradictions end up next to the claim they dispute.
    """
    if not raw:
        return []
    vectors = llm.embed([n.need_text for _, n in raw])
    clusters: list[NeedCluster] = []

    def best(group, vec):
        cands = [(cosine(vec, c.vector), c) for c in clusters if c.group == group]
        return max(cands, key=lambda t: t[0], default=(0.0, None))

    order = sorted(range(len(raw)), key=lambda i: raw[i][1].stance == "disputes_problem")
    for i in order:
        src, need = raw[i]
        vec = vectors[i]
        sim, cluster = best(need.stakeholder_group, vec)
        relation = "contradicts" if need.stance == "disputes_problem" else "supports"
        threshold = (settings.dispute_attach_threshold if relation == "contradicts"
                     else settings.need_cluster_threshold)
        if cluster is not None and sim >= threshold:
            target = cluster
        else:
            target = NeedCluster(need.stakeholder_group, need.need_text, vec)
            clusters.append(target)
        key = (src.id, normalize_for_match(need.excerpt))
        if not any((s.id, normalize_for_match(n.excerpt)) == key for s, n, _ in target.items):
            target.items.append((src, need, relation))
    return clusters
