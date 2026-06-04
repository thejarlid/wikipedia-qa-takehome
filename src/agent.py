"""Wikipedia QA agent: agentic loop with full trace capture and structured output."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.tools import search_wikipedia
import src.prompts as prompts

load_dotenv()

AGENT_MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 8
TRACES_DIR = Path(__file__).parent.parent / "traces"


# ── Output data structures ────────────────────────────────────────────────────

@dataclass
class SearchResult:
    query: str
    title: str | None
    content: str | None
    url: str | None
    error: str | None = None


@dataclass
class TraceStep:
    """One iteration of the agent loop: model reasoning + tool call + result."""
    step: int
    model_text: str
    """Text the model produced in this step — its visible reasoning before/after the tool call."""
    tool_name: str | None
    """'search_wikipedia', 'submit_answer', or None if the model ended without a tool call."""
    tool_input: dict | None
    tool_result: str | None
    """Raw string returned to the model from the tool."""


@dataclass
class StructuredAnswer:
    """Populated when the model calls submit_answer; otherwise synthesised from text."""
    answer: str
    reasoning: str
    confidence: str          # "high" | "medium" | "low"
    sources_used: list[str]
    limitations: str | None = None
    declined: bool = False
    """True when the model explicitly declined to answer (out-of-scope, etc.)."""
    from_submit_tool: bool = True
    """False when we fell back to text extraction (model didn't call submit_answer)."""


@dataclass
class AgentResponse:
    answer: str              # top-level shortcut to structured.answer
    structured: StructuredAnswer
    searches: list[SearchResult] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    prompt_version: str = "v1"
    model: str = AGENT_MODEL
    iterations: int = 0

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "structured": asdict(self.structured),
            "searches": [asdict(s) for s in self.searches],
            "trace": [asdict(t) for t in self.trace],
            "prompt_version": self.prompt_version,
            "model": self.model,
            "iterations": self.iterations,
        }


# ── Tool definition builders ──────────────────────────────────────────────────

def _build_search_tool(pv: prompts.PromptVersion) -> dict:
    return {
        "name": "search_wikipedia",
        "description": pv.tool_description,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": pv.tool_query_description,
                }
            },
            "required": ["query"],
        },
    }


