"""Wikipedia search via the MediaWiki API."""

import re
import time
import urllib.parse

import requests

MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
EXTRACT_WORD_LIMIT = 1000

_RETRY_BACKOFF = [1.0, 2.0, 4.0]  # seconds to wait before each retry
_MAX_RETRIES = len(_RETRY_BACKOFF)

_session = requests.Session()
# Wikipedia requires a descriptive User-Agent; without one they rate-limit aggressively
_session.headers["User-Agent"] = (
    "WikipediaQA-ResearchAgent/1.0 "
    "(Anthropic take-home project; https://github.com/dilrajsinghdevgun)"
)


def search_wikipedia(query: str) -> dict:
    """Search Wikipedia and return the best-matching article's content.

    Returns a dict with keys: title, content, url
    — or {"error": "<message>"} if nothing was found or all retries failed.
    """
    try:
        title = _find_best_title(query)
    except Exception as exc:
        return {"error": f"Wikipedia search failed for {query!r}: {exc}"}

    if title is None:
        return {"error": f"No Wikipedia article found for: {query!r}"}

    try:
        content = _fetch_extract(title)
    except Exception as exc:
        return {"error": f"Could not retrieve Wikipedia article {title!r}: {exc}"}

    if not content:
        return {"error": f"Wikipedia article {title!r} has no extractable content"}

    return {
        "title": title,
        "content": _truncate_to_words(content, EXTRACT_WORD_LIMIT),
        "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
    }


def _get(params: dict) -> requests.Response:
    """GET with retry logic and exponential backoff on 429 / 5xx."""
    for attempt, wait in enumerate(_RETRY_BACKOFF):
        resp = _session.get(MEDIAWIKI_API, params=params, timeout=15)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
                continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()  # final attempt exhausted
    return resp  # unreachable but satisfies type checker


def _find_best_title(query: str) -> str | None:
    """Return the best Wikipedia article title for a query.

    Tries direct page resolution (handles redirects) first, falls back to search.
    """
    resp = _get({
        "action": "query",
        "titles": query,
        "redirects": 1,
        "format": "json",
    })
    pages = resp.json()["query"]["pages"]
    page = next(iter(pages.values()))
    if "missing" not in page:
        return page["title"]

    resp = _get({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 1,
        "srinfo": "",
        "srprop": "titlesnippet",
        "format": "json",
    })
    results = resp.json()["query"]["search"]
    return results[0]["title"] if results else None


def _fetch_extract(title: str) -> str | None:
    """Fetch the plain-text intro extract for a Wikipedia article."""
    resp = _get({
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "titles": title,
        "redirects": 1,
        "format": "json",
    })
    pages = resp.json()["query"]["pages"]
    page = next(iter(pages.values()))
    return page.get("extract") or None


def _truncate_to_words(text: str, limit: int) -> str:
    words = re.split(r"\s+", text.strip())
    if len(words) <= limit:
        return text.strip()
    return " ".join(words[:limit]) + " [...]"
