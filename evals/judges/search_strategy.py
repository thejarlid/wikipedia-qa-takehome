"""Search strategy judge — Sonnet.

Evaluates query formulation, article selection, and search depth.
Receives the full agent reasoning trace so it can assess not just WHAT was
searched but WHY — the model's thinking between each tool call reveals whether
the search strategy was deliberate and well-reasoned.
"""

from __future__ import annotations

from evals.dataset.schema import TestCase
from evals.judges.base import SONNET, judge_call, pairwise_call
from evals.schema import JudgeResult
from src.agent import AgentResponse

_SYSTEM = """\
You are evaluating the search strategy used by a Wikipedia QA agent. You have access to:
1. The agent's reasoning trace — what it was thinking at each step before making a tool call.
2. The searches it made — the exact queries and which articles were retrieved.

Use both to assess: Were the queries well-formed? Did the agent identify the right articles to search? Was the search depth appropriate? Did the agent reason clearly about what it needed at each step?

RUBRIC (score 1–5):
5 – OPTIMAL: Clean entity-name queries, correct articles retrieved, appropriate search count (1–2 for simple, 2–4 for multi-hop). Reasoning shows clear search planning.
4 – GOOD: Minor inefficiency (one extra search or slightly imprecise query), but core strategy correct and reasoning is sound.
3 – ADEQUATE: Found relevant content but with poor query formulation (full sentences, redundant searches), OR reasoning doesn't explain search choices well.
2 – POOR: Missed key articles OR persistently verbose queries OR reasoning shows confused strategy OR excessive searches (5+) for a simple question.
1 – FAILING: Wrong articles throughout, no coherent strategy, answered without searching, or 6+ searches with no clear reasoning about why.

SPECIAL CASES:
- If retrievability is "out_of_reach": The expected answer is not reliably findable in Wikipedia. Score 4–5 if the agent made reasonable, entity-focused search attempts and ultimately acknowledged it could not find the answer. Do NOT penalize for failing to retrieve expected articles that don't exist or are beyond Wikipedia's coverage. Penalize only for clearly wrong query strategies (e.g., searching completely irrelevant terms, not searching at all).

FAILURE TAGS — include all that apply:
- "verbose_query": One or more queries were full sentences rather than entity names or short phrases.
- "wrong_article": Retrieved articles are not relevant to the question.
- "undersearch": Fewer searches than needed (e.g. multi-hop answered with one search).
- "oversearch": More than 4 searches for a question needing 1–2.
- "missing_search": No search was attempted at all.
- "poor_chain_reasoning": For multi-hop questions, the agent didn't reason clearly about the intermediate entity it needed to find.

PASS threshold: score ≥ 3.

Respond with valid JSON only:
{
  "score": <integer 1–5>,
  "reasoning": "<assessment of query quality, article selection, search depth, and reasoning clarity>",
  "failure_tags": [<zero or more tags>]
}"""


def run(case: TestCase, response: AgentResponse) -> JudgeResult:
    # Build a step-by-step trace narrative combining model reasoning + tool calls
    trace_lines = []
    for t in response.trace:
        lines = [f"Step {t.step}:"]
        if t.model_text:
            lines.append(f"  Model reasoning: {t.model_text[:400]}")
        if t.tool_name == "search_wikipedia":
            query = (t.tool_input or {}).get("query", "?")
            # Find the corresponding search result (match by query)
            result = next(
                (s for s in response.searches if s.query == query),
                None,
            )
            article = result.title if result and result.title else "(not found)"
            error = f" [ERROR: {result.error}]" if result and result.error else ""
            lines.append(f"  → search_wikipedia({query!r}) → {article}{error}")
        elif t.tool_name == "submit_answer":
            answer_preview = (t.tool_input or {}).get("answer", "")[:120]
            lines.append(f"  → submit_answer(...) answer: {answer_preview!r}")
        elif t.tool_name:
            lines.append(f"  → {t.tool_name}({t.tool_input})")
        trace_lines.append("\n".join(lines))

    trace_summary = "\n\n".join(trace_lines) if trace_lines else "(no trace available)"

    # Also provide a clean search summary for quick reference
    search_lines = []
    for i, s in enumerate(response.searches, 1):
        title = s.title or "(not found)"
        error = f" [ERROR: {s.error}]" if s.error else ""
        search_lines.append(f"  {i}. {s.query!r} → {title}{error}")
    search_summary = "\n".join(search_lines) if search_lines else "  (no searches made)"

    user_msg = f"""\
Question: {case.question}
Multi-hop required: {case.requires_multihop}
Retrievability: {case.retrievability}
Expected articles to find: {case.supporting_articles}

## Agent reasoning trace ({len(response.trace)} steps):
{trace_summary}

## Search summary ({len(response.searches)} searches):
{search_summary}

Evaluate the search strategy using both the trace and the search summary."""

    return judge_call(
        model=SONNET,
        system_prompt=_SYSTEM,
        user_message=user_msg,
        judge_name="search_strategy",
        pass_threshold=3,
    )


def run_pairwise(
    case: TestCase,
    response_a: AgentResponse,
    response_b: AgentResponse,
    label_a: str = "A",
    label_b: str = "B",
) -> dict:
    """Compare two responses on search strategy using the search strategy rubric."""
    def _trace_summary(resp: AgentResponse, label: str) -> str:
        def _f(t, key):  # handles both TraceStep dataclass and plain dict
            return t.get(key) if isinstance(t, dict) else getattr(t, key, None)
        lines = []
        for t in resp.trace:
            text = _f(t, "model_text")
            tool = _f(t, "tool_name")
            inp  = _f(t, "tool_input") or {}
            if text:
                lines.append(f"  Reasoning: {str(text)[:200]}")
            if tool == "search_wikipedia":
                q = inp.get("query", "?") if isinstance(inp, dict) else "?"
                result = next((s for s in resp.searches if s.query == q), None)
                article = result.title if result and result.title else "(not found)"
                lines.append(f"  → search({q!r}) → {article}")
        return "\n".join(lines) if lines else "(no trace)"

    def _search_summary(resp: AgentResponse) -> str:
        return "\n".join(
            f"  {i}. {s.query!r} → {s.title or '(not found)'}"
            for i, s in enumerate(resp.searches, 1)
        ) or "  (none)"

    user_msg = (
        f"Question: {case.question}\n"
        f"Multi-hop required: {case.requires_multihop}\n"
        f"Expected articles: {case.supporting_articles}\n\n"
        f"## Response {label_a} — trace:\n{_trace_summary(response_a, label_a)}\n"
        f"## Response {label_a} — searches:\n{_search_summary(response_a)}\n\n"
        f"## Response {label_b} — trace:\n{_trace_summary(response_b, label_b)}\n"
        f"## Response {label_b} — searches:\n{_search_summary(response_b)}\n\n"
        "Compare search strategy: which version searched more effectively?"
    )
    return pairwise_call(model=SONNET, system_prompt=_SYSTEM, user_message=user_msg)
