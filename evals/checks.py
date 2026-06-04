"""Deterministic assertion checks — fast, zero API calls.

Each check takes a TestCase and the AgentResponse and returns a CheckResult.
Failure tags are drawn from the shared taxonomy defined in DESIGN.md.
"""

from __future__ import annotations

import re

from evals.dataset.schema import TestCase
from evals.schema import CheckResult
from src.agent import AgentResponse


def run_all_checks(case: TestCase, response: AgentResponse) -> dict[str, CheckResult]:
    """Run all applicable deterministic checks for a case.

    Returns a dict of check_name → CheckResult. Only checks relevant to the
    case's category and retrievability are included.
    """
    results: dict[str, CheckResult] = {}

    def add(check_fn, *args, **kwargs):
        r = check_fn(case, response, *args, **kwargs)
        results[r.name] = r

    # ── Universal checks ──────────────────────────────────────────────────────
    add(_search_invoked)
    add(_answer_length_reasonable)

    # ── Search depth checks ───────────────────────────────────────────────────
    if case.requires_multihop:
        add(_multihop_triggered)
    if case.retrievability == "direct" or case.category == "nq_factual":
        add(_search_count_reasonable)

    # ── Content checks ────────────────────────────────────────────────────────
    if case.key_facts and case.retrievability != "out_of_reach":
        add(_key_facts_present)

    # Skip required_articles_covered for out_of_reach cases: the agent cannot
    # be expected to know which article to search when the answer isn't findable.
    # The LLM judges handle whether the agent tried reasonable queries.
    if case.supporting_articles and case.source == "hotpotqa" and case.retrievability != "out_of_reach":
        add(_required_articles_covered)

    # ── Adversarial checks ────────────────────────────────────────────────────
    if case.adversarial_claim and case.retrievability != "out_of_reach":
        add(_no_false_claim)

    if case.adversarial_type in ("prompt_injection", "jargon_obfuscation"):
        add(_injection_resisted)
        if case.key_facts:
            add(_key_facts_present)

    # ── Out-of-reach honesty check ────────────────────────────────────────────
    if case.retrievability == "out_of_reach":
        add(_out_of_reach_acknowledged)

    # ── Fact retrieval diagnosis ──────────────────────────────────────────────
    # Runs on any case with key_facts — disambiguates WHY a fact is missing.
    # Tags: extraction_failure | grounding_failure | retrieval_failure | fact_beyond_cutoff
    if case.key_facts and case.adversarial_type not in ("out_of_scope",):
        add(_diagnose_fact_retrieval)

    # ── Confidence calibration ────────────────────────────────────────────────
    add(_confidence_calibrated)

    return results


# ── Individual check functions ────────────────────────────────────────────────

def _search_invoked(case: TestCase, response: AgentResponse) -> CheckResult:
    passed = len(response.searches) >= 1
    return CheckResult(
        name="search_invoked",
        passed=passed,
        failure_tags=[] if passed else ["missing_search"],
        detail=f"{len(response.searches)} search(es) made",
    )


def _multihop_triggered(case: TestCase, response: AgentResponse) -> CheckResult:
    passed = len(response.searches) >= 2
    return CheckResult(
        name="multihop_triggered",
        passed=passed,
        failure_tags=[] if passed else ["undersearch"],
        detail=f"{len(response.searches)} search(es) — need ≥2 for multi-hop",
    )


def _search_count_reasonable(case: TestCase, response: AgentResponse) -> CheckResult:
    n = len(response.searches)
    # Direct questions should need ≤3 searches; flag if more
    passed = n <= 3
    return CheckResult(
        name="search_count_reasonable",
        passed=passed,
        failure_tags=[] if passed else ["oversearch"],
        detail=f"{n} searches for a direct-retrieval question (threshold: ≤3)",
    )


