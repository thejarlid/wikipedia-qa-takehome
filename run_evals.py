#!/usr/bin/env python3
"""Eval runner CLI.

Usage:
  python run_evals.py run --prompt v1
  python run_evals.py run --prompt v1 --categories nq_factual
  python run_evals.py compare results/v1_results.json results/v2_results.json
  python run_evals.py report results/v1_results.json
"""

import argparse
import json
import sys
from pathlib import Path

from evals.dataset import load_dataset
from evals.judges.pairwise import run as run_pairwise, PairwiseResult
from evals.report import generate as generate_report
from evals.runner import run_suite, results_path
from src.prompts import available_versions


def cmd_run(args) -> None:
    cases = load_dataset(
        sources=args.sources or None,
        categories=args.categories or None,
        retrievability=args.retrievability or None,
    )
    if not cases:
        print("No cases match the given filters.")
        sys.exit(1)

    resume = not args.no_resume
    print(f"\nRunning {len(cases)} cases  prompt={args.prompt}  resume={resume}\n")

    results = run_suite(
        cases,
        prompt_version=args.prompt,
        save_trace=args.save_traces,
        resume=resume,
    )

    out_path = results_path(args.prompt)
    passed = sum(1 for r in results if r.overall_passed)
    total = len(results)
    print(f"\nResults saved to: {out_path}")
    print(f"Overall: {passed}/{total} passed ({round(100*passed/total) if total else 0}%)\n")

    report = generate_report(results, save_to=Path(f"results/{args.prompt}_report.md"))
    print(report)


