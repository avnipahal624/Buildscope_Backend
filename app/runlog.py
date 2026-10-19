"""Small helpers for run logging and progress reporting."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ResearchRun

COVERAGE_NOTE = (
    "Search coverage is incomplete: private repositories, blocked pages and poorly indexed "
    "projects may be missed. Absence of a match is not evidence that an idea is original."
)


class RunLog:
    """Collects warnings/errors for a run and counts them."""

    def __init__(self):
        self.entries: list[dict] = []
        self.errors = 0
        self.warnings = 0

    def warn(self, msg: str):
        self.warnings += 1
        self.entries.append({"level": "warning", "message": msg,
                             "at": datetime.now(timezone.utc).isoformat()})

    def error(self, msg: str):
        self.errors += 1
        self.entries.append({"level": "error", "message": msg,
                             "at": datetime.now(timezone.utc).isoformat()})


def checkpoint(db: Session, run: ResearchRun, log: RunLog, stage: str, **extra):
    """Persist progress so GET /api/jobs/{id} shows what is happening."""
    scope = dict(run.scope or {})
    scope["stage"] = stage
    scope.update(extra)
    run.scope = scope
    run.log = list(log.entries)
    db.commit()
