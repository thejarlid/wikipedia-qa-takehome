#!/usr/bin/env python3
"""Pre-compute fact_in_retrieved_window and fact_in_full_article for each TestCase.

Fetches the full Wikipedia article (no word limit) for each case's supporting
articles and checks whether key_facts appear in:
  - The first 1000 words (the retrieval window our tool uses)
  - The full article

Results are stored in evals/dataset/enrichment.json, keyed by case_id.
The diagnostic check in checks.py reads this file to make exact determinations
for States B vs C (cutoff limitation vs retrieval failure).

Run once after building or modifying the dataset:
  python scripts/enrich_dataset.py

Re-run after changing key_facts or supporting_articles for any case.
"""

import json
import re
import sys
import time
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from dotenv import load_dotenv

load_dotenv()

from evals.dataset import load_dataset

ENRICHMENT_FILE = Path(__file__).parent.parent / "evals" / "dataset" / "enrichment.json"
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"

_session = requests.Session()
_session.headers["User-Agent"] = (
    "WikipediaQA-DatasetEnricher/1.0 "
    "(Anthropic take-home; dataset pre-computation)"
)


def fetch_full_article(title: str) -> str | None:
    """Fetch the complete plain-text extract of a Wikipedia article (no word limit).
    Retries with exponential backoff on 429 / 5xx.
    """
    delays = [2, 5, 15, 30]
    for attempt, wait in enumerate(delays):
        try:
            resp = _session.get(MEDIAWIKI_API, params={
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "titles": title,
                "redirects": 1,
                "format": "json",
            }, timeout=20)
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"\n    rate-limited, waiting {wait}s...", end="", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            pages = resp.json()["query"]["pages"]
            page = next(iter(pages.values()))
            return page.get("extract") or None
        except requests.exceptions.RequestException as e:
            if attempt < len(delays) - 1:
                print(f"\n    network error ({e}), retrying in {wait}s...", end="", flush=True)
                time.sleep(wait)
            else:
                print(f"\n  WARNING: could not fetch '{title}' after {len(delays)} attempts")
                return None
    return None


def words_up_to(text: str, limit: int) -> str:
    """Return the first `limit` words of text, matching our tool's retrieval window."""
    words = re.split(r"\s+", text.strip())
    return " ".join(words[:limit])


def check_facts_in_text(key_facts: list[str], text: str) -> bool:
    """Return True if any key fact appears (case-insensitive) in the text."""
    text_lower = text.lower()
    return any(f.lower() in text_lower for f in key_facts)


def enrich(cases, existing: dict) -> dict:
    results = dict(existing)  # preserve already-computed entries
    total = len(cases)

    for i, case in enumerate(cases, 1):
        # Skip cases with no key_facts or no supporting_articles to check
        if not case.key_facts or not case.supporting_articles:
            continue

        # Skip if already enriched (don't re-fetch unless forced)
        if case.id in results:
            print(f"[{i:2}/{total}] {case.id:8} already enriched, skipping")
            continue

        print(f"[{i:2}/{total}] {case.id:8} checking '{case.supporting_articles[0]}'...", end="", flush=True)

        in_window = False
        in_full = False

        for article_title in case.supporting_articles:
            full_text = fetch_full_article(article_title)
            if not full_text:
                continue

            window_text = words_up_to(full_text, 1000)

            if check_facts_in_text(case.key_facts, window_text):
                in_window = True
                in_full = True
                break

            if check_facts_in_text(case.key_facts, full_text):
                in_full = True
                # in_window stays False — fact is in article but beyond 1000 words

            time.sleep(1.5)  # be polite to Wikipedia — full article fetches are heavier

        results[case.id] = {
            "fact_in_retrieved_window": in_window,
            "fact_in_full_article": in_full,
            "supporting_articles_checked": case.supporting_articles,
            "key_facts_checked": case.key_facts,
        }

        status = (
            "✅ in window" if in_window
            else "⚠  beyond cutoff" if in_full
            else "❌ not in article"
        )
        print(f" {status}")

    return results


def main():
    cases = load_dataset()
    eligible = [c for c in cases if c.key_facts and c.supporting_articles]
    print(f"Cases with key_facts + supporting_articles: {len(eligible)} / {len(cases)}")
    print()

    existing = {}
    if ENRICHMENT_FILE.exists():
        existing = json.loads(ENRICHMENT_FILE.read_text())
        print(f"Loaded {len(existing)} existing enrichment entries\n")

    results = enrich(eligible, existing)

    ENRICHMENT_FILE.parent.mkdir(exist_ok=True)
    ENRICHMENT_FILE.write_text(json.dumps(results, indent=2))
    print(f"\nEnrichment data saved to: {ENRICHMENT_FILE}")

    # Summary
    in_window = sum(1 for v in results.values() if v["fact_in_retrieved_window"])
    in_full = sum(1 for v in results.values() if v["fact_in_full_article"])
    beyond = sum(1 for v in results.values() if v["fact_in_full_article"] and not v["fact_in_retrieved_window"])
    not_found = sum(1 for v in results.values() if not v["fact_in_full_article"])
    print(f"\nSummary:")
    print(f"  In 1000-word window:  {in_window}")
    print(f"  Beyond cutoff (in full article): {beyond}")
    print(f"  Not in Wikipedia at all: {not_found}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich dataset with fact retrievability metadata")
    parser.add_argument("--force", action="store_true", help="Re-compute all cases, ignoring existing entries")
    args = parser.parse_args()

    if args.force:
        print("--force: re-computing all cases\n")
        # Clear existing so enrich() re-computes everything
        cases = load_dataset()
        eligible = [c for c in cases if c.key_facts and c.supporting_articles]
        results = enrich(eligible, {})
    else:
        main()
        sys.exit(0)

    ENRICHMENT_FILE.write_text(json.dumps(results, indent=2))
    print(f"\nEnrichment data saved to: {ENRICHMENT_FILE}")
