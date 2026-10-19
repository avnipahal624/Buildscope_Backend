"""Step 1: save and list a project's own requirements."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import db as database
from app.models import Project, ProjectRequirement

router = APIRouter(tags=["project-requirements"])


def _session():
    with database.get_session_factory()() as s:
        yield s


class ProjectRequirementIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    requirement_type: str = "functional"
    priority: str = "medium"


def _out(r: ProjectRequirement) -> dict:
    return {
        "id": r.id, "project_id": r.project_id, "title": r.title,
        "description": r.description, "requirement_type": r.requirement_type,
        "priority": r.priority,
    }


@router.post("/projects/{project_id}/requirements")
def add_project_requirement(project_id: str, body: ProjectRequirementIn, db=Depends(_session)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    r = ProjectRequirement(project_id=project_id, **body.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return _out(r)


@router.get("/projects/{project_id}/requirements")
def list_project_requirements(project_id: str, db=Depends(_session)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    rows = db.scalars(select(ProjectRequirement).where(ProjectRequirement.project_id == project_id))
    return [_out(r) for r in rows]