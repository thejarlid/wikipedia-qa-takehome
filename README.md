# Wikipedia QA Agent — Anthropic Take-Home

A Wikipedia-grounded QA agent built on Claude. The agent always retrieves from Wikipedia before answering — every factual claim traces back to a retrieved source. Includes a full evaluation suite with deterministic checks, LLM judges, pairwise comparison, and a visual dashboard.

---

## Write-up

For the design rationale, prompt engineering approach, eval methodology, and results analysis, read **[Writeup.md](./Writeup.md)**.

The files in `docs/` — `DESIGN.md`, `DECISIONS.md`, and `PROMPT_ENGINEERING.md` — are working artifacts created during the build process. They document technical decisions, per-version prompt analysis, and the full iteration log in more detail than the write-up covers.

---

## Eval results summary

Eval calibration was applied after v2 (see `docs/PROMPT_ENGINEERING.md`). v4 = v2 prompt on calibrated eval, used to isolate calibration from prompt effects.

| Version | Eval | Composite | Pass Rate | Key changes |
|---------|------|-----------|-----------|-------------|
| v0 | original | 81.03 | 69.6% (32/46) | Baseline — 2-sentence prompt |
| v1 | original | 87.74 | 73.9% (34/46) | Premise check, 4-search cap, grounding, cutoff |
| v2 | original | 89.35 | 79.5% (35/44) | Multi-hop scaffold, worked examples, query craft table |
| v4 | calibrated | 91.39 | 77.3% (34/44) | v2 prompt re-run — calibration effect ≈0 |
| v3 | calibrated | 95.63 | **93.2% (41/44)** | Narrow-exception trap, delete-not-hedge grounding — **best version** |
| v5 | calibrated | 93.64 | 86.4% (38/44) | Further tightening — regressed bridge questions, confirmed v3 ceiling |

See `docs/PROMPT_ENGINEERING.md` for per-version failure analysis and `results/` for raw eval JSON.

---

## Setup

**1. Run the setup script**
```bash
bash setup.sh
```
Creates a `.venv/` virtual environment, installs dependencies, and copies `.env.example` → `.env`. Requires Python 3.10+.

**2. Add your API key**
```bash
# Edit .env and set:
ANTHROPIC_API_KEY=sk-ant-...
```

**3. Activate and verify**
```bash
source .venv/bin/activate
python main.py "Who invented the telephone?"
```

> All subsequent commands assume the venv is active.

---

## CLI — Ask questions

```bash
python main.py                                       # interactive REPL
python main.py "What is the capital of Australia?"  # single question
python main.py --demo                                # 6 preset showcase questions
python main.py --prompt v3                           # use a specific prompt version
python main.py --trace "Who directed Parasite?"      # show step-by-step reasoning
python main.py --save-trace                          # also write trace JSON to traces/
```

---

## Evals — Run the evaluation suite

```bash
# Run the full suite (44 cases) — checkpoints after every case, safe to interrupt and resume
python run_evals.py run --prompt v1

# Re-run from scratch, ignoring checkpointed results
python run_evals.py run --prompt v1 --no-resume

# Filter by source, category, or retrievability tier
python run_evals.py run --prompt v1 --categories nq_factual misconception
python run_evals.py run --prompt v1 --retrievability direct strategic

# Pairwise comparison between two prompt versions
python run_evals.py compare results/v1_results.json results/v2_results.json

# Re-generate a report from saved results without re-running
python run_evals.py report results/v1_results.json
```

Produces `results/<version>_results.json` and prints a synthesis report. Add `--save-traces` to also write per-case trace JSON (with full Wikipedia content) to `traces/`.

---

## Dashboard — Visual inspection

```bash
python generate_dashboard.py
open dashboard.html    # macOS — use xdg-open (Linux) or start (Windows)
```

Per-run metrics, radar chart, category breakdown, and a searchable case table with full traces and judge reports. Compare tab shows delta tiles and regression highlighting across two runs.

---

## Prompt versions

Prompts live in `prompts/<version>/` as plain text files. To iterate:

```bash
cp -r prompts/v3 prompts/v6
# Edit prompts/v6/system.md, tool.md, tool_submit_answer.md
python run_evals.py run --prompt v6
python run_evals.py compare results/v3_results.json results/v6_results.json
```

| File | Contents |
|------|----------|
| `system.md` | Full system prompt |
| `tool.md` | `search_wikipedia` description (above `---`) + query param description (below `---`) |
| `tool_submit_answer.md` | `submit_answer` — 6 field descriptions separated by `---` |

---

## Project structure

```
main.py                    # CLI entrypoint (REPL, demo, single-question)
run_evals.py               # Eval suite CLI (run, compare, report)
generate_dashboard.py      # Static HTML dashboard generator

src/
  agent.py                 # Agentic loop, structured output, trace capture
  tools.py                 # search_wikipedia() — MediaWiki API
  prompts.py               # File-based prompt version loader

prompts/
  v0/                      # Bare-bones baseline (2 sentences — intentionally minimal)
  v1/                      # Premise check, search cap, grounding, cutoff handling
  v2/                      # Worked examples, multi-hop scaffold, query craft table
  v3/                      # Narrow-exception trap, delete-not-hedge grounding (best version)
  v4/                      # v2 prompt re-run on calibrated eval (calibration control)
  v5/                      # Further tightening — confirmed v3 as ceiling

evals/
  dataset/                 # 44 eval cases (HotpotQA, NQ, SQuAD, curated)
  checks.py                # Deterministic assertion checks
  judges/                  # LLM judges (groundedness, correctness, completeness, search_strategy, pairwise)
  runner.py                # Orchestration with checkpointing and retry logic
  report.py                # Synthesis report generator
  schema.py                # EvalResult, CheckResult, JudgeResult dataclasses

results/                   # One JSON per prompt version (v1_results.json, etc.)
traces/                    # Full trace JSONs (written only with --save-traces)
dashboard.html             # Generated dashboard (run generate_dashboard.py first)

docs/
  DESIGN.md                # Living technical reference
  DECISIONS.md             # Chronological design decision log
  PROMPT_ENGINEERING.md    # Per-version prompt analysis and iteration log
```

---

## Eval dataset (44 cases)

| Source | Count | What it tests |
|--------|-------|---------------|
| HotpotQA (bridge) | 13 | Multi-hop: chain two Wikipedia articles |
| HotpotQA (comparison) | 3 | Compare facts across two articles |
| Natural Questions | 10 | Direct single-hop factual lookup |
| SQuAD 2.0 (false premise) | 8 | Questions with embedded wrong assumptions |
| Custom adversarial | 10 | Out-of-scope, misconceptions, prompt injection, jargon obfuscation |

Every case is labelled `direct` / `strategic` / `out_of_reach` — out-of-reach cases have different success criteria (honest acknowledgment, no hallucination) rather than factual correctness.
