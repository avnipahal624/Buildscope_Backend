"""Background job executor. FastAPI BackgroundTasks calls execute_run(run_id)."""
from datetime import datetime, timezone

from app import db as database
from app import deps
from app.config import get_settings
from app.models import ResearchRun
from app.research.pipeline import run_research
from app.stakeholders.pipeline import run_stakeholder_analysis


def execute_run(run_id: str) -> None:
    settings = get_settings()
    with database.get_session_factory()() as session:
        run = session.get(ResearchRun, run_id)
        if run is None or run.status not in ("pending",):
            return
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        session.commit()
        llm = None
        try:
            adapter, llm = deps.get_adapter(), deps.get_llm()
            runner = run_research if run.kind == "research" else run_stakeholder_analysis
            status = runner(session, run, adapter, llm, settings)
            run.status = status
        except Exception as e:                      # never leave a run stuck in 'running'
            session.rollback()
            run = session.get(ResearchRun, run_id)
            run.status = "failed"
            run.error = f"{type(e).__name__}: {e}"
        finally:
            if llm is not None:
                run.usage = dict(llm.usage)
            run.finished_at = datetime.now(timezone.utc)
            session.commit()
