"""Base judge infrastructure: shared client, prompt caching, temperature=0."""

from __future__ import annotations

import json
import os
import re

import anthropic
from dotenv import load_dotenv

from evals.schema import JudgeResult

load_dotenv()

SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"

# Appended to every judge system prompt to enforce JSON-only output.
# Positioned at the very end so it's the last instruction the model sees.
_JSON_ENFORCEMENT = """

CRITICAL OUTPUT REQUIREMENT: Your entire response must be a single valid JSON object.
Do not write any explanation, analysis, or text before or after the JSON.
Start your response with { and end it with }. Nothing else."""

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _extract_json(raw: str) -> dict:
    """Try multiple strategies to extract a JSON object from model output.

    Strategy 1 — Direct parse (model followed instructions perfectly).
    Strategy 2 — Strip markdown code fence (```json ... ``` or ``` ... ```).
    Strategy 3 — Brace matching: find the outermost { ... } block anywhere
                 in the text (handles prose wrapping the JSON).

    Raises json.JSONDecodeError if no valid JSON object found.
    """
    raw = raw.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from code fence
    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: brace matching — find the outermost complete JSON object
    start = raw.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(raw)):
            ch = raw[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    raise json.JSONDecodeError("No valid JSON object found in response", raw, 0)


def _retry_for_json(
    client: anthropic.Anthropic,
    model: str,
    system_prompt: str,
    user_message: str,
    bad_response: str,
) -> str:
    """One correction turn when the first response wasn't valid JSON."""
    retry = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0,
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": bad_response},
            {
                "role": "user",
                "content": (
                    "Your response was not valid JSON. "
                    "Please provide only the JSON object — nothing else. "
                    "Start with { and end with }."
                ),
            },
        ],
    )
    return retry.content[0].text.strip()


def judge_call(
    model: str,
    system_prompt: str,
    user_message: str,
    judge_name: str,
    pass_threshold: int,
) -> JudgeResult:
    """Make a single judge API call with caching and temperature=0.

    The system_prompt is cached — identical across all cases for a given judge.
    If the first response isn't valid JSON, one correction turn is attempted
    before falling back to a parse-error result.
    """
    client = get_client()
    full_system = system_prompt + _JSON_ENFORCEMENT

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0,
        system=[{"type": "text", "text": full_system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()

    try:
        data = _extract_json(raw)
    except json.JSONDecodeError:
        # One correction turn
        raw = _retry_for_json(client, model, full_system, user_message, raw)
        try:
            data = _extract_json(raw)
        except json.JSONDecodeError:
            return JudgeResult(
                judge_name=judge_name,
                model=model,
                score=1,
                reasoning=f"JSON parse error after retry. Raw: {raw[:400]}",
                failure_tags=["judge_parse_error"],
                passed=False,
            )

    score = int(data.get("score", 1))
    return JudgeResult(
        judge_name=judge_name,
        model=model,
        score=score,
        reasoning=data.get("reasoning", ""),
        failure_tags=data.get("failure_tags", []),
        passed=score >= pass_threshold,
    )


_PAIRWISE_SUFFIX = """

PREFERENCE COMPARISON: You are comparing two responses (A and B) to the same question.
Your job is to express a genuine preference — which response would you rather a user receive?
Use the rubric above as the lens through which you evaluate, but your output is a preference signal,
not a score. Ask yourself: if you could only give a user one of these responses, which would you choose?

A "clear" preference means one response is meaningfully better. A "slight" preference means both
are similar but one has a small edge. "tie" means both are genuinely equivalent.

Respond with valid JSON only:
{
  "winner": "A" | "B" | "tie",
  "confidence": "clear" | "slight",
  "reasoning": "<concise explanation of your preference — what specifically makes one better>",
  "failure_tags_A": [<failure tags from the rubric taxonomy that apply to A>],
  "failure_tags_B": [<failure tags from the rubric taxonomy that apply to B>]
}"""


def pairwise_call(
    model: str,
    system_prompt: str,
    user_message: str,
) -> dict:
    """Pairwise comparison call with retry on parse failure."""
    client = get_client()
    full_system = system_prompt + _PAIRWISE_SUFFIX + _JSON_ENFORCEMENT

    response = client.messages.create(
        model=model,
        max_tokens=768,
        temperature=0,
        system=[{"type": "text", "text": full_system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()

    try:
        return _extract_json(raw)
    except json.JSONDecodeError:
        raw = _retry_for_json(client, model, full_system, user_message, raw)
        try:
            return _extract_json(raw)
        except json.JSONDecodeError:
            return {
                "winner": "tie",
                "confidence": "slight",
                "reasoning": f"parse error after retry: {raw[:300]}",
                "failure_tags_A": [],
                "failure_tags_B": [],
            }
