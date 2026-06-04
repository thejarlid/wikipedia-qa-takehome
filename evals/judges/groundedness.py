"""Groundedness judge — Sonnet, reasoning-heavy.

Evaluates whether every factual claim in the answer is traceable to the
retrieved Wikipedia content. Requires nuanced semantic comparison.
"""

from __future__ import annotations

from evals.dataset.schema import TestCase
from evals.judges.base import SONNET, judge_call, pairwise_call
from evals.schema import JudgeResult
from src.agent import AgentResponse

_SYSTEM = """\
You are an expert evaluator assessing whether a Wikipedia-grounded QA system's answer is properly grounded in its retrieved sources.

Your task: determine whether every factual claim in the answer can be traced directly to the retrieved Wikipedia content provided.

RUBRIC (score 1-5):
5 - FULLY GROUNDED: Every factual claim traces directly to the retrieved Wikipedia text. Nothing material added from outside.
4 - MOSTLY GROUNDED: Trivial additions only (e.g. clarifying phrases, well-known units). All core factual claims from Wikipedia.
3 - PARTIALLY GROUNDED: Some claims extend beyond retrieved text but are plausible for the topic and not contradicted by Wikipedia.
2 - WEAKLY GROUNDED: Significant facts stated that are absent from retrieved text. Answer materially relies on non-Wikipedia information.
1 - NOT GROUNDED: Answer primarily uses training knowledge. Retrieved Wikipedia content barely influences the response.

FAILURE TAGS — include all that apply:
- "hallucination": A specific fact is stated that is not present anywhere in the retrieved Wikipedia text.
- "grounding_failure": The overall answer cannot be traced to the retrieved content (systemic, not isolated).

PASS threshold: score ≥ 4.

Respond with valid JSON only — no prose outside the JSON:
{
  "score": <integer 1-5>,
  "reasoning": "<concise explanation citing specific claims and whether they appear in the retrieved text>",
  "failure_tags": [<zero or more tags from the list above>]
}"""


def run(case: TestCase, response: AgentResponse) -> JudgeResult:
    # Build a clear picture of what the agent searched for and what it received.
    # This is the complete information available to the agent — nothing more.
    # The judge uses this to verify every claim in the answer traces back to here.
    retrieved_sections = []
    for i, s in enumerate(response.searches, 1):
        if s.error:
            retrieved_sections.append(
                f"Search {i}: query={s.query!r}\n  ERROR: {s.error}\n  (no content returned)"
            )
        elif s.title and s.content:
            retrieved_sections.append(
                f"Search {i}: query={s.query!r}\n"
                f"  Article: {s.title}\n"
                f"  URL: {s.url}\n"
                f"  Content:\n{s.content}"
            )
        else:
            retrieved_sections.append(
                f"Search {i}: query={s.query!r}\n  (no article found)"
            )

    if retrieved_sections:
        retrieved_block = "\n\n".join(retrieved_sections)
    else:
        retrieved_block = "(no Wikipedia searches were made — agent answered from memory)"

    user_msg = f"""\
Question: {case.question}

## Everything the agent retrieved from Wikipedia:
{retrieved_block}

## Agent's answer:
{response.answer}

Your task: determine whether every factual claim in the answer can be traced \
to the Wikipedia content above. The agent had access to ONLY the content shown \
above — nothing else. If the answer states a fact not present in any of the \
retrieved articles, that is a hallucination from training data.

Evaluate groundedness using the rubric."""

    return judge_call(
        model=SONNET,
        system_prompt=_SYSTEM,
        user_message=user_msg,
        judge_name="groundedness",
        pass_threshold=4,
    )


def run_pairwise(
    case: TestCase,
    response_a: AgentResponse,
    response_b: AgentResponse,
    label_a: str = "A",
    label_b: str = "B",
) -> dict:
    """Compare two responses on groundedness using the groundedness rubric."""
    def _retrieved(resp: AgentResponse) -> str:
        sections = []
        for i, s in enumerate(resp.searches, 1):
            if s.error:
                sections.append(f"Search {i}: query={s.query!r}\n  ERROR: {s.error}")
            elif s.title and s.content:
                sections.append(f"Search {i}: query={s.query!r}\n  Article: {s.title}\n  Content:\n{s.content}")
            else:
                sections.append(f"Search {i}: query={s.query!r}\n  (not found)")
        return "\n\n".join(sections) if sections else "(no searches made)"

    user_msg = (
        f"Question: {case.question}\n\n"
        f"## Response {label_a} — retrieved Wikipedia content:\n{_retrieved(response_a)}\n\n"
        f"## Response {label_a} — answer:\n{response_a.answer}\n\n"
        f"## Response {label_b} — retrieved Wikipedia content:\n{_retrieved(response_b)}\n\n"
        f"## Response {label_b} — answer:\n{response_b.answer}\n\n"
        "Compare groundedness: which answer stays closer to the retrieved Wikipedia content?"
    )
    return pairwise_call(model=SONNET, system_prompt=_SYSTEM, user_message=user_msg)