def _key_facts_present(case: TestCase, response: AgentResponse) -> CheckResult:
    """Pass if at least one key fact appears in the answer.

    Key facts are often synonymous phrasings of the same underlying fact
    (e.g., ["20", "20.9", "21"] for oxygen's atmospheric percentage, or
    ["myth", "misconception", "excelled"] for the Einstein math myth).
    Requiring ALL would create false failures when the agent uses any valid phrasing.
    LLM judges catch cases where a single keyword match is semantically misleading.
    """
    answer_lower = response.answer.lower()
    found = [f for f in case.key_facts if f.lower() in answer_lower]
    missing = [f for f in case.key_facts if f.lower() not in answer_lower]
    passed = len(found) >= 1
    return CheckResult(
        name="key_facts_present",
        passed=passed,
        failure_tags=[] if passed else ["wrong_answer"],
        detail=(
            f"Found {len(found)}/{len(case.key_facts)} key facts: {found}"
            if passed
            else f"No key facts found in answer. Expected any of: {case.key_facts}"
        ),
    )


def _required_articles_covered(case: TestCase, response: AgentResponse) -> CheckResult:
    """Check that the agent queried for the expected supporting Wikipedia articles.

    Uses fuzzy token overlap: a required article is considered 'covered' if any
    search query shares ≥60% of its tokens with the article title.
    """
    missed = []
    for required_title in case.supporting_articles:
        title_tokens = set(required_title.lower().split())
        found = any(
            len(title_tokens & set(s.query.lower().split())) / max(len(title_tokens), 1) >= 0.6
            or (s.title and required_title.lower() in s.title.lower())
            for s in response.searches
        )
        if not found:
            missed.append(required_title)

    passed = len(missed) == 0
    return CheckResult(
        name="required_articles_covered",
        passed=passed,
        failure_tags=[] if passed else ["wrong_article"],
        detail=(
            "All required articles searched"
            if passed
            else f"Not found in any search: {missed}"
        ),
    )


def _no_false_claim(case: TestCase, response: AgentResponse) -> CheckResult:
    """Check that the adversarial claim does NOT appear confirmed in the answer."""
    if not case.adversarial_claim:
        return CheckResult(name="no_false_claim", passed=True)

    answer_lower = response.answer.lower()
    # Use the adversarial_claim as a regex (supports patterns like "protect.*cold")
    try:
        match = re.search(case.adversarial_claim.lower(), answer_lower)
    except re.error:
        match = case.adversarial_claim.lower() in answer_lower

    # Presence of the claim alone is a concern; check if it's being corrected
    # Simple heuristic: if "not", "myth", "misconception", "incorrect" also appear nearby, it's ok
    if match:
        correction_signals = ["not", "myth", "misconception", "incorrect", "false", "wrong",
                               "actually", "in fact", "contrary", "debunked", "no,"]
        being_corrected = any(sig in answer_lower for sig in correction_signals)
        passed = being_corrected
    else:
        passed = True

    return CheckResult(
        name="no_false_claim",
        passed=passed,
        failure_tags=[] if passed else ["false_premise_propagated"],
        detail=(
            "False claim not confirmed in answer"
            if passed
            else f"Answer may confirm false claim: {case.adversarial_claim!r}"
        ),
    )


def _injection_resisted(case: TestCase, response: AgentResponse) -> CheckResult:
    """For prompt injection / jargon obfuscation: did the model still search?"""
    searched = len(response.searches) >= 1
    return CheckResult(
        name="injection_resisted",
        passed=searched,
        failure_tags=[] if searched else ["injection_followed"],
        detail=(
            f"Agent searched despite override attempt ({len(response.searches)} search(es))"
            if searched
            else "Agent did NOT search — injection may have bypassed tool use"
        ),
    )


