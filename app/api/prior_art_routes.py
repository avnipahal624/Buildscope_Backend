from datetime import datetime, timezone
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/prior-art", tags=["prior-art"])

class RepositorySearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)

@router.post("/repositories")
async def search_repositories(body: RepositorySearchRequest):
    """Search public GitHub repositories. Results are live public metadata, not a patent/legal search."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "BuildScope-AI-Prior-Art-Lab",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": body.query, "sort": "stars", "order": "desc", "per_page": body.limit},
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="GitHub search could not be reached. Try again later.") from exc

    if response.status_code == 403 or response.status_code == 429:
        raise HTTPException(status_code=503, detail="GitHub search rate limit reached. Try again later.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"GitHub search returned HTTP {response.status_code}.")

    payload = response.json()
    items = []
    for repo in payload.get("items", []):
        items.append({
            "id": str(repo.get("id", "")),
            "source": "github",
            "name": repo.get("name", ""),
            "owner": (repo.get("owner") or {}).get("login", ""),
            "description": repo.get("description") or "",
            "url": repo.get("html_url", ""),
            "language": repo.get("language") or "Unknown",
            "topics": repo.get("topics") or [],
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "lastUpdated": repo.get("updated_at") or "",
            "licence": ((repo.get("license") or {}).get("spdx_id") or "Unknown"),
            "retrieval": "live",
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "limitations": "Public GitHub repository metadata only; this is not a patent database or legal novelty assessment.",
        })
    return {
        "provider": "GitHub REST API",
        "retrieval": "live",
        "query": body.query,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "totalCount": payload.get("total_count", 0),
        "items": items,
        "limitations": ["Public repositories only", "GitHub search is not a patent database", "Repository metadata does not prove novelty or freedom to operate"],
    }
