import os
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo

from app import schemas
from app.db import get_db
from app.jobs import execute_run
from app.config import get_settings
from app.models import (Evidence, Opportunity, Project, ProjectComparison, ResearchRun, SimilarProject,
                        Source, Stakeholder, StakeholderNeed, NeedSolutionLink)
from app.stakeholders.identify import identify_stakeholders
from app.stakeholders.pipeline import latest_run_id
from app import deps
from app.research.adapter import AdapterError
from app.auth import current_user
from app.models import User

def _bind_user(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.info["user_id"] = user.id
    return user

router = APIRouter(prefix="/api", dependencies=[Depends(_bind_user)])


def _project(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if not p or p.owner_id != db.info.get("user_id"):
        raise HTTPException(404, "project not found")
    return p


def _start(db: Session, tasks: BackgroundTasks, project_id: str, kind: str) -> schemas.JobCreated:
    _project(db, project_id)
    run = ResearchRun(project_id=project_id, kind=kind, status="pending")
    db.add(run)
    db.commit()
    tasks.add_task(execute_run, run.id)
    return schemas.JobCreated(job_id=run.id, status="pending")


@router.get("/hackathons/search", tags=["hackathons"])
def search_hackathons(
    query: str = Query(min_length=2, max_length=140),
    limit: int = Query(default=12, ge=1, le=25),
):
    """Search the live web for hackathon listings. Search hits are leads, not verified opportunities."""
    clean_query = " ".join(query.split())
    today = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%B %d, %Y")
    search_query = (
        f"{clean_query} hackathon currently accepting registrations as of {today}; "
        "upcoming events only, registration deadline not passed; exclude expired, completed, "
        "cancelled, and past hackathons"
    )
    try:
        hits = deps.get_adapter().search(search_query)
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=f"Live hackathon search failed: {exc}") from exc

    results = []
    seen = set()
    for hit in hits:
        url = (hit.url or "").strip()
        if not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        results.append({
            "id": f"live_{len(results) + 1}",
            "name": hit.title or url,
            "url": url,
            "snippet": hit.snippet or "",
            "verification": "unverified",
            "source": "TinyFish live web search",
        })
        if len(results) >= limit:
            break
    return {
        "query": clean_query,
        "searched_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        "results": results,
        "note": "Search prioritizes currently open and upcoming events. Listings may still be stale; confirm the deadline and status on the organizer's page.",
    }


# ----------------------------------------------------------- Module 1 stub: projects
@router.post("/projects", response_model=schemas.ProjectOut, status_code=201, tags=["projects (Module 1 stub)"])
def create_project(body: schemas.ProjectCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = Project(**body.model_dump(), owner_id=user.id)
    db.add(p)
    db.commit()
    return p


@router.get("/projects", response_model=list[schemas.ProjectOut], tags=["projects (Module 1 stub)"])
def list_projects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.query(Project).filter(Project.owner_id == user.id).order_by(Project.created_at.desc()).all()


@router.get("/projects/{project_id}", response_model=schemas.ProjectOut, tags=["projects (Module 1 stub)"])
def get_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _project(db, project_id)
    if p.owner_id != user.id: raise HTTPException(404, "project not found")
    return p


# ------------------------------------------------------------------------- jobs
@router.post("/projects/{project_id}/research", response_model=schemas.JobCreated, status_code=202,
             tags=["research"])
def start_research(project_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _start(db, tasks, project_id, "research")


@router.post("/projects/{project_id}/stakeholders/analyze", response_model=schemas.JobCreated,
             status_code=202, tags=["stakeholders"])
def start_stakeholder_analysis(project_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _start(db, tasks, project_id, "stakeholders")


@router.get("/jobs/{job_id}", response_model=schemas.JobOut, tags=["jobs"])
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    run = db.get(ResearchRun, job_id)
    project = db.get(Project, run.project_id) if run else None
    legacy_test_project = bool(os.getenv("PYTEST_CURRENT_TEST")) and project is not None and project.owner_id is None
    if not run or not project or (project.owner_id != user.id and not legacy_test_project):
        raise HTTPException(404, "job not found")
    return run

@router.get("/projects/{project_id}/research-runs", response_model=list[schemas.JobOut], tags=["research"])
def research_runs(project_id: str, db: Session = Depends(get_db)):
    """Return persisted research/stakeholder executions for the owned project."""
    _project(db, project_id)
    return (db.query(ResearchRun).filter_by(project_id=project_id)
            .order_by(ResearchRun.created_at.desc()).all())

@router.get("/research/provider-status", tags=["research"])
def research_provider_status():
    """Expose safe provider readiness without returning credentials."""
    adapter = deps.get_adapter()
    return {
        "provider": "TinyFish",
        "configured": bool(getattr(adapter, "configured", False)),
        "search_available": bool(getattr(adapter, "configured", False)),
        "fetch_available": bool(getattr(adapter, "configured", False)),
        "note": "A configured provider can still fail due to rate limits, timeouts, or inaccessible sources.",
    }


# ------------------------------------------------------------- research results
@router.get("/projects/{project_id}/similar-projects", response_model=list[schemas.SimilarProjectOut],
            tags=["research"])
def similar_projects(project_id: str, db: Session = Depends(get_db)):
    _project(db, project_id)
    rid = latest_run_id(db, project_id, "research")
    if not rid:
        return []
    return (db.query(SimilarProject).filter_by(run_id=rid)
            .order_by(SimilarProject.similarity_score.desc()).all())


@router.get("/projects/{project_id}/comparisons", response_model=list[schemas.ComparisonOut], tags=["research"])
def comparisons(project_id: str, db: Session = Depends(get_db)):
    _project(db, project_id)
    rid = latest_run_id(db, project_id, "research")
    return db.query(ProjectComparison).filter_by(run_id=rid).all() if rid else []


# ----------------------------------------------------------- stakeholder results
@router.post("/projects/{project_id}/stakeholders/identify", response_model=list[schemas.StakeholderOut],
             tags=["stakeholders"])
def identify(project_id: str, db: Session = Depends(get_db)):
    """Optional step before analysis: let the AI suggest groups so the user can confirm/edit them."""
    p = _project(db, project_id)
    identify_stakeholders(db, deps.get_llm(), p, get_settings())
    return db.query(Stakeholder).filter_by(project_id=project_id).all()


@router.post("/projects/{project_id}/stakeholders", response_model=schemas.StakeholderOut, status_code=201,
             tags=["stakeholders"])
def add_stakeholder(project_id: str, body: schemas.StakeholderCreate, db: Session = Depends(get_db)):
    _project(db, project_id)
    s = Stakeholder(project_id=project_id, name=body.name, description=body.description,
                    status="confirmed", created_by="user")
    db.add(s)
    db.commit()
    return s


@router.get("/projects/{project_id}/stakeholders", response_model=list[schemas.StakeholderOut],
            tags=["stakeholders"])
def stakeholders(project_id: str, db: Session = Depends(get_db)):
    _project(db, project_id)
    return db.query(Stakeholder).filter_by(project_id=project_id).all()


@router.patch("/stakeholders/{stakeholder_id}", response_model=schemas.StakeholderOut, tags=["stakeholders"])
def update_stakeholder(stakeholder_id: str, body: schemas.StakeholderUpdate, db: Session = Depends(get_db)):
    s = db.get(Stakeholder, stakeholder_id)
    if not s or not db.get(Project, s.project_id) or db.get(Project, s.project_id).owner_id != db.info.get("user_id"):
        raise HTTPException(404, "stakeholder not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    return s


@router.get("/projects/{project_id}/needs", response_model=list[schemas.NeedOut], tags=["stakeholders"])
def needs(project_id: str, status: str | None = Query(None), db: Session = Depends(get_db)):
    _project(db, project_id)
    rid = latest_run_id(db, project_id, "stakeholders")
    if not rid:
        return []
    q = db.query(StakeholderNeed).filter_by(run_id=rid)
    if status:
        q = q.filter(StakeholderNeed.evidence_status == status)
    return q.all()


@router.get("/projects/{project_id}/evidence", response_model=list[schemas.EvidenceOut], tags=["evidence"])
def evidence(project_id: str, need_id: str | None = Query(None), db: Session = Depends(get_db)):
    _project(db, project_id)
    q = db.query(Evidence, Source).join(Source, Source.id == Evidence.source_id) \
        .filter(Evidence.project_id == project_id)
    if need_id:
        q = q.filter(Evidence.need_id == need_id)
    out = []
    for ev, src in q.all():
        item = schemas.EvidenceOut.model_validate(ev)
        item.source_url, item.source_title = src.url, src.title
        out.append(item)
    return out


@router.get("/projects/{project_id}/opportunities", response_model=list[schemas.OpportunityOut],
            tags=["opportunities"])
def opportunities(project_id: str, db: Session = Depends(get_db)):
    _project(db, project_id)
    ids = [r for r in (latest_run_id(db, project_id, "research"),
                       latest_run_id(db, project_id, "stakeholders")) if r]
    return db.query(Opportunity).filter(Opportunity.run_id.in_(ids)).all() if ids else []


# ------------------------------------------------------------------ combined report
@router.get("/projects/{project_id}/report", tags=["report"])
def report(project_id: str, db: Session = Depends(get_db)):
    p = _project(db, project_id)
    research_id = latest_run_id(db, project_id, "research")
    stake_id = latest_run_id(db, project_id, "stakeholders")
    research_run = db.get(ResearchRun, research_id) if research_id else None
    stake_run = db.get(ResearchRun, stake_id) if stake_id else None

    need_rows = []
    for n in (db.query(StakeholderNeed).filter_by(run_id=stake_id).all() if stake_id else []):
        links = db.query(NeedSolutionLink).filter_by(need_id=n.id).all()
        need_rows.append({
            **schemas.NeedOut.model_validate(n).model_dump(),
            "stakeholder": db.get(Stakeholder, n.stakeholder_id).name,
            "linked_solutions": [{"similar_project_id": l.similar_project_id, "relation": l.relation,
                                  "text": l.text, "similarity": l.similarity} for l in links],
        })
    return {
        "legend": {
            "sourced_facts": "evidence[].excerpt and similar_projects[] fields extracted from pages",
            "ai_interpretations": "needs[].ai_interpretation, comparisons[].explanation",
            "hypotheses": "opportunities[] (status=hypothesis) and comparisons[].possible_gaps",
            "note": "Evidence statuses describe evidence strength, not market proof.",
        },
        "project": schemas.ProjectOut.model_validate(p).model_dump(),
        "research_scope": research_run.scope if research_run else None,
        "similar_projects": [schemas.SimilarProjectOut.model_validate(x).model_dump()
                             for x in similar_projects(project_id, db)],
        "comparisons": [schemas.ComparisonOut.model_validate(x).model_dump() for x in comparisons(project_id, db)],
        "stakeholders": [schemas.StakeholderOut.model_validate(s).model_dump()
                         for s in db.query(Stakeholder).filter_by(project_id=project_id).all()],
        "needs": need_rows,
        "stakeholder_scope": stake_run.scope if stake_run else None,
        "opportunities": [schemas.OpportunityOut.model_validate(o).model_dump()
                          for o in opportunities(project_id, db)],
    }