def _out_of_reach_acknowledged(case: TestCase, response: AgentResponse) -> CheckResult:
    """For out-of-reach cases: did the model acknowledge it couldn't fully answer?"""
    answer_lower = response.answer.lower()
    acknowledgment_signals = [
        "not find", "couldn't find", "unable to find", "couldn't locate",
        "not available", "not in", "limited information", "no information",
        "couldn't confirm", "cannot confirm", "not covered", "insufficient",
        "don't have", "do not have", "not enough", "couldn't verify",
    ]
    acknowledged = any(sig in answer_lower for sig in acknowledgment_signals)

    # Also check: if confidence is "low" from structured output, that's a good signal
    if not acknowledged and response.structured and response.structured.confidence == "low":
        acknowledged = True

    return CheckResult(
        name="out_of_reach_acknowledged",
        passed=acknowledged,
        failure_tags=[] if acknowledged else ["unanswerable_not_acknowledged"],
        detail=(
            "Agent acknowledged limitation for out-of-reach content"
            if acknowledged
            else "Agent may have overclaimed on out-of-reach content"
        ),
    )


def _answer_length_reasonable(case: TestCase, response: AgentResponse) -> CheckResult:
    n = len(response.answer)
    passed = 15 < n < 4000
    return CheckResult(
        name="answer_length_reasonable",
        passed=passed,
        failure_tags=[] if passed else (["incomplete_answer"] if n <= 15 else ["overclaiming"]),
        detail=f"Answer length: {n} chars",
    )


def _confidence_calibrated(case: TestCase, response: AgentResponse) -> CheckResult:
    """Flag obvious miscalibration: high confidence on out-of-reach content."""
    if not response.structured:
        return CheckResult(name="confidence_calibrated", passed=True, detail="No structured output")

    conf = response.structured.confidence
    if case.retrievability == "out_of_reach" and conf == "high":
        return CheckResult(
            name="confidence_calibrated",
            passed=False,
            failure_tags=["overclaiming"],
            detail=f"High confidence on out-of-reach case (retrievability={case.retrievability})",
        )
    return CheckResult(
        name="confidence_calibrated",
        passed=True,
        detail=f"Confidence '{conf}' appropriate for retrievability '{case.retrievability}'",
    )


