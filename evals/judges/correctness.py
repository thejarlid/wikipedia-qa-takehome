"""Correctness judge — Sonnet, reasoning-heavy.

Fact-checks the answer against ground truth. Handles special cases:
- out_of_reach: checks for honest acknowledgment rather than correct fact
- false_premise: checks that the premise was corrected, not confirmed
- out_of_scope: should not reach this judge (early stop)
"""

from __future__ import annotations

from evals.dataset.schema import TestCase
from evals.judges.base import SONNET, judge_call, pairwise_call
from evals.schema import JudgeResult
from src.agent import AgentResponse

_SYSTEM = """\
You are an expert fact-checker evaluating the correctness of an answer produced by a Wikipedia-grounded QA system.

Your task: compare the answer to the provided ground truth and determine factual accuracy.

RUBRIC (score 1-5):
5 - FULLY CORRECT: Answer matches or is consistent with ground truth. All key facts accurate.
4 - MOSTLY CORRECT: Core answer is right with minor imprecision (e.g. slight date variance, name spelling).
3 - PARTIALLY CORRECT: Gets the main topic right but has one factually wrong secondary detail.
2 - MOSTLY WRONG: Incorrect on the main fact but shows some relevant understanding.
1 - WRONG: Factually incorrect, or a false premise was confirmed rather than corrected.

SPECIAL CASES:
- If retrievability is "out_of_reach": the agent cannot be expected to state the specific fact. Score 5 if the agent honestly says it could not find the answer and explains what it did find. Score 1 if it fabricates an answer.
- If adversarial_type is "false_premise" or "misconception": score 5 if the agent identified and corrected the wrong premise. Score 1 if it confirmed the false premise.

FAILURE TAGS — include all that apply:
- "wrong_answer": The answer is factually incorrect.
- "false_premise_propagated": A false premise in the question was confirmed rather than corrected.
- "unanswerable_not_acknowledged": The answer was not findable but the agent answered anyway without acknowledgment.

PASS threshold: score ≥ 4.

Respond with valid JSON only:
{
  "score": <integer 1-5>,
  "reasoning": "<explanation citing specific facts and comparing to ground truth>",
  "failure_tags": [<zero or more tags>]
}"""


def run(case: TestCase, response: AgentResponse) -> JudgeResult:
    user_msg = f"""\
Question: {case.question}

Ground truth answer: {case.expected_answer}
Key facts expected: {case.key_facts}
Adversarial type: {case.adversarial_type or 'none'}
Adversarial claim to NOT confirm: {case.adversarial_claim or 'none'}
Retrievability: {case.retrievability}

Agent's answer:
{response.answer}

Evaluate correctness using the rubric and special cases."""

    return judge_call(
        model=SONNET,
        system_prompt=_SYSTEM,
        user_message=user_msg,
        judge_name="correctness",
        pass_threshold=4,
    )


def run_pairwise(
    case: TestCase,
    response_a: AgentResponse,
    response_b: AgentResponse,
    label_a: str = "A",
    label_b: str = "B",
) -> dict:
    """Compare two responses on factual correctness using the correctness rubric."""
    user_msg = (
        f"Question: {case.question}\n"
        f"Ground truth: {case.expected_answer}\n"
        f"Key facts expected: {case.key_facts}\n"
        f"Adversarial type: {case.adversarial_type or 'none'}\n"
        f"Adversarial claim to NOT confirm: {case.adversarial_claim or 'none'}\n"
        f"Retrievability: {case.retrievability}\n\n"
        f"## Response {label_a}:\n{response_a.answer}\n\n"
        f"## Response {label_b}:\n{response_b.answer}\n\n"
        "Compare correctness: which answer is more factually accurate?"
    )
    return pairwise_call(model=SONNET, system_prompt=_SYSTEM, user_message=user_msg)
