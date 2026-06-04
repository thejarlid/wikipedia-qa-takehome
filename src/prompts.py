"""Load versioned prompt files from the prompts/ directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@dataclass(frozen=True)
class PromptVersion:
    version: str
    system: str
    # search_wikipedia tool
    tool_description: str
    tool_query_description: str
    # submit_answer tool — descriptions for each field (split by ---)
    submit_tool_description: str
    submit_field_declined: str
    submit_field_answer: str
    submit_field_reasoning: str
    submit_field_confidence: str
    submit_field_sources: str
    submit_field_limitations: str


def load(version: str) -> PromptVersion:
    """Load a prompt version from prompts/<version>/."""
    base = PROMPTS_DIR / version
    if not base.is_dir():
        available = [d.name for d in PROMPTS_DIR.iterdir() if d.is_dir()]
        raise ValueError(f"Unknown prompt version {version!r}. Available: {available}")

    system = (base / "system.md").read_text().strip()

    # search_wikipedia tool: description --- query param description
    raw_tool = (base / "tool.md").read_text()
    parts = raw_tool.split("---", maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"prompts/{version}/tool.md must contain exactly one '---' separator")

    # submit_answer tool: description --- answer --- reasoning --- confidence --- sources --- limitations
    raw_submit = (base / "tool_submit_answer.md").read_text()
    submit_parts = [p.strip() for p in raw_submit.split("---")]
    if len(submit_parts) != 7:
        raise ValueError(
            f"prompts/{version}/tool_submit_answer.md must have exactly 6 '---' separators "
            f"(got {len(submit_parts) - 1})"
        )

    return PromptVersion(
        version=version,
        system=system,
        tool_description=parts[0].strip(),
        tool_query_description=parts[1].strip(),
        submit_tool_description=submit_parts[0],
        submit_field_declined=submit_parts[1],
        submit_field_answer=submit_parts[2],
        submit_field_reasoning=submit_parts[3],
        submit_field_confidence=submit_parts[4],
        submit_field_sources=submit_parts[5],
        submit_field_limitations=submit_parts[6],
    )


def available_versions() -> list[str]:
    return sorted(d.name for d in PROMPTS_DIR.iterdir() if d.is_dir())
