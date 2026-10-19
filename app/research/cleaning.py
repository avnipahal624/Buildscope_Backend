"""URL normalisation, source classification, text cleaning and duplicate detection."""
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_EXACT = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "igshid"}
_TWO_PART_TLDS = {"co.uk", "org.uk", "ac.uk", "com.au", "co.in", "ac.in", "co.jp", "com.br", "co.nz"}

SKIP_DOMAINS = {"youtube.com", "youtu.be", "facebook.com", "instagram.com", "tiktok.com", "pinterest.com"}


def normalize_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
        scheme = p.scheme.lower()
        host = (p.hostname or "").lower()
        netloc = host
        if p.port and not ((scheme == "http" and p.port == 80) or (scheme == "https" and p.port == 443)):
            netloc = f"{host}:{p.port}"
    except ValueError:
        return url.strip()
    path = p.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_EXACT]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def registered_domain(url: str) -> str:
    """Rough 'who owns this site' key, used to judge source independence."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2 or all(p.isdigit() for p in parts):
        return host
    if ".".join(parts[-2:]) in _TWO_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def classify_source(url: str) -> str:
    d = registered_domain(url)
    if d in ("github.com", "gitlab.com", "bitbucket.org"):
        return "repository"
    if d == "devpost.com":
        return "hackathon_project"
    if d in ("arxiv.org", "doi.org", "semanticscholar.org", "researchgate.net", "acm.org", "ieee.org"):
        return "paper"
    if d in ("reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com", "ycombinator.com"):
        return "forum"
    if d in ("trustpilot.com", "g2.com", "capterra.com", "apple.com", "play.google.com"):
        return "review"
    if d == "producthunt.com":
        return "product_listing"
    return "website"


def should_skip_domain(url: str) -> bool:
    return registered_domain(url) in SKIP_DOMAINS


def clean_text(text: str, max_chars: int = 200_000) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)       # markdown images
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:max_chars]


def normalize_for_match(text: str) -> str:
    """Normalise text so quotes/markdown/whitespace differences don't break excerpt matching."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)         # [label](url) -> label
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u00a0", " ")):
        t = t.replace(a, b)
    t = re.sub(r"[*_`#>\[\]]", "", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def excerpt_in_text(excerpt: str | None, text: str, min_len: int = 20) -> bool:
    """True only if the excerpt really appears (after normalisation) in the page text.

    This is the cheap anti-hallucination check. Ellipses split the excerpt into segments;
    every substantial segment must appear.
    """
    if not excerpt:
        return False
    haystack = normalize_for_match(text)
    segments = [s.strip() for s in re.split(r"\.\.\.|\u2026", normalize_for_match(excerpt)) if s.strip()]
    substantial = [s for s in segments if len(s) >= 10]
    if not substantial or max(len(s) for s in substantial) < min_len:
        return False
    return all(s in haystack for s in substantial)


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_for_match(text).encode("utf-8")).hexdigest()


def _shingles(text: str, n: int = 5) -> set[str]:
    words = normalize_for_match(text)[:4000].split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def near_duplicate(a: str, b: str, threshold: float = 0.9) -> bool:
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return False
    return len(sa & sb) / len(sa | sb) >= threshold


_STOP = {"the", "and", "for", "with", "that", "this", "from", "have", "are", "was", "not", "but",
         "can", "you", "your", "all", "any", "has", "its", "into", "per", "via", "our", "their"}


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP}


def is_grounded(statement: str, page_text: str, min_ratio: float = 0.6) -> bool:
    """Cheap check that a claimed feature/limitation uses words that appear on the page."""
    words = content_words(statement)
    if not words:
        return False
    page_words = content_words(page_text)
    return len(words & page_words) / len(words) >= min_ratio
