from contextlib import asynccontextmanager

from fastapi import FastAPI

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bulidscope-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.api.routes import router
from app.api.chain_routes import router as chain_router  
from app.api.project_requirement_routes import router as project_req_router # <-- NEW LINE 1
from app import db as database
from app.db import init_db
from app.models import ResearchRun


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # creates tables on first start (swap for Alembic later)
    # FastAPI background tasks do not survive a restart: don't leave orphaned jobs 'running'.
    with database.get_session_factory()() as s:
        for run in s.query(ResearchRun).filter(ResearchRun.status.in_(["pending", "running"])):
            run.status, run.error = "failed", "server restarted before the job finished; start it again"
        s.commit()
    yield


app = FastAPI(title="BuildScope AI - Research & Stakeholder modules", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(chain_router)
app.include_router(project_req_router)                            # <-- NEW LINE 2


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}