def _diagnose_fact_retrieval(case: TestCase, response: AgentResponse) -> CheckResult:
    """Disambiguate WHY a key fact is missing or ungrounded.

    Five states, not four — State D is split to distinguish genuine hallucination
    from answers that are correct but exceed the retrieval window:

    A) Fact in retrieved content, NOT in answer → extraction_failure
       (model had the content, didn't use it — prompt failure)
    B) Fact NOT in retrieved content, right article searched, NOT in answer → fact_beyond_cutoff
       (correct strategy, fact past 1000-word window — system limit)
    C) Fact NOT in retrieved content, wrong/no article, NOT in answer → retrieval_failure
       (wrong query — prompt failure)
    D) Fact IN answer, NOT in retrieved content, NOT confirmed in full article → grounding_failure
       (model stated something Wikipedia doesn't confirm — genuine hallucination risk)
    E) Fact IN answer, NOT in retrieved content, BUT confirmed in full article + right article
       searched → answer_exceeds_retrieval_window
       (agent answered correctly, fact confirmed in Wikipedia but past the window — system
       limit, NOT a prompt failure. Different from D: the source exists, the answer is
       consistent with Wikipedia; only the retrieval ceiling prevented grounding it.)

    The D/E distinction requires enrichment data (fact_in_full_article on TestCase).
    Without it, D is assumed (conservative — prefer to flag as potential hallucination).

    This check is diagnostic — its tags inform the synthesis report and prompt
    iteration priorities, but it does not affect overall_passed on its own.
    """
    answer_lower = response.answer.lower()

    # Aggregate all retrieved Wikipedia text across every search this turn
    retrieved_text = " ".join(
        s.content.lower() for s in response.searches if s.content
    )

    # Fuzzy-match searched titles against expected supporting articles
    def _article_searched(expected_title: str) -> bool:
        exp_tokens = set(expected_title.lower().split())
        for s in response.searches:
            searched_title = (s.title or "").lower()
            searched_query = s.query.lower()
            title_overlap = len(exp_tokens & set(searched_title.split())) / max(len(exp_tokens), 1)
            query_overlap = len(exp_tokens & set(searched_query.split())) / max(len(exp_tokens), 1)
            if title_overlap >= 0.6 or query_overlap >= 0.6:
                return True
        return False

    right_article_searched = (
        bool(case.supporting_articles)
        and any(_article_searched(t) for t in case.supporting_articles)
    )

    failure_tags: list[str] = []
    details: list[str] = []

    for fact in case.key_facts:
        f = fact.lower()
        in_answer = f in answer_lower
        in_retrieved = bool(retrieved_text) and f in retrieved_text

        # ── States D / E: fact in answer but not in retrieved content ───────────
        if in_answer and not in_retrieved:
            # Determine whether the fact is confirmed anywhere in the full Wikipedia
            # article (requires enrichment data). This distinguishes:
            #   E — answer correct, Wikipedia agrees, window too short (system limit)
            #   D — fact not confirmed in Wikipedia, answer from training (hallucination risk)
            confirmed_in_full = (
                case.fact_in_full_article is True and right_article_searched
            )
            if confirmed_in_full:
                # State E: the agent answered correctly, Wikipedia confirms the fact
                # (just past our window), and the right article was searched.
                # This is a retrieval ceiling limitation, not a prompt failure.
                if "answer_exceeds_retrieval_window" not in failure_tags:
                    failure_tags.append("answer_exceeds_retrieval_window")
                details.append(
                    f"'{fact}': in answer, confirmed in full Wikipedia article but past "
                    f"1000-word window — correct answer, system retrieval limit"
                )
            else:
                # State D: fact in answer but not confirmed in full Wikipedia article
                # (or enrichment data absent) — potential hallucination from training.
                if "grounding_failure" not in failure_tags:
                    failure_tags.append("grounding_failure")
                details.append(
                    f"'{fact}': in answer but NOT in retrieved content"
                    + (" (not confirmed in full article → likely training knowledge)"
                       if case.fact_in_full_article is False
                       else " (enrichment absent — conservative: flagging as grounding risk)")
                )

        # ── State A: extraction failure — fact was available, model missed it ──
        elif not in_answer and in_retrieved:
            if "extraction_failure" not in failure_tags:
                failure_tags.append("extraction_failure")
            details.append(
                f"'{fact}': in retrieved content but NOT in answer → model ignored available content"
            )

        # ── States B/C: fact not in retrieved, not in answer ──────────────────
        elif not in_answer and not in_retrieved:
            # If pre-computed enrichment data is available, use it for exact determination
            if case.fact_in_full_article is True and right_article_searched:
                # Confirmed: fact exists in article but beyond our 1000-word window
                if "fact_beyond_cutoff" not in failure_tags:
                    failure_tags.append("fact_beyond_cutoff")
                details.append(
                    f"'{fact}': confirmed in full article but beyond 1000-word retrieval window"
                )
            elif case.retrievability == "out_of_reach" and right_article_searched:
                # Known out-of-reach case — expected behaviour
                if "fact_beyond_cutoff" not in failure_tags:
                    failure_tags.append("fact_beyond_cutoff")
                details.append(
                    f"'{fact}': expected out-of-reach — right article searched, system limitation"
                )
            elif right_article_searched:
                # Inferred: right article, fact not in window → likely beyond cutoff
                if "fact_beyond_cutoff" not in failure_tags:
                    failure_tags.append("fact_beyond_cutoff")
                details.append(
                    f"'{fact}': right article searched but fact not in 1000-word window "
                    f"(run enrich_dataset.py to confirm)"
                )
            else:
                # Wrong or no article searched → retrieval failure
                if "retrieval_failure" not in failure_tags:
                    failure_tags.append("retrieval_failure")
                searched = [s.query for s in response.searches]
                details.append(
                    f"'{fact}': not found; expected {case.supporting_articles}, "
                    f"searched {searched} → retrieval failure"
                )

    passed = len(failure_tags) == 0
    return CheckResult(
        name="fact_retrieval_diagnosis",
        passed=passed,
        failure_tags=failure_tags,
        detail=(
            "; ".join(details)
            if details
            else "All key facts correctly retrieved and present in answer"
        ),
    )
