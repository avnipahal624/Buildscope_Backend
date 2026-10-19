"""Step 5/6: Opportunity -> Requirement -> Verification, plus the proof chain."""
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.models import (
    Evidence, Opportunity, Requirement, Source, StakeholderNeed, VerificationResult,
)


class RequirementDraft(BaseModel):
    text: str = Field(description="One testable requirement, starting with 'The system shall'")
    acceptance_test: str = Field(description="A concrete check that shows the requirement works")


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def _needs_and_evidence(db: Session, opp: Opportunity):
    need_ids = opp.linked_need_ids or []
    needs = list(db.scalars(select(StakeholderNeed).where(StakeholderNeed.id.in_(need_ids)))) if need_ids else []
    evidence = list(db.scalars(select(Evidence).where(Evidence.need_id.in_(need_ids)))) if need_ids else []
    return needs, evidence


# ------------------------------------------------------------ Step 5: requirement
def generate_requirement(db: Session, opportunity_id: str, llm: LLMClient | None = None) -> Requirement:
    opp = db.get(Opportunity, opportunity_id)
    if not opp:
        raise ValueError("Opportunity not found")
    needs, evidence = _needs_and_evidence(db, opp)

    need_lines = "\n".join(f"- {n.need_text}" for n in needs) or "- (none linked)"
    evidence_lines = "\n".join(f'- "{e.excerpt[:300]}"' for e in evidence[:5]) or "- (none)"

    system = (
        "You are a requirements engineer. Write ONE specific, testable software requirement "
        "that solves the stakeholder NEED. The need is what real users want. The opportunity "
        "text may quote a limitation of some other product: treat that as background, and do "
        "not copy it as the requirement. The acceptance test must be something that can be "
        "checked by running the software, with a measurable result where possible. "
        "Use only the information given. Do not invent facts."
    )
    user = (
        f"Stakeholder need (the requirement must address this):\n{need_lines}\n\n"
        f"Evidence from real users:\n{evidence_lines}\n\n"
        f"Background opportunity: {opp.description}\n"
        f"Rationale: {opp.rationale}"
    )
    llm = llm or LLMClient()
    draft = llm.complete_json(system, user, RequirementDraft)

    req = Requirement(
        project_id=opp.project_id,
        opportunity_id=opp.id,
        text=draft.text,
        acceptance_test=draft.acceptance_test,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# ------------------------------------------------------------ Step 6: verification
def run_verification(db: Session, requirement_id: str) -> list[VerificationResult]:
    req = db.get(Requirement, requirement_id)
    if not req:
        raise ValueError("Requirement not found")
    opp = db.get(Opportunity, req.opportunity_id)
    _, evidence = _needs_and_evidence(db, opp)

    results: list[VerificationResult] = []

    def save(name: str, result: str, details: str):
        r = VerificationResult(requirement_id=req.id, test_name=name, result=result, details=details)
        db.add(r)
        results.append(r)

    if not evidence:
        save("evidence_exists", "fail", "No evidence is linked to this requirement's opportunity.")
    else:
        save("evidence_exists", "pass", f"{len(evidence)} evidence item(s) linked.")

    # Test A: is each quoted excerpt really inside the stored page text?
    for ev in evidence[:5]:
        src = db.get(Source, ev.source_id)
        if not src or not src.content:
            save("excerpt_in_source", "error", f"No stored page text for evidence {ev.id}.")
        elif _norm(ev.excerpt) in _norm(src.content):
            save("excerpt_in_source", "pass", f"Excerpt found in {src.url}")
        else:
            save("excerpt_in_source", "fail", f"Excerpt NOT found in {src.url}")

    # Test B: does the evidence source URL still load?
    for ev in evidence[:5]:
        src = db.get(Source, ev.source_id)
        if not src:
            continue
        try:
            resp = httpx.get(src.url, timeout=10, follow_redirects=True)
            ok = resp.status_code < 400
            save("source_url_reachable", "pass" if ok else "fail", f"{src.url} returned {resp.status_code}")
        except httpx.HTTPError as e:
            save("source_url_reachable", "error", f"{src.url}: {e}")

    db.commit()
    for r in results:
        db.refresh(r)
    return results


# ------------------------------------------------------------ The proof chain
def get_chain(db: Session, opportunity_id: str) -> dict:
    opp = db.get(Opportunity, opportunity_id)
    if not opp:
        raise ValueError("Opportunity not found")
    needs, evidence = _needs_and_evidence(db, opp)
    reqs = list(db.scalars(select(Requirement).where(Requirement.opportunity_id == opp.id)))
    out_reqs = []
    for r in reqs:
        tests = list(db.scalars(select(VerificationResult).where(VerificationResult.requirement_id == r.id)))
        out_reqs.append({
            "id": r.id, "text": r.text, "acceptance_test": r.acceptance_test,
            "verification": [
                {"test": t.test_name, "result": t.result, "details": t.details,
                 "tested_at": t.tested_at.isoformat()} for t in tests
            ],
        })
    ev_out = []
    for e in evidence:
        src = db.get(Source, e.source_id)
        ev_out.append({"id": e.id, "excerpt": e.excerpt, "relation": e.relation,
                       "source_url": src.url if src else None})
    return {
        "opportunity": {"id": opp.id, "description": opp.description, "rationale": opp.rationale},
        "needs": [{"id": n.id, "text": n.need_text, "evidence_status": n.evidence_status} for n in needs],
        "evidence": ev_out,
        "requirements": out_reqs,
    }

