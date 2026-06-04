"""Synthesis report generator.

Reads eval results and produces:
  1. Structured statistics (pass rates, failure tag frequencies)
  2. LLM-synthesized narrative diagnosis (Sonnet, Option B per D-12)
  3. Pairwise comparison summary (if comparison results provided)

Output: markdown report printed to console and optionally saved to results/.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from evals.judges.base import SONNET, get_client
from evals.schema import EvalResult

_SYNTHESIS_SYSTEM = """\
You are an expert AI systems analyst reviewing the results of an evaluation run on a Wikipedia-grounded QA agent.

You will be given structured statistics about where the system succeeded and failed, including failure tag frequencies, per-category pass rates, and judge score distributions.

Your job: write a concise, insightful diagnostic narrative with these sections:

1. **Systematic Failure Patterns** — What failure modes appear most frequently? Group related tags together and name the underlying pattern (e.g., "Query formulation is consistently too verbose, indicating the prompt's query guidance isn't being followed").

2. **What Each Pattern Reveals About the System Prompt** — For each failure pattern, explain specifically which part of the system prompt is missing, weak, or absent. Be concrete (e.g., "There is no explicit instruction about what to do when retrieved content doesn't contain the answer, leading to overclaiming").

3. **Priority Order of Fixes** — Rank the top 3–5 prompt improvements by expected impact × frequency. For each: what to add/change and why.

4. **What the System Reliably Gets Right** — Areas of consistent success. Be specific about which case categories or question types perform well.

Keep the narrative tight — aim for 400–600 words total. Write for an engineer who will use this to write the next prompt version. Reference the prompt version supplied in the user message when labelling your narrative heading."""

_PAIRWISE_SYSTEM = """\
You are summarising pairwise comparison results between two versions of a Wikipedia QA system prompt.

Given per-dimension win rates and representative cases where v2 won or lost, write a concise summary:
1. Where v2 improved over v1 (with specific examples)
2. Where v2 regressed or tied unexpectedly
3. Whether the improvements align with the intended prompt changes
4. One key insight about what the pairwise comparison reveals that per-case scoring alone would miss

