from sqlalchemy.orm import Session

from app.config import Settings
from app.llm.prompts import STAKEHOLDER_SYSTEM
from app.llm.schemas import StakeholderList
from app.models import Project, Stakeholder
from app.research.extraction import project_profile


def identify_stakeholders(db: Session, llm, project: Project, settings: Settings) -> list[Stakeholder]:
    """Ask the LLM for stakeholder groups. They are stored as 'suggested' until the user confirms."""
    out = llm.complete_json(
        STAKEHOLDER_SYSTEM,
        f"Project:\n{project_profile(project)}\n\nReturn at most {settings.max_stakeholder_groups} groups.",
        StakeholderList)
    existing = {s.name.lower() for s in db.query(Stakeholder).filter_by(project_id=project.id)}
    created = []
    for g in out.groups[:settings.max_stakeholder_groups]:
        name = g.name.strip()
        if not name or name.lower() in existing:
            continue
        existing.add(name.lower())
        s = Stakeholder(project_id=project.id, name=name, description=g.description,
                        status="suggested", created_by="ai")
        db.add(s)
        created.append(s)
    db.commit()
    return created
