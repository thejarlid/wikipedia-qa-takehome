"""Pairwise comparison — orchestrates four specialized judges concurrently.

Each judge compares two responses on its own dimension using its own rubric,
rather than one general judge trying to assess all dimensions at once.
This mirrors the Constitutional AI approach: binary preference on a specific
dimension is more reliable than multi-objective scoring.

Judges run concurrently for speed. Results aggregated into PairwiseResult.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict

from evals.dataset.schema import TestCase
from evals.judges import completeness, correctness, groundedness, search_strategy
from src.agent import AgentResponse


@dataclass
class DimensionComparison:
    winner: str         # "A" | "B" | "tie"
    confidence: str     # "clear" | "slight"
    reasoning: str
    failure_tags_A: list[str] = field(default_factory=list)
    failure_tags_B: list[str] = field(default_factory=list)


@dataclass
class PairwiseResult:
    case_id: str
    question: str
    category: str
    label_a: str
    label_b: str
    groundedness: DimensionComparison
    correctness: DimensionComparison
    completeness: DimensionComparison
    search_strategy: DimensionComparison
    overall: DimensionComparison  # derived, not a separate judge call

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def b_wins(self) -> int:
        """Number of dimensions where B wins (use for 'how much did the new version improve?')."""
        dims = [self.groundedness, self.correctness, self.completeness, self.search_strategy]
        return sum(1 for d in dims if d.winner == "B")

    @property
    def a_wins(self) -> int:
        dims = [self.groundedness, self.correctness, self.completeness, self.search_strategy]
        return sum(1 for d in dims if d.winner == "A")

    @property
    def regressions(self) -> list[str]:
        """Dimension names where B (new version) is worse than A (baseline)."""
        dims = {
            "groundedness": self.groundedness,
            "correctness": self.correctness,
            "completeness": self.completeness,
            "search_strategy": self.search_strategy,
        }
        return [name for name, d in dims.items() if d.winner == "A" and d.confidence == "clear"]


def _derive_overall(dims: list[DimensionComparison], label_a: str, label_b: str) -> DimensionComparison:
    """Derive overall winner by majority vote across the four dimensions."""
    a_wins = sum(1 for d in dims if d.winner == "A")
    b_wins = sum(1 for d in dims if d.winner == "B")
    ties = sum(1 for d in dims if d.winner == "tie")

    if b_wins > a_wins:
        winner = "B"
        confidence = "clear" if b_wins >= 3 else "slight"
        reasoning = f"{label_b} wins {b_wins}/4 dimensions, {label_a} wins {a_wins}/4, {ties} ties."
    elif a_wins > b_wins:
        winner = "A"
        confidence = "clear" if a_wins >= 3 else "slight"
        reasoning = f"{label_a} wins {a_wins}/4 dimensions, {label_b} wins {b_wins}/4, {ties} ties."
    else:
        winner = "tie"
        confidence = "slight"
        reasoning = f"Split: {label_a} wins {a_wins}, {label_b} wins {b_wins}, {ties} ties."

    return DimensionComparison(winner=winner, confidence=confidence, reasoning=reasoning)


def run(
    case: TestCase,
    response_a: AgentResponse,
    response_b: AgentResponse,
    label_a: str = "A",
    label_b: str = "B",
) -> PairwiseResult:
    """Run all four specialized pairwise judges concurrently and aggregate results."""

    judge_fns = {
        "groundedness":    lambda: groundedness.run_pairwise(case, response_a, response_b, label_a, label_b),
        "correctness":     lambda: correctness.run_pairwise(case, response_a, response_b, label_a, label_b),
        "completeness":    lambda: completeness.run_pairwise(case, response_a, response_b, label_a, label_b),
        "search_strategy": lambda: search_strategy.run_pairwise(case, response_a, response_b, label_a, label_b),
    }

    dim_results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn): name for name, fn in judge_fns.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                dim_results[name] = future.result()
            except Exception as exc:
                dim_results[name] = {
                    "winner": "tie", "confidence": "slight",
                    "reasoning": f"judge error: {exc}",
                    "failure_tags_A": [], "failure_tags_B": [],
                }

    def _dc(key: str) -> DimensionComparison:
        d = dim_results.get(key, {})
        return DimensionComparison(
            winner=d.get("winner", "tie"),
            confidence=d.get("confidence", "slight"),
            reasoning=d.get("reasoning", ""),
            failure_tags_A=d.get("failure_tags_A", []),
            failure_tags_B=d.get("failure_tags_B", []),
        )

    g = _dc("groundedness")
    c = _dc("correctness")
    cp = _dc("completeness")
    ss = _dc("search_strategy")
    overall = _derive_overall([g, c, cp, ss], label_a, label_b)

    return PairwiseResult(
        case_id=case.id,
        question=case.question,
        category=case.category,
        label_a=label_a,
        label_b=label_b,
        groundedness=g,
        correctness=c,
        completeness=cp,
        search_strategy=ss,
        overall=overall,
    )