Keep it to 200–300 words."""


def generate(
    results: list[EvalResult],
    pairwise_results: list[dict] | None = None,
    save_to: Path | None = None,
    prompt_version: str | None = None,
) -> str:
    """Generate the full synthesis report as a markdown string."""
    stats = _compute_stats(results)
    # Infer version from results if not supplied
    if not prompt_version and results:
        prompt_version = results[0].prompt_version
    narrative = _synthesize_narrative(stats, prompt_version=prompt_version or "unknown")
    pairwise_section = ""
    pairwise_labels: tuple[str, str] = ("A", "B")
    if pairwise_results:
        pairwise_section = _pairwise_summary(pairwise_results)
        pairwise_labels = (
            pairwise_results[0].get("label_a", "A"),
            pairwise_results[0].get("label_b", "B"),
        )

    report = _render_report(stats, narrative, pairwise_section, pairwise_labels)

    if save_to:
        save_to.parent.mkdir(exist_ok=True)
        save_to.write_text(report)
        print(f"Report saved to: {save_to}")

    return report


def _compute_stats(results: list[EvalResult]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.overall_passed)

    # Pass rates by category
    by_cat: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r.overall_passed)

    # Pass rates by retrievability
    by_ret: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_ret[r.retrievability].append(r.overall_passed)

    # Failure tag frequency
    all_tags: list[str] = []
    for r in results:
        all_tags.extend(r.failure_tags)
    tag_counts = Counter(all_tags)

    # Early stop stats
    early_stops = [r for r in results if r.early_stop]
    correct_declines = sum(1 for r in early_stops if r.early_stop_outcome == "correctly_declined")
    scope_violations = sum(1 for r in early_stops if r.early_stop_outcome == "scope_violation")

    # Per-judge average scores
    judge_scores: dict[str, list[int]] = defaultdict(list)
    for r in results:
        for judge_name, jr in r.judges.items():
            if isinstance(jr, dict) and "score" in jr:
                judge_scores[judge_name].append(jr["score"])

    judge_avgs = {
        name: round(sum(scores) / len(scores), 2)
        for name, scores in judge_scores.items()
        if scores
    }

    # Per-judge pass rates
    judge_pass: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        for judge_name, jr in r.judges.items():
            if isinstance(jr, dict) and "passed" in jr:
                judge_pass[judge_name].append(jr["passed"])

    judge_pass_rates = {
        name: round(sum(passes) / len(passes) * 100, 1)
        for name, passes in judge_pass.items()
        if passes
    }

    # Failure examples (up to 3 per top tag)
    failure_examples: dict[str, list[str]] = defaultdict(list)
    for r in results:
        for tag in r.failure_tags:
            if len(failure_examples[tag]) < 3:
                failure_examples[tag].append(f"[{r.case_id}] {r.question[:80]}")

    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "by_category": {
            cat: {"total": len(v), "passed": sum(v), "rate": round(sum(v) / len(v) * 100, 1)}
            for cat, v in sorted(by_cat.items())
        },
        "by_retrievability": {
            ret: {"total": len(v), "passed": sum(v), "rate": round(sum(v) / len(v) * 100, 1)}
            for ret, v in sorted(by_ret.items())
        },
        "tag_counts": tag_counts.most_common(20),
        "early_stop": {
            "total": len(early_stops),
            "correctly_declined": correct_declines,
            "scope_violations": scope_violations,
        },
        "judge_averages": judge_avgs,
        "judge_pass_rates": judge_pass_rates,
        "failure_examples": {tag: examples for tag, examples in failure_examples.items()},
    }


def _synthesize_narrative(stats: dict, prompt_version: str = "unknown") -> str:
    """Ask Sonnet to synthesize the failure patterns into actionable diagnostics."""
    stats_text = json.dumps(stats, indent=2)
    client = get_client()
    response = client.messages.create(
        model=SONNET,
        max_tokens=2048,
        temperature=0,
        system=[{"type": "text", "text": _SYNTHESIS_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": (
                f"Prompt version being evaluated: {prompt_version}\n\n"
                f"Here are the eval statistics:\n\n```json\n{stats_text}\n```\n\n"
                "Please write the diagnostic narrative."
            ),
        }],
    )
    return response.content[0].text.strip()


def _pairwise_summary(pairwise_results: list[dict]) -> str:
    """Ask Sonnet to summarize pairwise comparison results."""
    # Extract actual version labels from data (PairwiseResult stores label_a / label_b)
    label_a = pairwise_results[0].get("label_a", "A") if pairwise_results else "A"
    label_b = pairwise_results[0].get("label_b", "B") if pairwise_results else "B"

    # Compute win rates per dimension
    dim_wins: dict[str, Counter] = {
        d: Counter() for d in ["groundedness", "correctness", "completeness", "search_strategy", "overall"]
    }
    for pr in pairwise_results:
        for dim in dim_wins:
            winner = pr.get(dim, {}).get("winner", "tie")
            dim_wins[dim][winner] += 1

    win_rate_summary = {
        dim: {
            f"{label_b}_wins": counts.get("B", 0),
            f"{label_a}_wins": counts.get("A", 0),
            "ties": counts.get("tie", 0),
            f"{label_b}_win_rate": round(counts.get("B", 0) / len(pairwise_results) * 100, 1) if pairwise_results else 0,
        }
        for dim, counts in dim_wins.items()
    }

    # Sample cases where the new version clearly won / lost
    b_clear_wins = [
        pr for pr in pairwise_results
        if pr.get("overall", {}).get("winner") == "B"
        and pr.get("overall", {}).get("confidence") == "clear"
    ][:3]
    a_holds = [
        pr for pr in pairwise_results
        if pr.get("overall", {}).get("winner") == "A"
        and pr.get("overall", {}).get("confidence") == "clear"
    ][:3]

    summary_input = {
        "baseline": label_a,
        "new_version": label_b,
        "win_rates": win_rate_summary,
        f"{label_b}_clear_wins": b_clear_wins,
        f"{label_a}_holds": a_holds,
    }

    client = get_client()
    response = client.messages.create(
        model=SONNET,
        max_tokens=512,
        temperature=0,
        system=[{"type": "text", "text": _PAIRWISE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"Pairwise data:\n\n```json\n{json.dumps(summary_input, indent=2)}\n```\n\nWrite the summary.",
        }],
    )
    return response.content[0].text.strip()


def _render_report(
    stats: dict, narrative: str, pairwise_section: str,
    pairwise_labels: tuple[str, str] = ("A", "B"),
) -> str:
    lines = [
        "# Eval Report",
        "",
        f"**Cases evaluated:** {stats['total']}  ",
        f"**Overall pass rate:** {stats['pass_rate']}% ({stats['passed']}/{stats['total']})",
        "",
        "---",
        "",
        "## Pass Rates by Category",
        "",
        "| Category | Passed | Total | Rate |",
        "|----------|--------|-------|------|",
    ]
    for cat, d in stats["by_category"].items():
        lines.append(f"| {cat} | {d['passed']} | {d['total']} | {d['rate']}% |")

    lines += [
        "",
        "## Pass Rates by Retrievability Tier",
        "",
        "| Tier | Passed | Total | Rate |",
        "|------|--------|-------|------|",
    ]
    for ret, d in stats["by_retrievability"].items():
        lines.append(f"| {ret} | {d['passed']} | {d['total']} | {d['rate']}% |")

    lines += [
        "",
        "## Out-of-Scope Handling",
        f"- Correctly declined: {stats['early_stop']['correctly_declined']}",
        f"- Scope violations (answered when should decline): {stats['early_stop']['scope_violations']}",
        "",
        "## Judge Scores",
        "",
        "| Judge | Avg Score (1–5) | Pass Rate |",
        "|-------|-----------------|-----------|",
    ]
    for name in ["groundedness", "correctness", "completeness", "search_strategy"]:
        avg = stats["judge_averages"].get(name, "–")
        pr = stats["judge_pass_rates"].get(name, "–")
        lines.append(f"| {name} | {avg} | {pr}% |")

    lines += [
        "",
        "## Failure Tag Frequency",
        "",
        "| Tag | Count |",
        "|-----|-------|",
    ]
    for tag, count in stats["tag_counts"]:
        lines.append(f"| `{tag}` | {count} |")

    lines += [
        "",
        "---",
        "",
        "## Diagnostic Analysis",
        "",
        narrative,
    ]

    if pairwise_section:
        label_a, label_b = pairwise_labels
        lines += [
            "",
            "---",
            "",
            f"## Pairwise Comparison ({label_a} vs {label_b})",
            "",
            pairwise_section,
        ]

    return "\n".join(lines)
