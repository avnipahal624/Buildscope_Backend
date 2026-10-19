"""Evidence-strength rules. Plain code on purpose: an LLM must not decide this."""
from dataclasses import dataclass

from app.research.cleaning import normalize_for_match, registered_domain

UNVERIFIED = "unverified"
SUPPORTED = "supported"
STRONGLY_SUPPORTED = "strongly_supported"
CONFLICTING = "conflicting"
NEEDS_MORE = "needs_further_research"


@dataclass
class Strength:
    status: str
    need_type: str            # explicit | pattern | hypothesis
    supporting: int
    contradicting: int
    independent_sources: int


def assess_strength(evidence: list[tuple[str, str, str]], min_domains: int = 3) -> Strength:
    """evidence = [(relation, excerpt, source_url)].

    Independence rules (deliberately conservative):
    * identical/copied excerpts count once
    * several pages on the same registered domain count as ONE source
    """
    seen_excerpts: set[str] = set()
    supporting_domains: set[str] = set()
    contradicting_domains: set[str] = set()
    supporting = contradicting = 0
    for relation, excerpt, url in evidence:
        key = (relation, normalize_for_match(excerpt))
        if key in seen_excerpts:
            continue
        seen_excerpts.add(key)
        domain = registered_domain(url) or url
        if relation == "supports":
            supporting += 1
            supporting_domains.add(domain)
        elif relation == "contradicts":
            contradicting += 1
            contradicting_domains.add(domain)

    independent = len(supporting_domains)
    if supporting and contradicting:
        status = CONFLICTING
    elif supporting == 0 and contradicting == 0:
        status = UNVERIFIED
    elif supporting == 0:
        status = NEEDS_MORE            # only disagreement found, nothing in favour
    elif independent >= min_domains:
        status = STRONGLY_SUPPORTED
    else:
        status = SUPPORTED

    need_type = "hypothesis" if supporting == 0 else ("pattern" if independent >= 2 else "explicit")
    return Strength(status, need_type, supporting, contradicting, independent)
