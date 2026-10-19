"""Shared fakes. No network, no API keys, no Postgres needed to run the tests."""
import math
import os
import re
import zlib

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["LINK_THRESHOLD"] = "0.5"
os.environ["LLM_API_KEY"] = "test"
os.environ["TINYFISH_API_KEY"] = "test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app import db as database
from app import deps
from app.config import get_settings
from app.research import safety
from app.research.adapter import FetchedPage, FetchFailure, SearchHit

get_settings.cache_clear()


class FakeLLM:
    """Returns canned structured answers; embeddings are hashed bag-of-words vectors."""
    model = "fake-llm"

    def __init__(self):
        self.usage = {"llm_calls": 0}
        self.handlers = {}

    def complete_json(self, system, user, schema, retries=1):
        self.usage["llm_calls"] += 1
        handler = self.handlers.get(schema.__name__)
        assert handler, f"no fake handler for {schema.__name__}"
        return handler(user)

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 256
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                v[zlib.crc32(w.encode()) % 256] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class FakeAdapter:
    def __init__(self, pages, search_fn):
        self.pages, self.search_fn = pages, search_fn
        self.fetch_calls = 0

    def search(self, query):
        return [SearchHit(url=u, title=u) for u in self.search_fn(query)]

    def fetch(self, urls):
        self.fetch_calls += 1
        ok, bad = [], []
        for u in urls:
            if u in self.pages:
                ok.append(FetchedPage(url=u, text=self.pages[u]))
            else:
                bad.append(FetchFailure(u, "404"))
        return ok, bad


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    """Pretend every hostname resolves to a public IP."""
    import ipaddress

    def fake(host):
        try:
            ipaddress.ip_address(host)
            return [host]                      # IP literals resolve to themselves, as in real life
        except ValueError:
            return ["93.184.216.34"]

    monkeypatch.setattr(safety, "resolve_host", fake)


@pytest.fixture()
def fresh_db():
    database.configure("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    database.init_db()
    yield


@pytest.fixture()
def client(fresh_db):
    from app.main import app
    with TestClient(app) as c:
        yield c
