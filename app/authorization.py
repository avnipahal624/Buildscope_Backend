"""Ownership checks shared by all nested-resource endpoints."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Opportunity, Project, Requirement, User


def owned_project(db: Session, project_id: str, user: User) -> Project:
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(404, "Project not found")
    return project


def owned_opportunity(db: Session, opportunity_id: str, user: User) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(404, "Opportunity not found")
    owned_project(db, opportunity.project_id, user)
    return opportunity


def owned_requirement(db: Session, requirement_id: str, user: User) -> Requirement:
    requirement = db.get(Requirement, requirement_id)
    if not requirement:
        raise HTTPException(404, "Requirement not found")
    owned_opportunity(db, requirement.opportunity_id, user)
    return requirement
