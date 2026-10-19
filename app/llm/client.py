"""One wrapper around an OpenAI-compatible LLM + embeddings API.

complete_json(system, user, SomePydanticModel) -> validated model instance.
We ask for a JSON object, validate it with Pydantic, and retry once with the
validation error if the output is malformed. Schema compliance does NOT mean the
content is true: callers still verify excerpts against the source text.

Rate limits: calls are spaced by LLM_MIN_INTERVAL_SECONDS, and 429/5xx replies are retried
with long waits (honouring Retry-After). A *daily* quota error stops immediately because
waiting a minute cannot fix it.
"""
import json
import re
import time
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel

from app.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)

BACKOFF_SECONDS = [10, 20, 40, 60, 60]


class LLMError(RuntimeError):
    pass


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    return m.group(1) if m else text


def _looks_like_daily_quota(body: str) -> bool:
    b = body.lower().replace("_", "").replace(" ", "")
    return "perday" in b or "dailylimit" in b or "requestsperday" in b


class LLMClient:
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.s = settings or get_settings()
        self.http = client or httpx.Client(timeout=120)
        self.model = self.s.llm_model
        self._sleep = time.sleep
        self._last_call = 0.0
        self.usage = {
            "llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "embedding_calls": 0, "embedding_tokens": 0, "rate_limit_waits": 0,
        }

    # ------------------------------------------------------------------ HTTP
    def _throttle(self):
        gap = self.s.llm_min_interval_seconds
        if gap > 0 and self._last_call:
            wait = gap - (time.monotonic() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = time.monotonic()

    def _post(self, base: str, key: str, path: str, payload: dict) -> dict:
        if not key:
            raise LLMError("LLM API key is not configured (set LLM_API_KEY in .env)")
        url = base.rstrip("/") + path
        last = "request failed"
        attempts = max(1, self.s.llm_max_attempts)
        for attempt in range(attempts):
            self._throttle()
            try:
                r = self.http.post(url, json=payload, headers={"Authorization": f"Bearer {key}"})
            except httpx.HTTPError as e:           # network problem: retry
                last = f"network error: {e}"
                self._sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                continue
            if r.status_code == 429 and _looks_like_daily_quota(r.text):
                raise LLMError("DAILY quota exhausted for this model/key. Waiting will not help "
                               "until it resets; try a different model or provider. "
                               f"Provider said: {r.text[:400]}")
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}: {r.text[:400]}"
                if attempt == attempts - 1:
                    break
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                retry_after = r.headers.get("retry-after", "")
                if retry_after.isdigit():
                    wait = max(wait, min(int(retry_after), 120))
                self.usage["rate_limit_waits"] += 1
                self._sleep(wait)
                continue
            if r.status_code >= 400:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:500]}")
            return r.json()
        raise LLMError(last)

    # ------------------------------------------------------------ completions
    def complete_json(self, system: str, user: str, schema: Type[T], retries: int = 1) -> T:
        schema_text = json.dumps(schema.model_json_schema())
        full_system = (
            system
            + "\n\nReturn ONLY one JSON object that conforms to this JSON Schema "
              "(no markdown fences, no commentary):\n" + schema_text
        )
        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user},
        ]
        last_error = ""
        for _ in range(retries + 1):
            data = self._post(
                self.s.llm_base_url, self.s.llm_api_key, "/chat/completions",
                {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            self.usage["llm_calls"] += 1
            u = data.get("usage") or {}
            self.usage["prompt_tokens"] += u.get("prompt_tokens", 0)
            self.usage["completion_tokens"] += u.get("completion_tokens", 0)
            content = data["choices"][0]["message"]["content"] or ""
            try:
                return schema.model_validate_json(_strip_fences(content))
            except ValueError as e:                # includes pydantic ValidationError
                last_error = str(e)[:500]
                messages += [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"That JSON was invalid: {last_error}. "
                                                "Return corrected JSON only."},
                ]
        raise LLMError(f"model returned invalid JSON after retries: {last_error}")

    # -------------------------------------------------------------- embeddings
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        base = self.s.embedding_base_url or self.s.llm_base_url
        key = self.s.embedding_api_key or self.s.llm_api_key
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            batch = [t[:8000] for t in texts[i:i + 64]]
            data = self._post(base, key, "/embeddings",
                              {"model": self.s.embedding_model, "input": batch})
            self.usage["embedding_calls"] += 1
            self.usage["embedding_tokens"] += (data.get("usage") or {}).get("total_tokens", 0)
            items = data["data"]
            if all("index" in d for d in items):       # OpenAI sends an index; Gemini does not
                items = sorted(items, key=lambda d: d["index"])
            if len(items) != len(batch):
                raise LLMError(f"embedding count mismatch: sent {len(batch)}, got {len(items)}")
            out.extend(d["embedding"] for d in items)
        return out