def cmd_compare(args) -> None:
    from collections import Counter, defaultdict
    from evals.dataset import ALL_CASES
    from src.agent import AgentResponse, SearchResult, StructuredAnswer

    path_a, path_b = Path(args.files[0]), Path(args.files[1])
    label_a = path_a.stem.replace("_results", "")
    label_b = path_b.stem.replace("_results", "")

    results_a = json.loads(path_a.read_text())
    results_b = json.loads(path_b.read_text())
    a_map = {r["case_id"]: r for r in results_a}
    b_map = {r["case_id"]: r for r in results_b}
    common_ids = sorted(set(a_map) & set(b_map))

    if not common_ids:
        print("No common case IDs between the two result files.")
        sys.exit(1)

    print(f"\nPairwise comparison: {label_a} vs {label_b} ({len(common_ids)} cases)\n")
    case_map = {c.id: c for c in ALL_CASES}

    def _make_response(data: dict) -> AgentResponse:
        searches = [
            SearchResult(
                query=s["query"], title=s.get("title"),
                content=s.get("content"), url=s.get("url"), error=s.get("error"),
            )
            for s in data.get("searches", [])
        ]
        structured = StructuredAnswer(
            answer=data.get("answer", ""), reasoning=data.get("reasoning", ""),
            confidence=data.get("confidence", "low"), sources_used=data.get("sources_used", []),
            limitations=data.get("limitations"), declined=data.get("declined", False),
        )
        return AgentResponse(
            answer=data["answer"], structured=structured, searches=searches,
            trace=data.get("trace", []),
            prompt_version=data.get("prompt_version", ""), iterations=data.get("iterations", 0),
        )

    pairwise_results = []
    for i, case_id in enumerate(common_ids, 1):
        case = case_map.get(case_id)
        if not case:
            continue
        ra = _make_response(a_map[case_id])
        rb = _make_response(b_map[case_id])
        print(f"  [{i:2}/{len(common_ids)}] {case_id:8} ...", end="", flush=True)
        try:
            pr = run_pairwise(case, ra, rb, label_a=label_a, label_b=label_b)
            pairwise_results.append(pr.to_dict())
            reg = " ⚠ REGRESSION" if pr.regressions else ""
            print(f" {pr.overall.winner} wins overall ({pr.b_wins}/4 dims for {label_b}){reg}")
        except Exception as exc:
            print(f" ERROR: {exc}")

    out_path = Path("results/comparison.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(pairwise_results, indent=2))
    print(f"\nResults saved to: {out_path}")

    # ── Regression statistics ─────────────────────────────────────────────────
    total = len(pairwise_results)
    dims = ["groundedness", "correctness", "completeness", "search_strategy"]

    print(f"\n{'='*60}")
    print(f"REGRESSION REPORT: {label_a} → {label_b}")
    print(f"{'='*60}")

    # PairwiseResult stores winners as "A" (baseline/label_a) and "B" (new/label_b), not version names.
    # Per-dimension win rates
    print(f"\n{'Dimension':<20} {label_b+' wins':>10} {label_a+' wins':>10} {'Ties':>6} {'B win%':>8}")
    print("-" * 60)
    for dim in dims:
        b_w = sum(1 for pr in pairwise_results if pr.get(dim, {}).get("winner") == "B")
        a_w = sum(1 for pr in pairwise_results if pr.get(dim, {}).get("winner") == "A")
        tie = sum(1 for pr in pairwise_results if pr.get(dim, {}).get("winner") == "tie")
        pct = round(b_w / total * 100, 1) if total else 0
        print(f"  {dim:<18} {b_w:>10} {a_w:>10} {tie:>6} {pct:>7}%")
    b_overall = sum(1 for pr in pairwise_results if pr.get("overall", {}).get("winner") == "B")
    a_overall = sum(1 for pr in pairwise_results if pr.get("overall", {}).get("winner") == "A")
    tie_overall = total - b_overall - a_overall
    print(f"  {'OVERALL':<18} {b_overall:>10} {a_overall:>10} {tie_overall:>6} {round(b_overall/total*100,1):>7}%")

    # Clear regressions (B worse than A on a dimension with clear confidence)
    regressions_by_dim: dict = defaultdict(list)
    for pr in pairwise_results:
        for dim in dims:
            d = pr.get(dim, {})
            if d.get("winner") == "A" and d.get("confidence") == "clear":
                regressions_by_dim[dim].append(pr["case_id"])

    print(f"\nCLEAR REGRESSIONS ({label_b} clearly worse than {label_a}):")
    any_regressions = False
    for dim in dims:
        cases = regressions_by_dim[dim]
        if cases:
            any_regressions = True
            print(f"  {dim}: {cases}")
    if not any_regressions:
        print(f"  None — {label_b} did not clearly regress on any dimension")

    # Clear improvements
    improvements_by_dim: dict = defaultdict(list)
    for pr in pairwise_results:
        for dim in dims:
            d = pr.get(dim, {})
            if d.get("winner") == "B" and d.get("confidence") == "clear":
                improvements_by_dim[dim].append(pr["case_id"])

    print(f"\nCLEAR IMPROVEMENTS ({label_b} clearly better than {label_a}):")
    any_improvements = False
    for dim in dims:
        cases = improvements_by_dim[dim]
        if cases:
            any_improvements = True
            print(f"  {dim}: {cases}")
    if not any_improvements:
        print(f"  None — no clear improvements detected")

    # Per-category breakdown
    cats: dict = defaultdict(lambda: defaultdict(int))
    for pr in pairwise_results:
        cat = pr.get("category", "unknown")
        winner = pr.get("overall", {}).get("winner", "tie")
        cats[cat][winner] += 1

    print(f"\nPER-CATEGORY BREAKDOWN (overall winner):")
    for cat, counts in sorted(cats.items()):
        b_w = counts.get("B", 0)
        a_w = counts.get("A", 0)
        t = counts.get("tie", 0)
        print(f"  {cat:<30} {label_b}:{b_w}  {label_a}:{a_w}  tie:{t}")

    print(f"\n{'='*60}\n")

    from evals.schema import EvalResult
    results_obj = [EvalResult(**r) for r in results_a]
    report = generate_report(
        results_obj,
        pairwise_results=pairwise_results,
        save_to=Path("results/comparison_report.md"),
    )
    print(report)


def cmd_report(args) -> None:
    """Re-generate a report from an existing results file without re-running evals."""
    from evals.schema import EvalResult
    data = json.loads(Path(args.file).read_text())
    results = [EvalResult(**r) for r in data]

    stem = Path(args.file).stem
    out = Path(f"results/{stem}_report.md")
    report = generate_report(results, save_to=out)
    print(report)


def main() -> None:
    versions = available_versions()

    parser = argparse.ArgumentParser(description="Wikipedia QA Eval Suite")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run the eval suite and generate report")
    run_p.add_argument("--prompt", choices=versions, default="v1")
    run_p.add_argument("--sources", nargs="+", help="Filter by source (hotpotqa, nq, squad, curated)")
    run_p.add_argument("--categories", nargs="+", help="Filter by category")
    run_p.add_argument("--retrievability", nargs="+", help="Filter by retrievability tier")
    run_p.add_argument("--save-traces", action="store_true", dest="save_traces")
    run_p.add_argument(
        "--no-resume", action="store_true", dest="no_resume",
        help="Re-run all cases from scratch, ignoring any checkpointed results",
    )

    cmp_p = sub.add_parser("compare", help="Pairwise comparison + report from two result files")
    cmp_p.add_argument("files", nargs=2, metavar="RESULTS_JSON")

    rep_p = sub.add_parser("report", help="Re-generate report from an existing results file")
    rep_p.add_argument("file", metavar="RESULTS_JSON")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
