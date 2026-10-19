import httpx
import pytest

from app.config import get_settings
from app.llm.client import LLMClient, LLMError
from app.llm.schemas import QueryList
from app.research.adapter import TinyFishAdapter
from app.research.cleaning import (excerpt_in_text, is_grounded, near_duplicate, normalize_url,
                                   registered_domain)
from app.research.safety import is_safe_url
from app.research.similarity import cosine, list_overlap
from app.stakeholders.strength import assess_strength


# ---------------------------------------------------------------- URL / text
def test_normalize_url_strips_tracking_fragment_and_slash():
    a = normalize_url("HTTPS://Example.com/path/?utm_source=x&b=2&a=1#frag")
    b = normalize_url("https://example.com/path?a=1&b=2")
    assert a == b


def test_registered_domain():
    assert registered_domain("https://www.reddit.com/r/x") == "reddit.com"
    assert registered_domain("https://blog.example.co.uk/a") == "example.co.uk"


def test_excerpt_matching_handles_quotes_and_markdown():
    page = "He said **I can\u2019t tell which assignment to do first** and left [more](http://x.com)."
    assert excerpt_in_text("I can't tell which assignment to do first", page)
    assert not excerpt_in_text("Students always know which assignment to do first", page)
    assert not excerpt_in_text("too short", "too short")


def test_is_grounded_rejects_invented_feature():
    page = "The app sends reminders before deadlines."
    assert is_grounded("sends reminders before deadlines", page)
    assert not is_grounded("blockchain based plagiarism detection", page)


def test_near_duplicate():
    base = " ".join(f"token{i}" for i in range(300))
    assert near_duplicate(base + " alpha", base + " beta")
    assert not near_duplicate(base, " ".join(f"other{i}" for i in range(300)))


# ------------------------------------------------------------------- safety
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/",
    "ftp://example.com/file", "file:///etc/passwd", "http://localhost:8000/", "https://user:pw@example.com/",
])
def test_unsafe_urls_rejected(url):
    ok, _ = is_safe_url(url)
    assert not ok


def test_public_url_accepted():
    ok, _ = is_safe_url("https://example.com/", resolve=lambda h: ["93.184.216.34"])
    assert ok


# ----------------------------------------------------------------- strength
def test_strength_statuses():
    min_d = 3
    assert assess_strength([], min_d).status == "unverified"
    one = [("supports", "quote one is long enough", "https://a.com/1")]
    assert assess_strength(one, min_d).status == "supported"
    three = one + [("supports", "quote two is long enough", "https://b.com/1"),
                   ("supports", "quote three is long enough", "https://c.org/1")]
    s = assess_strength(three, min_d)
    assert s.status == "strongly_supported" and s.need_type == "pattern"
    conflict = three + [("contradicts", "I disagree strongly here", "https://d.com/1")]
    assert assess_strength(conflict, min_d).status == "conflicting"
    assert assess_strength([("contradicts", "I disagree strongly here", "https://d.com/1")],
                           min_d).status == "needs_further_research"


def test_copies_and_same_domain_do_not_inflate_strength():
    copied = [("supports", "Exactly the same sentence here", "https://a.com/1"),
              ("supports", "Exactly the same sentence here", "https://b.com/2"),
              ("supports", "Exactly the same sentence here", "https://c.com/3")]
    assert assess_strength(copied, 3).status == "supported"          # copies count once
    same_site = [("supports", f"different quote number {i} here", f"https://reddit.com/r/x/{i}")
                 for i in range(5)]
    s = assess_strength(same_site, 3)
    assert s.status == "supported" and s.independent_sources == 1


def test_list_overlap_and_cosine():
    assert list_overlap([], ["a"]) is None
    assert list_overlap(["due date reminders"], ["reminders for due dates"]) > 0
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)


# ------------------------------------------------------------ HTTP clients
def _llm_with(handler):
    s = get_settings()
    c = LLMClient(s, httpx.Client(transport=httpx.MockTransport(handler)))
    c._sleep = lambda _: None
    return c


def test_llm_retries_on_invalid_json_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        content = "not json" if calls["n"] == 1 else '```json\n{"queries": ["a b c"]}\n```'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 2}})

    out = _llm_with(handler)
    result = out.complete_json("sys", "user", QueryList)
    assert result.queries == ["a b c"] and calls["n"] == 2
    assert out.usage["prompt_tokens"] == 10


def test_llm_gives_up_after_retries():
    llm = _llm_with(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "{bad"}}]}))
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", QueryList, retries=1)


def test_tinyfish_adapter_parses_search_and_fetch():
    def handler(request):
        assert request.headers["X-API-Key"] == "test"
        if request.method == "GET":
            return httpx.Response(200, json={"results": [
                {"position": 1, "title": "T", "url": "https://a.com", "snippet": "S"}]})
        return httpx.Response(200, json={
            "results": [{"url": "https://a.com", "text": "hello page"}],
            "errors": [{"url": "https://b.com", "error": "blocked"}]})

    a = TinyFishAdapter(get_settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    hits = a.search("q")
    assert hits[0].url == "https://a.com" and hits[0].snippet == "S"
    pages, failures = a.fetch(["https://a.com", "https://b.com", "https://c.com"])
    assert [p.url for p in pages] == ["https://a.com"]
    assert {f.url for f in failures} == {"https://b.com", "https://c.com"}   # c silently missing
