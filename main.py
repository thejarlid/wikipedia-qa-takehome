#!/usr/bin/env python3
"""Wikipedia QA Agent — interactive REPL, demo mode, and single-question mode."""

import argparse

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from src.agent import ask
from src.prompts import available_versions

console = Console()

DEMO_QUESTIONS = [
    "Who was the first person to walk on the moon, and what was the name of the mission?",
    "What is the nationality of the director of the film Parasite?",
    "What injury did Neymar sustain in the 2014 world cup?",
    "Who invented the telephone?",
    "What did Marie Curie win Nobel Prizes for, and in what years?",
]

CONFIDENCE_STYLE = {"high": "green", "medium": "yellow", "low": "red"}


def run_question(
    question: str,
    prompt_version: str = "v3",
    show_trace: bool = False,
    save_trace: bool = False,
) -> None:
    console.print(f"\n[bold cyan]Question:[/bold cyan] {question}\n")
    with console.status("[dim]Searching Wikipedia...[/dim]", spinner="dots"):
        result = ask(question, prompt_version=prompt_version, save_trace=save_trace)

    # ── Search trace ──────────────────────────────────────────────────────────
    if result.searches:
        console.print(Rule("[dim]Wikipedia searches[/dim]", style="dim"))
        for i, s in enumerate(result.searches, 1):
            if s.error:
                console.print(f"  [dim]{i}.[/dim] [red]✗[/red] [dim]{s.query!r}[/dim] → {s.error}")
            else:
                console.print(
                    f"  [dim]{i}.[/dim] [green]✓[/green] [dim]{s.query!r}[/dim] "
                    f"→ [link={s.url}]{s.title}[/link]"
                )
        console.print()

    # ── Answer ────────────────────────────────────────────────────────────────
    console.print(Rule("[dim]Answer[/dim]", style="dim"))
    console.print(Markdown(result.answer))

    # Reasoning, confidence, and limitations are intentionally not shown here —
    # they are captured in the structured output and trace for eval use only.

    # ── Full step-by-step trace (--trace flag) ────────────────────────────────
    if show_trace and result.trace:
        console.print()
        console.print(Rule("[dim]Full agent trace[/dim]", style="dim"))
        for step in result.trace:
            console.print(f"\n[bold]Step {step.step}[/bold]")
            if step.model_text:
                console.print(f"  [dim]Model:[/dim] {step.model_text[:300]}")
            if step.tool_name:
                console.print(f"  [dim]Tool:[/dim] [cyan]{step.tool_name}[/cyan]")
                console.print(f"  [dim]Input:[/dim] {step.tool_input}")
            if step.tool_result:
                snippet = step.tool_result[:200].replace("\n", " ")
                console.print(f"  [dim]Result:[/dim] {snippet}…")

    console.print(
        f"\n[dim]  ({result.iterations} iteration(s), "
        f"prompt={result.prompt_version}, model={result.model}"
        f"{', trace saved' if save_trace else ''})[/dim]\n"
    )


def repl_mode(prompt_version: str, show_trace: bool, save_trace: bool) -> None:
    console.print(Panel(
        Text.from_markup(
            "[bold]Wikipedia QA Agent[/bold]\n\n"
            "Ask any factual question — the agent always retrieves evidence from Wikipedia.\n"
            "Type [bold cyan]exit[/bold cyan] or press [bold cyan]Ctrl-C[/bold cyan] to quit.",
        ),
        title="[bold green]Ready[/bold green]",
        border_style="green",
    ))
    while True:
        try:
            question = console.input("\n[bold cyan]>[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            console.print("[dim]Goodbye.[/dim]")
            break
        run_question(question, prompt_version=prompt_version,
                     show_trace=show_trace, save_trace=save_trace)


def demo_mode(prompt_version: str, show_trace: bool, save_trace: bool) -> None:
    console.print(Panel(
        "[bold]Wikipedia QA Agent — Demo Mode[/bold]\n\n"
        "Running a curated set of questions that showcase multi-hop reasoning,\n"
        "misconception handling, and disambiguation.",
        title="[bold yellow]Demo[/bold yellow]",
        border_style="yellow",
    ))
    for q in DEMO_QUESTIONS:
        run_question(q, prompt_version=prompt_version,
                     show_trace=show_trace, save_trace=save_trace)
        console.input("[dim]  Press Enter for next question...[/dim]")


def main() -> None:
    versions = available_versions()
    parser = argparse.ArgumentParser(
        description="Wikipedia QA Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python main.py                           # interactive REPL\n"
            '  python main.py "Who invented the radio?" # single question\n'
            "  python main.py --demo                    # demo mode (6 curated questions)\n"
            "  python main.py --prompt v2               # use a different prompt version\n"
            "  python main.py --trace                   # show full agent reasoning trace\n"
            "  python main.py --save-trace              # save trace JSON to traces/\n"
        ),
    )
    parser.add_argument("question", nargs="?", help="Ask a single question and exit")
    parser.add_argument("--demo", action="store_true", help="Run demo questions")
    parser.add_argument(
        "--prompt", choices=versions, default="v3",
        help=f"Prompt version (available: {', '.join(versions)}). Default: v3 (best performing)",
    )
    parser.add_argument(
        "--trace", action="store_true",
        help="Print full step-by-step agent reasoning trace",
    )
    parser.add_argument(
        "--save-trace", action="store_true", dest="save_trace",
        help="Save full trace JSON to traces/",
    )
    args = parser.parse_args()

    if args.demo:
        demo_mode(args.prompt, show_trace=args.trace, save_trace=args.save_trace)
    elif args.question:
        run_question(args.question, prompt_version=args.prompt,
                     show_trace=args.trace, save_trace=args.save_trace)
    else:
        repl_mode(args.prompt, show_trace=args.trace, save_trace=args.save_trace)


if __name__ == "__main__":
    main()
