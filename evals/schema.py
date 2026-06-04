"""Data structures for eval results."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class CheckResult:
    name: str
    passed: bool
    failure_tags: list[str] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JudgeResult:
    judge_name: str
    model: str
    score: int          # 1–5
    reasoning: str
    failure_tags: list[str] = field(default_factory=list)
    passed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalResult:
    case_id: str
    question: str
    category: str
    source: str
    retrievability: str
    prompt_version: str
    timestamp: str

    # Agent output
    answer: str
    declined: bool          # from StructuredAnswer.declined
    confidence: str
    sources_used: list[str]
    reasoning: str
    limitations: str | None
    searches: list[dict]    # serialised SearchResult list (query, title, url, error)
    iterations: int

    # Compact agent trace — always embedded.
    # Each step: {step, model_text, tool_name, tool_input}
    # tool_result (full Wikipedia text) is omitted here — already in searches[].
    # Use --save-traces to also write full traces to traces/ for deep debugging.
    trace: list[dict] = field(default_factory=list)

    # Early stop — only applies to out_of_scope cases
    early_stop: bool = False
    early_stop_outcome: str = ""
    # "correctly_declined" → case passed at deterministic layer
    # "scope_violation"   → answered when it should have declined

    # Deterministic checks (empty when early_stop=True)
    checks: dict[str, dict] = field(default_factory=dict)
    checks_passed: bool = False

    # Judge results (empty when early_stop=True)
    judges: dict[str, dict] = field(default_factory=dict)
    judges_passed: bool = False

    # Failure taxonomy — union of tags from all checks + judges
    failure_tags: list[str] = field(default_factory=list)

    # Weighted composite score 0–100.
    # Computed from judge scores using JUDGE_WEIGHTS in runner.py.
    # Normalises each 1–5 judge score to 0–100, applies weights, sums.
    # Early-stop cases: 100 for correctly_declined, 0 for scope_violation.
    composite_score: float = 0.0

    # Overall
    overall_passed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
