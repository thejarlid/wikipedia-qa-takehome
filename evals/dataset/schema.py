"""TestCase schema for the Wikipedia QA eval suite."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestCase:
    id: str
    question: str

    category: str
    """hotpotqa_bridge | hotpotqa_comparison | nq_factual | squad_false_premise |
    out_of_scope | misconception | false_premise | disambiguation | prompt_injection |
    jargon_obfuscation"""

    expected_answer: str
    """Short answer for deterministic matching. Empty string for out-of-scope cases
    where the correct behaviour is a decline."""

    key_facts: list[str] = field(default_factory=list)
    """Substrings that should appear in the answer (case-insensitive).
    Empty for out-of-scope cases."""

    supporting_articles: list[str] = field(default_factory=list)
    """Wikipedia article titles the agent is expected to search, in hop order."""

    requires_multihop: bool = False
    """True when answering requires chaining two or more Wikipedia lookups."""

    retrievability: str = "direct"
    """direct     – answer is in the first ~1000 words of the right article.
    strategic   – requires finding the correct specific article or multi-hop chain.
    out_of_reach – answer exists in Wikipedia but beyond the tool's retrieval window,
                   OR the subject has no Wikipedia article. Success criteria differ."""

    adversarial_type: str | None = None
    """out_of_scope | misconception | false_premise | disambiguation |
    prompt_injection | jargon_obfuscation — or None for standard cases."""

    adversarial_claim: str | None = None
    """The false claim that must NOT be confirmed in the answer.
    Used for misconception and false_premise cases."""

    notes: str = ""
    """What this case tests and why it is interesting."""

    source: str = "curated"
    """curated | hotpotqa | nq | squad"""

    # Pre-computed by scripts/enrich_dataset.py — None until that script is run.
    fact_in_retrieved_window: bool | None = None
    """True if any key_fact appears in the first ~1000 words of the expected
    supporting article(s). Populated at dataset-build time, not eval time."""

    fact_in_full_article: bool | None = None
    """True if any key_fact appears anywhere in the full Wikipedia article
    (beyond the 1000-word retrieval window). Populated at dataset-build time."""
