# BuildScope AI — Backend

**Research Analysis + Stakeholder Intelligence**

BuildScope AI helps teams investigate an early-stage product idea before committing to implementation. This repository contains the Python API and research-processing backend: it gathers public-web material, extracts structured information, compares related projects, and organizes evidence about potential users and their needs.

> **Evidence-first principle:** BuildScope AI is a research aid, not an originality certificate or a guarantee that a product will succeed. AI-generated interpretations and possible opportunities must be reviewed against their sources.

- **Frontend:** [BuildScope AI — React workspace](https://github.com/avnipahal624/Bulidscope_frontend)
- **Backend:** [Buildscope_Backend](https://github.com/avnipahal624/Buildscope_Backend)
- **API documentation (local):** `http://localhost:8000/docs`

## Why this backend exists

An idea description alone is not enough to decide whether something is worth building. The backend turns an idea into a more structured investigation:

1. Generate varied research queries from the submitted idea.
2. Retrieve potentially relevant public sources.
3. clean and deduplicate source material.
4. Extract structured details about existing projects and stakeholder needs.
5. Compare related projects and record evidence, gaps, and possible opportunities.
6. Preserve job status, warnings, and errors so an investigation is not silently presented as successful when part of it failed.

The result is intended to help a team ask better questions and make a more informed build/no-build decision.

## Core modules

### 1. Research Analysis

Research Analysis looks for existing products and projects related to an idea.

- Generates multiple search queries.
- Retrieves source pages and their content.
- Normalizes URLs, removes duplicates, and caches fetched content.
- Uses an LLM to extract structured project information.
- Checks extracted excerpts against retrieved page content.
- Ranks similar projects using available relevance signals.
- Produces comparisons and records possible opportunities as hypotheses.

Similarity ranking can consider description similarity, problem similarity, target-user overlap, and feature overlap. Configurable weights are used; these scores are prioritization signals, not proof that two ideas are equivalent or that an idea is novel.

### 2. Stakeholder Intelligence

Stakeholder Intelligence investigates who might use a product and what problems public evidence suggests they experience.

- Identifies stakeholder groups relevant to the idea.
- Searches for public evidence about problems, frustrations, and requirements.
- Extracts structured needs from source material.
- Groups similar needs using embedding-based similarity.
- Records supporting and contradicting evidence.
- Applies explicit rules to assess evidence strength.
- Links needs to existing features and limitations.
- Suggests opportunities that deserve further research.

AI interpretations are stored separately from source excerpts. A need is not considered validated just because a model generated it.

## TinyFish integration

TinyFish is part of the backend's **web-research and source-retrieval layer**. It helps the research workflow move from a submitted idea to public web material that can be examined by later stages.

### Where it fits

```text
Project idea
    |
    v
Query generation
    |
    v
TinyFish web search / page retrieval
    |
    v
Source cleaning, URL normalization and deduplication
    |
    v
Structured extraction with an LLM
    |
    v
Excerpt checks, relevance ranking and comparison
    |
    v
Research findings, evidence and opportunity hypotheses
```

### Why TinyFish matters

- **Discovery:** research queries can lead the workflow toward relevant public pages.
- **Retrieval:** page content gives later processing stages material to inspect rather than relying only on the original idea prompt.
- **Evidence trail:** retrieved material can be associated with extracted details and excerpts for review.
- **Downstream analysis:** cleaned source material feeds extraction, similarity ranking, comparison, and stakeholder-need analysis.

TinyFish is not the component that independently proves a claim, validates market demand, or decides whether an idea is original. The backend's extraction and evidence checks are separate stages, and the quality of the final analysis still depends on source quality, coverage, model behaviour, and human review.

### Configure TinyFish

1. Obtain an API key through your authorized TinyFish account.
2. Add it to your local `.env` file as `TINYFISH_API_KEY`.
3. Check `.env.example` and `app/config.py` for the configuration names and defaults used by the current code.
4. Run the TinyFish provider check described in `GUIDE.md`.
5. Review the command output and logs before treating live retrieval as verified.

Never commit `.env`, publish API keys, or place provider credentials in frontend code. Configure production secrets in the hosting provider's environment settings.

The exact provider behaviour and availability must be confirmed using a real credential and the live integration check. Offline tests do not establish that the external service is currently reachable or that credentials and response formats are valid.

## Technology stack

| Technology | Role |
|---|---|
| Python 3.11+ | Backend runtime |
| FastAPI | HTTP API and interactive API documentation |
| Pydantic | Request/response data validation |
| SQLAlchemy | Database access and models |
| PostgreSQL | Intended deployed database; SQLite is used for offline tests |
| TinyFish | Web search and page retrieval for research |
| OpenAI-compatible LLM API | Structured extraction and analysis |
| Embedding API | Similarity operations and grouping |
| Docker Compose | Local supporting services |
| Pytest | Automated tests |

## Architecture overview

The application separates API handling, configuration and persistence, long-running jobs, provider access, research processing, and stakeholder analysis.

```text
app/
├── main.py
├── config.py
├── db.py
├── models.py
├── schemas.py
├── deps.py
├── jobs.py
├── runlog.py
├── api/
│   └── routes.py
├── llm/
│   ├── client.py
│   ├── schemas.py
│   └── prompts.py
├── research/
│   ├── adapter.py
│   ├── safety.py
│   ├── cleaning.py
│   ├── sourcing.py
│   ├── extraction.py
│   ├── similarity.py
│   ├── comparison.py
│   └── pipeline.py
└── stakeholders/
    ├── identify.py
    ├── evidence.py
    ├── strength.py
    ├── analysis.py
    ├── linking.py
    └── pipeline.py

scripts/     # Provider checks and demonstration workflows
tests/       # Automated tests
```

### Processing and reliability notes

- **Source processing:** URL normalization, deduplication, cleaning, and caching help reduce repeated or noisy material.
- **Evidence checks:** extracted excerpts are checked against retrieved page content. A text match alone does not prove that the source supports the full claim.
- **Similarity ranking:** missing similarity signals can be excluded and the remaining weights adjusted.
- **Background work:** longer investigations run as background jobs; callers can inspect status, warnings, errors, and usage information.
- **Partial failure:** job outcomes distinguish successful completion from completion with errors and failure.

## Getting started

### Prerequisites

- Python 3.11 or newer
- Git
- Docker Desktop or Docker Engine with Docker Compose
- TinyFish API key for live web research
- LLM API credentials for extraction and analysis
- An embedding endpoint/model for similarity operations

### 1. Clone the repository

```bash
git clone https://github.com/avnipahal624/Buildscope_Backend.git
cd Buildscope_Backend
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the environment template:

**macOS / Linux**

```bash
cp .env.example .env
```

**Windows Command Prompt**

```cmd
copy .env.example .env
```

Review `.env.example` and `app/config.py` for the exact settings supported by this version. The main settings documented by the project include:

| Variable | Purpose |
|---|---|
| `TINYFISH_API_KEY` | TinyFish access for live search and page retrieval |
| `LLM_API_KEY` | Language-model credentials |
| `LLM_MODEL` | Chat model selection |
| `LLM_BASE_URL` | LLM API endpoint |
| `EMBEDDING_BASE_URL` | Embedding API endpoint |
| `EMBEDDING_API_KEY` | Embedding service credentials |
| `EMBEDDING_MODEL` | Embedding model selection |

Use the actual names and defaults in the checked-in template and configuration as the source of truth. Do not commit secrets. Some workflows may require only a subset of these services, but live research and analysis should be tested with the providers they depend on.

### 5. Start the database services

```bash
docker compose up -d
```

This starts the services defined in the repository's Docker Compose configuration. Check the compose file and logs if a service fails to start.

### 6. Run offline tests

```bash
python -m pytest -q
```

The project guide documents 23 offline tests using simulated external services and SQLite. These tests are useful for application logic and API behaviour, but passing them does not verify live TinyFish credentials, LLM/embedding credentials, external response formats, or PostgreSQL deployment.

### 7. Start the API

```bash
uvicorn app.main:app --reload
```

Open the interactive API docs at [http://localhost:8000/docs](http://localhost:8000/docs). Use the docs to inspect available endpoints and request schemas for the version you are running.

## API workflow

The API supports a project-based research workflow.

### Research Analysis

1. Create a project with `POST /api/projects`.
2. Start research with `POST /api/projects/{id}/research`.
3. Poll `GET /api/jobs/{job_id}` to monitor progress.
4. Review the resulting similar projects, comparisons, sources, and opportunity hypotheses.

### Stakeholder Intelligence

1. Identify groups with `POST /api/projects/{id}/stakeholders/identify`.
2. Review and curate the suggested groups where appropriate.
3. Start analysis with `POST /api/projects/{id}/stakeholders/analyze`.
4. Monitor the job status.
5. Review stakeholder groups, needs, evidence, solution links, opportunities, and reports.

Documented job states include `pending`, `running`, `completed`, `completed_with_errors`, and `failed`. See the interactive API documentation and `GUIDE.md` for complete schemas and endpoint details.

## Configuration and tuning

The project documents the following initial limits and thresholds:

| Setting | Documented default | Purpose |
|---|---:|---|
| `MAX_SOURCES_PER_RUN` | 12 | Maximum sources processed per run |
| `MAX_QUERIES_PER_RUN` | 5 | Maximum search queries per run |
| `COMPARISON_TOP_K` | 5 | Number of projects selected for comparison |
| `FETCH_CACHE_DAYS` | 7 | Cache lifetime for fetched pages |
| `STRONG_SUPPORT_MIN_DOMAINS` | 3 | Independent domains required for strong support |
| `NEED_CLUSTER_THRESHOLD` | 0.80 | Similarity threshold for clustering needs |
| `LINK_THRESHOLD` | 0.55 | Similarity threshold for linking needs and features |

These are configuration starting points, not calibrated accuracy guarantees. Their usefulness depends on source coverage, data quality, model choice, and evaluation against representative examples.

## Verify live provider integrations

After the offline tests, run the checks described in `GUIDE.md`:

```bash
python -m scripts.check_tinyfish "student assignment manager app"
python -m scripts.check_llm
python -m scripts.demo_flow
```

Review the output and generated reports. If a check fails, investigate environment-variable names, authentication, quota, network access, and response-format changes before debugging downstream analysis.

## Limitations and evidence integrity

- Live provider integrations must be tested with real credentials before they can be called verified.
- Background jobs are not resumable after a server interruption.
- The current backend does not provide authentication or per-user access control.
- Matching an extracted excerpt to page text does not independently prove that the excerpt supports the associated claim.
- Domain-based evidence independence is approximate and may not detect copied or republished material.
- Similarity weights and thresholds need evaluation against labelled examples.
- Public-web evidence may not adequately represent the prevalence of a stakeholder need.
- Database migrations should be introduced as the data model stabilizes.
- Search results are limited by the sources found, their accessibility, and the configured provider limits.

Use findings to guide investigation and prioritization—not as proof of originality, guaranteed demand, or product success.

## Related documentation

- [Frontend repository](https://github.com/avnipahal624/Bulidscope_frontend)
- [Backend setup and development guide](GUIDE.md)

## License

No license is specified here. Review the repository's licensing terms before redistributing or reusing the code.
