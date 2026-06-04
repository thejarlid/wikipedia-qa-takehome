"""Completeness judge — Haiku, mechanical.

Checks whether the answer addresses all parts of the question and is
appropriately detailed. Mechanical enough for Haiku.
"""

from __future__ import annotations

from evals.dataset.schema import TestCase
from evals.judges.base import HAIKU, SONNET, judge_call, pairwise_call
from evals.schema import JudgeResult
from src.agent import AgentResponse

_SYSTEM = """\
You are evaluating whether a QA system's answer is complete and appropriately detailed.

RUBRIC (score 1-5):
5 - COMPLETE: All parts of the question are addressed. Appropriate level of detail — not padded, not missing anything important.
4 - MOSTLY COMPLETE: One minor gap or slightly thin on detail, but the core question is answered.
3 - PARTIALLY COMPLETE: Addresses the main question but misses a secondary component or is significantly underdeveloped.
2 - INCOMPLETE: A significant part of the question is unanswered. The answer would be misleading or insufficient.
1 - VERY INCOMPLETE: Barely addresses what was asked, or is a non-answer.

SPECIAL CASES:
- For out-of-scope cases that were correctly declined: score 5 — a clear decline IS a complete response.
- For out_of_reach cases: score 5 if the agent clearly states what it found and what it couldn't find.

FAILURE TAGS — include all that apply:
- "incomplete_answer": A meaningful part of the question was not addressed.
- "overclaiming": The answer is padded or overstates what was found.
- "underclaiming": The answer hedges or declines when Wikipedia clearly supported an answer.

PASS threshold: score ≥ 4.

Respond with valid JSON only:
{
  "score": <integer 1-5>,
  "reasoning": "<brief explanation>",
  "failure_tags": [<zero or more tags>]
}"""


def run(case: TestCase, response: AgentResponse) -> JudgeResult:
    user_msg = f"""\
Question: {case.question}
Category: {case.category}
Retrievability: {case.retrievability}

Agent's answer:
{response.answer}

Evaluate completeness using the rubric."""

    return judge_call(
        model=HAIKU,
        system_prompt=_SYSTEM,
        user_message=user_msg,
        judge_name="completeness",
        pass_threshold=4,
    )


def run_pairwise(
    case: TestCase,
    response_a: AgentResponse,
    response_b: AgentResponse,
    label_a: str = "A",
    label_b: str = "B",
) -> dict:
    """Compare two responses on completeness using the completeness rubric."""
    user_msg = (
        f"Question: {case.question}\n"
        f"Category: {case.category}\n"
        f"Retrievability: {case.retrievability}\n\n"
        f"## Response {label_a}:\n{response_a.answer}\n\n"
        f"## Response {label_b}:\n{response_b.answer}\n\n"
        "Compare completeness: which answer more fully addresses the question?"
    )
    # Use Sonnet for pairwise even though single-response uses Haiku —
    # comparative judgments benefit from stronger reasoning
    return pairwise_call(model=SONNET, system_prompt=_SYSTEM, user_message=user_msg)