def _build_submit_tool(pv: prompts.PromptVersion) -> dict:
    return {
        "name": "submit_answer",
        "description": pv.submit_tool_description,
        "input_schema": {
            "type": "object",
            "properties": {
                "declined": {
                    "type": "boolean",
                    "description": pv.submit_field_declined,
                },
                "answer": {
                    "type": "string",
                    "description": pv.submit_field_answer,
                },
                "reasoning": {
                    "type": "string",
                    "description": pv.submit_field_reasoning,
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": pv.submit_field_confidence,
                },
                "sources_used": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": pv.submit_field_sources,
                },
                "limitations": {
                    "type": "string",
                    "description": pv.submit_field_limitations,
                },
            },
            "required": ["declined", "answer", "reasoning", "confidence", "sources_used"],
        },
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def ask(
    question: str,
    prompt_version: str = "v1",
    save_trace: bool = False,
    case_id: str | None = None,
) -> AgentResponse:
    """Run the Wikipedia QA agent on a single question.

    Args:
        question: The question to answer.
        prompt_version: Which prompt version directory to load.
        save_trace: If True, write the full trace JSON to traces/.
        case_id: Optional identifier added to the trace filename.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    pv = prompts.load(prompt_version)
    search_tool = _build_search_tool(pv)
    submit_tool = _build_submit_tool(pv)
    all_tools = [search_tool, submit_tool]

    messages: list[dict] = [{"role": "user", "content": question}]
    searches: list[SearchResult] = []
    trace: list[TraceStep] = []
    iterations = 0

    while iterations < MAX_ITERATIONS:
        iterations += 1
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=2048,
            system=pv.system,
            tools=all_tools,
            messages=messages,
        )

        # Collect any text the model produced this step
        model_text = " ".join(
            b.text for b in response.content if hasattr(b, "text")
        ).strip()

        messages.append({"role": "assistant", "content": response.content})

        # ── Model finished with text (no tool call) ──
        if response.stop_reason == "end_turn":
            trace.append(TraceStep(
                step=iterations, model_text=model_text,
                tool_name=None, tool_input=None, tool_result=None,
            ))
            structured = StructuredAnswer(
                answer=model_text or "(no answer)",
                reasoning="(model ended without calling submit_answer)",
                confidence="low",
                sources_used=[s.title for s in searches if s.title],
                from_submit_tool=False,
            )
            response_obj = AgentResponse(
                answer=structured.answer, structured=structured,
                searches=searches, trace=trace,
                prompt_version=prompt_version, model=AGENT_MODEL, iterations=iterations,
            )
            if save_trace:
                _save_trace(response_obj, question, case_id)
            return response_obj

        # ── Model made tool calls ──
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                # ── submit_answer: structured termination ──
                if tool_name == "submit_answer":
                    trace.append(TraceStep(
                        step=iterations, model_text=model_text,
                        tool_name="submit_answer", tool_input=tool_input,
                        tool_result=None,
                    ))
                    structured = StructuredAnswer(
                        answer=tool_input.get("answer", ""),
                        reasoning=tool_input.get("reasoning", ""),
                        confidence=tool_input.get("confidence", "low"),
                        sources_used=tool_input.get("sources_used", []),
                        limitations=tool_input.get("limitations"),
                        declined=bool(tool_input.get("declined", False)),
                        from_submit_tool=True,
                    )
                    response_obj = AgentResponse(
                        answer=structured.answer, structured=structured,
                        searches=searches, trace=trace,
                        prompt_version=prompt_version, model=AGENT_MODEL, iterations=iterations,
                    )
                    if save_trace:
                        _save_trace(response_obj, question, case_id)
                    return response_obj

                # ── search_wikipedia ──
                if tool_name == "search_wikipedia":
                    query = tool_input.get("query", "")
                    result = search_wikipedia(query)
                    sr = SearchResult(
                        query=query,
                        title=result.get("title"),
                        content=result.get("content"),
                        url=result.get("url"),
                        error=result.get("error"),
                    )
                    searches.append(sr)
                    tool_result_str = _format_search_result(result)

                    trace.append(TraceStep(
                        step=iterations, model_text=model_text,
                        tool_name="search_wikipedia", tool_input={"query": query},
                        tool_result=tool_result_str,
                    ))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result_str,
                    })

            if tool_results:
                messages.append({"role": "user", "content": tool_results})
            continue

        # ── Unexpected stop reason ──
        trace.append(TraceStep(
            step=iterations, model_text=model_text,
            tool_name=None, tool_input=None, tool_result=None,
        ))
        break

    # ── Max iterations — force final answer ──
    response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=1024,
        system=pv.system,
        tools=all_tools,
        tool_choice={"type": "none"},
        messages=messages + [{
            "role": "user",
            "content": "Please submit your final answer now based on what you have found.",
        }],
    )
    fallback_text = " ".join(
        b.text for b in response.content if hasattr(b, "text")
    ).strip()
    structured = StructuredAnswer(
        answer=fallback_text or "(max iterations reached)",
        reasoning="(forced: max iterations reached)",
        confidence="low",
        sources_used=[s.title for s in searches if s.title],
        from_submit_tool=False,
    )
    response_obj = AgentResponse(
        answer=structured.answer, structured=structured,
        searches=searches, trace=trace,
        prompt_version=prompt_version, model=AGENT_MODEL, iterations=iterations,
    )
    if save_trace:
        _save_trace(response_obj, question, case_id)
    return response_obj


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_search_result(result: dict) -> str:
    if "error" in result:
        return f"[Wikipedia search error: {result['error']}]"
    return (
        f"Title: {result['title']}\n"
        f"URL: {result['url']}\n\n"
        f"{result['content']}"
    )


def _save_trace(response: AgentResponse, question: str, case_id: str | None) -> Path:
    TRACES_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = case_id or "manual"
    path = TRACES_DIR / f"{ts}_{slug}.json"
    payload = {"question": question, **response.to_dict()}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path
