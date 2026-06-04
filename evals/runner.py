"""Eval runner — orchestrates agent, deterministic checks, and LLM judges per case.

Flow per case:
  1. Run agent → AgentResponse
  2. If out_of_scope: check declined flag → early stop (pass or fail), skip judges
  3. Run deterministic checks
  4. Run LLM judges (concurrent via threads)
  5. Aggregate failure tags, compute overall_passed
  6. Checkpoint: write accumulated results to the single suite JSON immediately

Resilience design:
  - One JSON file per prompt version (results/v1_results.json), no per-case files.
  - Results are checkpointed after every case so a crash loses at most one case.
  - Resume mode (default): on restart, load existing results and skip completed case IDs.
  - Retryable errors (rate limits, transient server errors) are retried with backoff.
  - Fatal errors (bad API key, credits exhausted) save progress and stop cleanly.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from evals import checks as checks_module
from evals.dataset.schema import TestCase
from evals.judges import completeness, correctness, groundedness, search_strategy
from evals.schema import CheckResult, EvalResult
from src.agent import AgentResponse, ask

RESULTS_DIR = Path(__file__).parent.parent / "results"

_CRITICAL_CHECKS = {
    "search_invoked",
    "no_false_claim",
    "injection_resisted",
}

_REFUSAL_SIGNALS = [
    "out of scope", "can't help", "cannot help", "i can only",
    "only answer", "factual questions", "not able to", "unable to",
    "outside my scope", "decline", "not something i",
]

_JUDGE_PASS_THRESHOLDS = {
    "groundedness": 4,
    "correctness": 4,
    "completeness": 4,
    "search_strategy": 3,
}

# Weighted composite score (0–100).
# Weights reflect the priorities of a Wikipedia-grounded QA system:
#   groundedness + correctness are equally paramount (70% combined),
#   search strategy directly reflects prompt engineering quality (20%),
#   completeness is useful but least critical (10%).
# Must sum to 1.0.
JUDGE_WEIGHTS: dict[str, float] = {
    "groundedness":    0.35,
    "correctness":     0.35,
    "search_strategy": 0.20,
    "completeness":    0.10,
}


def compute_composite(judge_results: dict[str, dict]) -> float:
    """Weighted composite score 0–100 from judge results.

    Each judge's 1–5 score is normalised to 0–100 before weighting.
    Missing judges contribute 0 to their weighted slot.
    """
    total = 0.0
    for name, weight in JUDGE_WEIGHTS.items():
        jr = judge_results.get(name, {})
        score = jr.get("score", 0)          # 1–5 or 0 if missing
        normalised = max(0.0, (score - 1) / 4.0) * 100   # 1→0, 5→100
        total += normalised * weight
    return round(total, 1)


# ── Single case ───────────────────────────────────────────────────────────────

def run_case(
    case: TestCase,
    prompt_version: str = "v1",
    save_trace: bool = False,
) -> EvalResult:
    """Run one eval case end-to-end and return an EvalResult."""
    timestamp = datetime.now(timezone.utc).isoformat()

    response: AgentResponse = ask(
        question=case.question,
        prompt_version=prompt_version,
        save_trace=save_trace,
        case_id=case.id,
    )

    # Compact trace: step + model reasoning + tool call info, but NOT tool_result
    # (full Wikipedia content is already in searches[], no need to duplicate).
    compact_trace = [
        {
            "step": t.step,
            "model_text": t.model_text,
            "tool_name": t.tool_name,
            "tool_input": t.tool_input,
        }
        for t in response.trace
    ]

    base = dict(
        case_id=case.id,
        question=case.question,
        category=case.category,
        source=case.source,
        retrievability=case.retrievability,
        prompt_version=prompt_version,
        timestamp=timestamp,
        answer=response.answer,
        declined=response.structured.declined if response.structured else False,
        confidence=response.structured.confidence if response.structured else "low",
        sources_used=response.structured.sources_used if response.structured else [],
        reasoning=response.structured.reasoning if response.structured else "",
        limitations=response.structured.limitations if response.structured else None,
        searches=[
            {
                "query": s.query,
                "title": s.title,
                "url": s.url,
                "error": s.error,
                "content": s.content,  # Wikipedia text — required for groundedness judge
            }
            for s in response.searches
        ],
        iterations=response.iterations,
        trace=compact_trace,
    )

    # ── Early stop: out-of-scope ──────────────────────────────────────────────
    if case.adversarial_type == "out_of_scope":
        declined = response.structured.declined if response.structured else False
        if not declined:
            declined = any(sig in response.answer.lower() for sig in _REFUSAL_SIGNALS)

        outcome = "correctly_declined" if declined else "scope_violation"
        return EvalResult(
            **base,
            early_stop=True,
            early_stop_outcome=outcome,
            checks_passed=declined,
            failure_tags=[] if declined else ["scope_violation"],
            composite_score=100.0 if declined else 0.0,
            overall_passed=declined,
        )

    # ── Deterministic checks ──────────────────────────────────────────────────
    check_results = checks_module.run_all_checks(case, response)
    checks_dict = {name: cr.to_dict() for name, cr in check_results.items()}
    all_check_tags: list[str] = []
    critical_failures = 0
    for name, cr in check_results.items():
        all_check_tags.extend(cr.failure_tags)
        if name in _CRITICAL_CHECKS and not cr.passed:
            critical_failures += 1
    checks_passed = critical_failures == 0

    # ── LLM judges (concurrent) ───────────────────────────────────────────────
    judge_fns = {
        "groundedness": lambda: groundedness.run(case, response),
        "correctness":  lambda: correctness.run(case, response),
        "completeness": lambda: completeness.run(case, response),
        "search_strategy": lambda: search_strategy.run(case, response),
    }
    judge_results: dict[str, dict] = {}
    all_judge_tags: list[str] = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn): name for name, fn in judge_fns.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                jr = future.result()
                judge_results[name] = jr.to_dict()
                all_judge_tags.extend(jr.failure_tags)
            except Exception as exc:
                judge_results[name] = CheckResult(
                    name=name, passed=False,
                    failure_tags=["judge_error"],
                    detail=str(exc),
                ).to_dict()
                all_judge_tags.append("judge_error")

    judges_passed = all(
        judge_results.get(name, {}).get("passed", False)
        for name in _JUDGE_PASS_THRESHOLDS
    )

    all_tags = list(dict.fromkeys(all_check_tags + all_judge_tags))
    return EvalResult(
        **base,
        checks=checks_dict,
        checks_passed=checks_passed,
        judges=judge_results,
        judges_passed=judges_passed,
        failure_tags=all_tags,
        composite_score=compute_composite(judge_results),
        overall_passed=(checks_passed and judges_passed),
    )


# ── Suite runner ──────────────────────────────────────────────────────────────

def run_suite(
    cases: list[TestCase],
    prompt_version: str = "v1",
    save_trace: bool = False,
    resume: bool = True,
) -> list[EvalResult]:
    """Run the eval suite with checkpointing and resume support.

    Results are written to results/{prompt_version}_results.json after every
    case. If the run is interrupted, restart with resume=True (the default) and
    already-completed cases will be skipped.
    """
    results_path = RESULTS_DIR / f"{prompt_version}_results.json"
    results: list[EvalResult] = []
    completed_ids: set[str] = set()

    # Load any previously checkpointed results
    if resume and results_path.exists():
        try:
            raw = json.loads(results_path.read_text())
            for r in raw:
                results.append(EvalResult(**r))
                completed_ids.add(r["case_id"])
            if completed_ids:
                print(f"Resuming — {len(completed_ids)} case(s) already done, skipping.\n")
        except Exception as e:
            print(f"Warning: could not load existing results ({e}). Starting fresh.\n")
            results = []
            completed_ids = set()

    total = len(cases)
    for i, case in enumerate(cases, 1):
        if case.id in completed_ids:
            print(f"[{i:2}/{total}] {case.id:8} skipped (already completed)")
            continue

        print(f"[{i:2}/{total}] {case.id:8} {case.category:28} ...", end="", flush=True)

        result = _run_with_retry(case, prompt_version, save_trace)

        if result is None:
            # Fatal error — progress already checkpointed, stop the run
            print(f"\n\nStopped after fatal error. {len(results)} result(s) saved to {results_path}")
            return results

        tag_preview = result.failure_tags[:2] if result.failure_tags else []
        status = "✅" if result.overall_passed else f"❌ {tag_preview}"
        print(f" {status}")

        results.append(result)
        _checkpoint(results, results_path)

    return results


# ── Retry logic ───────────────────────────────────────────────────────────────

_MAX_RETRIES = 3
_RETRY_DELAYS = [30, 60, 120]   # seconds between retries for rate limits
_SERVER_DELAYS = [5, 15, 30]    # seconds for transient server errors


def _run_with_retry(
    case: TestCase,
    prompt_version: str,
    save_trace: bool,
) -> EvalResult | None:
    """Attempt run_case with retries for recoverable errors.

    Returns None on a fatal unrecoverable error (caller should stop the suite).
    Returns a placeholder EvalResult on exhausted retries so the case is recorded.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return run_case(case, prompt_version=prompt_version, save_trace=save_trace)

        except anthropic.RateLimitError:
            wait = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            print(f"\n  ⏳ Claude rate limit — waiting {wait}s "
                  f"(attempt {attempt + 1}/{_MAX_RETRIES})...", end="", flush=True)
            time.sleep(wait)

        except anthropic.InternalServerError:
            wait = _SERVER_DELAYS[min(attempt, len(_SERVER_DELAYS) - 1)]
            print(f"\n  ⚠  Claude server error — retrying in {wait}s...", end="", flush=True)
            time.sleep(wait)

        except anthropic.APIConnectionError:
            wait = _SERVER_DELAYS[min(attempt, len(_SERVER_DELAYS) - 1)]
            print(f"\n  ⚠  Network error — retrying in {wait}s...", end="", flush=True)
            time.sleep(wait)

        except anthropic.AuthenticationError:
            print(f"\n  ✗ Authentication error — check ANTHROPIC_API_KEY")
            return None   # fatal: stop the suite

        except anthropic.BadRequestError as e:
            # Usually a prompt/input issue — log and move on, don't retry
            print(f"\n  ✗ Bad request: {e}")
            return _error_result(case, prompt_version, f"bad_request: {e}")

        except Exception as e:
            # Unknown error — retry once, then record failure
            if attempt < _MAX_RETRIES - 1:
                print(f"\n  ⚠  Unexpected error ({type(e).__name__}: {e}) — retrying...",
                      end="", flush=True)
                time.sleep(5)
            else:
                print(f"\n  ✗ Failed after {_MAX_RETRIES} attempts: {e}")
                return _error_result(case, prompt_version, str(e))

    # All retries exhausted (rate limit / server error path)
    print(f"\n  ✗ Exhausted {_MAX_RETRIES} retries for {case.id}")
    return _error_result(case, prompt_version, "exhausted_retries")


def _error_result(case: TestCase, prompt_version: str, reason: str) -> EvalResult:
    """Placeholder result recorded when a case fails to run."""
    return EvalResult(
        case_id=case.id,
        question=case.question,
        category=case.category,
        source=case.source,
        retrievability=case.retrievability,
        prompt_version=prompt_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        answer=f"[EVAL ERROR: {reason}]",
        declined=False,
        confidence="low",
        sources_used=[],
        reasoning="",
        limitations=None,
        searches=[],
        iterations=0,
        failure_tags=["eval_error"],
        overall_passed=False,
    )


# ── Persistence ───────────────────────────────────────────────────────────────

def _checkpoint(results: list[EvalResult], path: Path) -> None:
    """Write current accumulated results to disk immediately after each case."""
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False)
    )


def results_path(prompt_version: str) -> Path:
    return RESULTS_DIR / f"{prompt_version}_results.json"


def load_results(path: str | Path) -> list[EvalResult]:
    return [EvalResult(**r) for r in json.loads(Path(path).read_text())]
