"""Eval dataset aggregator — all test cases from all sources."""

import json
from copy import replace
from pathlib import Path

from evals.dataset.schema import TestCase
from evals.dataset.hotpotqa import HOTPOTQA_CASES
from evals.dataset.nq import NQ_CASES
from evals.dataset.squad import SQUAD_CASES
from evals.dataset.curated import CURATED_CASES

_ENRICHMENT_FILE = Path(__file__).parent / "enrichment.json"

# Load pre-computed enrichment data if available (produced by enrich_dataset.py)
_ENRICHMENT: dict = {}
if _ENRICHMENT_FILE.exists():
    try:
        _ENRICHMENT = json.loads(_ENRICHMENT_FILE.read_text())
    except Exception:
        pass


def _apply_enrichment(cases: list[TestCase]) -> list[TestCase]:
    """Merge pre-computed fact_in_retrieved_window / fact_in_full_article into cases."""
    if not _ENRICHMENT:
        return cases
    enriched = []
    for c in cases:
        entry = _ENRICHMENT.get(c.id)
        if entry:
            c = replace(
                c,
                fact_in_retrieved_window=entry.get("fact_in_retrieved_window"),
                fact_in_full_article=entry.get("fact_in_full_article"),
            )
        enriched.append(c)
    return enriched


ALL_CASES: list[TestCase] = _apply_enrichment(
    HOTPOTQA_CASES + NQ_CASES + SQUAD_CASES + CURATED_CASES
)


def load_dataset(
    sources: list[str] | None = None,
    categories: list[str] | None = None,
    retrievability: list[str] | None = None,
) -> list[TestCase]:
    """Return test cases, optionally filtered.

    sources: e.g. ["hotpotqa", "nq", "squad", "curated"]
    categories: e.g. ["hotpotqa_bridge", "misconception", "prompt_injection"]
    retrievability: e.g. ["direct", "strategic", "out_of_reach"]
    """
    cases = ALL_CASES
    if sources:
        cases = [c for c in cases if c.source in sources]
    if categories:
        cases = [c for c in cases if c.category in categories]
    if retrievability:
        cases = [c for c in cases if c.retrievability in retrievability]
    return cases


def dataset_summary() -> dict:
    from collections import Counter
    enriched = sum(1 for c in ALL_CASES if c.fact_in_retrieved_window is not None)
    return {
        "total": len(ALL_CASES),
        "by_source": dict(Counter(c.source for c in ALL_CASES)),
        "by_category": dict(Counter(c.category for c in ALL_CASES)),
        "by_retrievability": dict(Counter(c.retrievability for c in ALL_CASES)),
        "requires_multihop": sum(1 for c in ALL_CASES if c.requires_multihop),
        "enriched_cases": enriched,
    }
