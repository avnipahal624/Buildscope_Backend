"""Endpoints for step 5 (requirement) and step 6 (verification) + the proof chain."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app import db as database
from app.chain import generate_requirement, get_chain, run_verification
from app.deps import get_llm
from app.llm.client import LLMError
from app.models import Opportunity, Project, Requirement
from app.auth import current_user

router = APIRouter(tags=["proof-chain"], dependencies=[Depends(current_user)])


def _session():
    with database.get_session_factory()() as s:
        yield s


@router.get("/opportunities")
def _owned_opportunity(db, opportunity_id: str, user):
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity or not db.get(Project, opportunity.project_id) or db.get(Project, opportunity.project_id).owner_id != user.id:
        raise HTTPException(404, "Opportunity not found")
    return opportunity


def list_opportunities(db=Depends(_session), user=Depends(current_user)):
    """Use this first to find an opportunity id."""
    rows = db.scalars(select(Opportunity).join(Project, Project.id == Opportunity.project_id)
                      .where(Project.owner_id == user.id).order_by(Opportunity.created_at.desc()))
    return [
        {"id": o.id, "description": o.description[:150], "linked_needs": len(o.linked_need_ids or [])}
        for o in rows
    ]


@router.post("/opportunities/{opportunity_id}/requirement")
def create_requirement(opportunity_id: str, db=Depends(_session), user=Depends(current_user)):
    _owned_opportunity(db, opportunity_id, user)
    try:
        req = generate_requirement(db, opportunity_id, get_llm())
    except ValueError as e:
        raise HTTPException(404, str(e))
    except LLMError as e:
        raise HTTPException(502, f"LLM call failed: {e}")
    return {"id": req.id, "text": req.text, "acceptance_test": req.acceptance_test}


@router.post("/requirements/{requirement_id}/verify")
def verify_requirement(requirement_id: str, db=Depends(_session), user=Depends(current_user)):
    requirement = db.get(Requirement, requirement_id)
    if not requirement:
        raise HTTPException(404, "Requirement not found")
    _owned_opportunity(db, requirement.opportunity_id, user)
    try:
        results = run_verification(db, requirement_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return [{"test": r.test_name, "result": r.result, "details": r.details} for r in results]


@router.get("/opportunities/{opportunity_id}/chain")
def opportunity_chain(opportunity_id: str, db=Depends(_session), user=Depends(current_user)):
    _owned_opportunity(db, opportunity_id, user)
    try:
        return get_chain(db, opportunity_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
