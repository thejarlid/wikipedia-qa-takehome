# Design Decision Log

> Chronological record of significant design decisions, options considered, and reasoning.
> Never edited retroactively — only appended to as new decisions are made.
> Intended for retrospective analysis: what did we decide, why, and what would we revisit with more time?

---

## D-01 · Single tool: `search_wikipedia(query: str)` only

**Context:** The assignment specifies a single `search_wikipedia` tool. During implementation we encountered a question (Neymar's 2014 World Cup injury) where the answer exists on Wikipedia but is ~8,400 words into a 14,318-word article — well beyond any reasonable retrieval window. We discussed whether to add a second `get_wikipedia_section` tool.

**Options considered:**
- Add `get_wikipedia_section(title, section)` tool for progressive access
- Return the full article content (no truncation)
- Stay single-tool, tune for better queries and graceful degradation

**Decision:** Single tool only, as specified by the assignment.

**Reasoning:** The assignment explicitly asks to design a system for the `search_wikipedia(query: str)` tool. Adding tools shifts the challenge from prompt engineering to tool design. The more interesting and relevant work for this role is: how do you prompt the model to use a limited tool well, and how do you evaluate that?

**Tradeoffs accepted:** Some legitimate questions are structurally unanswerable with this tool (facts deep in article bodies). These become a feature of the eval design — an intentional "out-of-reach" tier that tests grounding discipline rather than factual accuracy.

**What we'd revisit with more time:** Section-level retrieval would meaningfully improve answer coverage. A `get_wikipedia_section` tool with proper prompting to guide when to use it would be a natural extension.

---

## D-02 · MediaWiki API over Wikipedia Python library

**Context:** The assignment allows any Wikipedia retrieval approach. We chose between the MediaWiki API directly vs. the `wikipedia` Python library (which wraps the API).

**Options considered:**
- `wikipedia` Python library
- Direct MediaWiki API via `requests`

**Decision:** Direct MediaWiki API.

**Reasoning:** More control over the exact parameters (redirect handling, extract format, search ranking). The library adds a dependency and abstracts away behavior we want to understand and tune. The API is stable and well-documented.

**Tradeoffs accepted:** Slightly more boilerplate. Rate limiting (429) requires explicit retry logic that the library handles internally.

---

## D-03 · Mandatory retrieval before answering

**Context:** Should the agent always search Wikipedia, or decide case-by-case whether to search?

**Options considered:**
- Conditional retrieval: agent decides when a search is needed
- Mandatory retrieval: agent must always search before answering

**Decision:** Mandatory retrieval.

**Reasoning:** Grounding is the core value proposition of this system. Allowing the agent to skip search and answer from training knowledge defeats the purpose and makes grounding quality impossible to evaluate cleanly. A system that sometimes searches and sometimes doesn't produces inconsistent, hard-to-audit behavior.

**Tradeoffs accepted:** Slightly higher latency and cost for simple questions. A sophisticated agent might correctly skip search for definitionally true statements ("Is 2+2=4?") — we accept that this system over-retrieves in those cases.

---

## D-04 · File-based prompt versioning (directory per version)

**Context:** How to store and version system prompts and tool definitions.

**Options considered:**
- Python constants in `prompts.py` (e.g., `PROMPT_V1 = "..."`)
- Separate `.md` files per version in a directory structure
- YAML config file per version

**Decision:** Directory per version (`prompts/v1/system.md` + `tool.md`).

**Reasoning:** Prompts are content, not code. Keeping them in `.md` files means: clean git diffs, proper text editing experience, easy to review changes without Python syntax noise. A new version is created by copying a directory and editing text — no Python changes needed.

The `tool.md` file uses a simple `---` separator: tool description above, query parameter description below. Both sections are prompt engineering surfaces that need to be versioned and iterated on together with the system prompt.

**Tradeoffs accepted:** Requires a file loader in `src/prompts.py`. Slightly more indirection than inline strings.

---

## D-05 · Tool description as a versioned prompt engineering artifact

**Context:** The tool definition (specifically: the `description` field and the `query` parameter description) directly shapes how the model uses the tool — when it calls it, and how it formulates queries. These are prompt engineering levers, not fixed infrastructure.

**Decision:** Version the tool description and query parameter description alongside the system prompt, as part of the same `prompts/v<N>/tool.md` file.

**Reasoning:** Query formulation behavior is one of the most important things to evaluate and improve. If the tool description says "use entity names," the model follows it. If it's vague, the model generates verbose full-sentence queries (which is exactly what we observed: the Neymar test produced queries like `"Neymar back injury fractured vertebra Juan Camilo Zúñiga"`). The tool description is part of the prompt — it should be versioned and diffed like the rest.

**Tradeoffs accepted:** Slightly more files per version. But the gain in explicitness and iterability is worth it.

---

## D-06 · 1000-word content limit (no `exintro` flag)

**Context:** The MediaWiki API's `exintro=1` flag returns only the lead section. We initially used it with a 600-word limit, then explored removing it.

**Options considered:**
- `exintro=1` (intro only): ~600 words
- No `exintro`, truncate to 800 words
- No `exintro`, truncate to 1000 words
- Return full article (no truncation)

**Decision:** No `exintro`, 1000-word truncation.

**Reasoning:** `exintro` was too restrictive — many articles have long lead sections and we were cutting off relevant content. Full articles (up to 14k+ words) would overwhelm context across multiple searches. 1000 words is a reasonable balance: covers full intro sections for most articles, captures some body content for shorter articles, keeps context cost manageable.

**Tradeoffs accepted:** Some facts remain structurally out of reach (e.g., the Neymar 2014 World Cup injury detail at word ~8,400). These cases are explicitly categorized in the eval dataset as `retrievability: "out_of_reach"` and evaluated on different criteria (grounding discipline + honest acknowledgment rather than factual correctness).

---

## D-07 · Eval retrievability tiers

**Context:** During early testing (Neymar injury question), we discovered that the question "was the search strategy correct?" and "was the answer correct?" are separable. A model can make a perfect query, get the right article, and still not find the answer — because the fact is too deep in the article.

**Decision:** Classify all test cases into three retrievability tiers with different success criteria.

| Tier | Success criteria |
|------|-----------------|
| `direct` | Correct answer + grounded in retrieved text |
| `strategic` | Correct multi-hop search chain + correct answer |
| `out_of_reach` | Correct search strategy + honest acknowledgment of limitation (no hallucination) |

**Reasoning:** Treating all cases with the same "correct answer?" rubric would unfairly penalize the system for tool limitations and reward hallucination (a model that makes up the answer looks "correct" even when Wikipedia didn't provide it). Separating the dimensions gives a more honest picture of what the prompt engineering is actually accomplishing.

**Tradeoffs accepted:** More complex eval logic (different checks apply to different tiers). More complex to explain in the writeup. Worth it for honest measurement.

---

## D-08 · V1 is intentionally sparse

**Context:** We could have written a comprehensive v1 prompt and iterated from there. Instead, v1 is deliberately missing certain guidance to create predictable, measurable failure modes.

**Intentional gaps in v1:**
- No structured multi-step reasoning guidance
- Minimal sourcing instruction ("At the end produce your sources")
- No explicit grounding discipline for out-of-reach cases

**Decision:** Keep v1 sparse. Write v2 after running real evals on v1.

**Reasoning:** The eval-driven iteration story (v1 → evals → insights → v2) is only compelling if v1 has real, observed failures — not hypothetical ones. Writing v2 before running evals would make the iteration feel post-hoc. We want to be able to say: "We ran v1, saw that multi-hop triggered only X% of the time on cases that required it, and added explicit multi-step guidance in v2 to address that."

**Tradeoffs accepted:** v1 will perform worse than it could. That's the point.

---

## D-09 · HotpotQA for multi-hop eval cases

**Context:** We needed a source of multi-hop questions with verifiable ground truth and known supporting Wikipedia articles.

**Decision:** Use the HotpotQA dataset (bridge type, medium/hard difficulty) as the backbone of the multi-hop test cases.

**Reasoning:** HotpotQA is ideal for this use case: each question is explicitly designed to require chaining two Wikipedia articles, and the dataset provides both the expected answer (short string) and the `supporting_facts` field (which Wikipedia article titles contain the answer). The `supporting_facts` titles enable a deterministic `required_articles_searched` check — we can verify the agent searched the right articles, not just that it got the right answer.

Filter criteria:
- Type: `bridge` (sequential lookup, not comparison)
- Level: `medium` / `hard`
- Exclude time-sensitive questions (elections, records, "current" state)

**Tradeoffs accepted:** HotpotQA is from 2018 — some facts may be outdated. Time-stable filtering mitigates but doesn't eliminate this. Noted as a limitation in the writeup.

---

## D-10 · Separate specialized LLM judges per eval dimension

**Context:** How to structure LLM-based evaluation.

**Options considered:**
- Single judge with multi-criteria rubric
- Multiple independent judges, one per dimension
- Majority vote across multiple independent judge instances

**Decision:** Separate specialized judges per dimension (grounding, factuality, query quality).

**Reasoning:** A single multi-criteria judge conflates dimensions that behave differently and may trade off against each other. A grounding failure (hallucinating facts) and a factuality failure (getting the right fact from the wrong source) are distinct problems that require distinct remediation. Separating them gives clearer signal for which prompt changes to make.

Using `claude-haiku-4-5-20251001` for judges (vs. Sonnet for the agent): keeps eval cost manageable for bulk runs across ~45 cases × 2 prompt versions × 3 judges.

**Tradeoffs accepted:** More API calls per eval run. Each judge operates without awareness of the other dimensions, which could miss interactions (e.g., a highly grounded answer that is factually wrong).

Using `claude-haiku-4-5-20251001` for completeness and search_strategy (mechanical checks); Sonnet for groundedness, correctness, and pairwise (reasoning-heavy). All judges use `temperature=0` and system prompt caching (`cache_control: ephemeral`) to reduce cost and ensure determinism.

---

## D-11 · `submit_answer` tool for structured output + full trace capture

**Context:** The agent was returning plain text answers with no machine-readable structure. For evals we need: a stable answer field, confidence signal, reasoning, and sources. We also had no visibility into what the model was thinking between tool calls.

**Options considered:**
- Parse unstructured text with regex/heuristics
- Add a `submit_answer` tool the model calls to finalize
- Use extended thinking (separate reasoning tokens)

**Decision:** Add `submit_answer` as a second tool. The model calls it to submit: `answer`, `reasoning`, `confidence` (high/medium/low), `sources_used`, and `limitations`. The agentic loop captures every step (model text + tool call + result) into a `TraceStep` list.

**Reasoning:** Tool use naturally enforces structure — no parsing needed. The `submit_answer` schema makes confidence and limitations first-class fields, directly usable as eval signals. The full trace captures the model's visible reasoning at each step, enabling post-hoc analysis of *why* the model made each search decision.

**Tradeoffs accepted:** Adds one more tool to the definition, slightly increasing prompt complexity. The model may sometimes end with `end_turn` without calling `submit_answer` (v1 lacks explicit instruction to use it) — we fall back to text extraction and mark `from_submit_tool=False`.

**Reasoning/confidence not surfaced to users:** These fields are internal — captured in trace JSON for eval pipelines, not displayed in the REPL. The user-facing output stays clean: searches + answer only.

---

## D-12 · Dataset composition: 46 cases across 4 sources

**Context:** Designed a representative eval dataset covering multiple failure modes and question types.

**Decision:** 46 cases: 16 HotpotQA (bridge + comparison), 10 Natural Questions, 10 SQuAD 2.0 false premise, 10 curated adversarial.

**Retrievability labeling:** Every case is labeled `direct`, `strategic`, or `out_of_reach`. Out-of-reach cases (4 total) have inverted success criteria: we check for honest acknowledgment and absence of hallucination rather than correct factual answer. This distinction is critical — without it, a model that fabricates the answer would score "correct" on a case where the information was structurally inaccessible.

**SQuAD false premise rationale:** Chose questions where the premise is factually inverted or wrong (not just "answer absent from excerpt"). These specifically test whether the agent propagates false claims vs. identifying and correcting them. Sourced from 5 different Wikipedia articles for topical diversity.

**Adversarial rationale:** Out-of-scope cases test scope adherence (v1 gap). Prompt injection (direct + roleplay) and jargon obfuscation test robustness against override attempts. Misconception cases test whether the agent faithfully reports Wikipedia rather than reinforcing myths.

**Tradeoffs accepted:** 46 cases × 2 prompt versions × 3 judges = substantial API cost per full eval run. Kept intentionally lean — signal density over volume.

---

## D-12b · Judges operate from primary evidence, not deterministic check results

**Context:** Considered whether to pass deterministic check results (e.g. `key_facts_present=False`, `required_articles_covered=False`) to LLM judges as helpful priors.

**Decision:** Judges receive only primary evidence — the question, answer, retrieved Wikipedia content, and raw search trace. They do NOT receive deterministic check outcomes or failure tags.

**Reasoning:**
1. **Anchoring risk.** A judge that sees `key_facts_present=False` may defer to that verdict rather than independently assessing whether the answer is correct. Deterministic checks can have false negatives (the fact is present but phrased differently from the expected substring).
2. **Cascade errors.** A wrong deterministic result would corrupt the judge's score with no way to detect the error.
3. **Independent signal.** The value of having two layers is that they measure independently. If judges see check results, their output conflates "what the check found" with "what I assess" — the layers are no longer independent.

**What judges DO receive:** Raw behavioral facts that ARE primary evidence — search count, query strings, article titles retrieved, the answer text, the Wikipedia content. These are inputs to reasoning, not conclusions.

**Where combination happens:** The synthesis report and failure taxonomy aggregate deterministic + judge findings after both layers have formed independent views.

**Connection to pairwise / RLAIF:** The pairwise judge is also kept clean — it compares the two answers from primary evidence only. This mirrors how Constitutional AI preference learning works: the preference signal comes from direct comparison of outputs, not from pre-labelled quality scores.

---

## D-13 · Static HTML dashboard generated from result JSON

**Context:** Needed a way to inspect eval results visually — not just terminal output. Considered a web app, a notebook, and a static HTML file.

**Decision:** Python script (`generate_dashboard.py`) reads `results/*.json` and outputs a single self-contained `dashboard.html` with all data embedded. Uses Chart.js from CDN, vanilla JS, no framework.

**Reasoning:** Static HTML is the simplest artifact to share — open the file, done. No server, no build step, no dependencies. The data is embedded as a JS constant so the file works offline. The script is regenerated after each eval run, not served dynamically.

**What it shows:** Metric tiles (pass rate, avg score — color-coded), radar chart (per-dimension averages), horizontal bar chart (pass rate by category), line trend chart (scores over multiple runs for regression tracking), LLM synthesis narrative, searchable/filterable case table with expandable rows showing full answer, search trace, and all judge reports with score bars and reasoning text. Compare tab for two-run delta view.

**Tradeoffs accepted:** Embedding all data in the HTML means the file grows with each run (roughly 10-15KB per case). Fine for 46 cases (~600KB), would need pagination for thousands.

---

## D-14 · Checkpointing and resume for eval runs

**Context:** A full eval run (46 cases × 4 judges + synthesis) takes significant time and API calls. Without safeguards, a crash at case 30 loses all progress.

**Decision:** Single JSON file per prompt version (`results/v1_results.json`), written after every case. Resume mode is the default: on restart, completed case IDs are loaded and skipped. Three-tier retry logic for recoverable errors.

**Options considered:**
- JSONL append-only format (efficient writes, harder to read)
- Individual per-case files (creates directory noise, previously implemented)
- Single JSON rewritten after each case (chosen)

**Reasoning:** Rewriting ~500KB JSON 46 times is negligible I/O. Single-file format is easier to inspect, load in the dashboard, and pass to the compare command. The resume logic is simple: load existing results, extract case IDs, skip any case already present.

**Retry tiers:**
- `RateLimitError` → wait 30/60/120s, retry 3×
- `InternalServerError` / `APIConnectionError` → wait 5/15/30s, retry 3×
- `AuthenticationError` → save progress, stop suite (fatal)
- Unknown errors → retry once, then record a placeholder `EvalResult` with `failure_tags: ["eval_error"]`

**Tradeoffs accepted:** If a case fails all retries, it's recorded as a failure (not silently dropped). This means eval results are always complete — every case has an entry — which simplifies downstream analysis.

---

## D-15 · Four specialized pairwise judges with RLAIF-inspired preference framing

**Context:** Original pairwise used one general Sonnet call to assess all four eval dimensions at once. This conflates dimensions and reduces accuracy — a judge trying to assess groundedness, correctness, completeness, and search strategy simultaneously produces less reliable signal than one focused on each.

**Decision:** Each specialized judge (`groundedness`, `correctness`, `completeness`, `search_strategy`) has its own `run_pairwise()` function using its dimension-specific rubric. All four run concurrently. Overall winner is derived by majority vote — no separate "overall" judge call.

**RLAIF framing:** The pairwise suffix appended to each judge's system prompt frames the task as preference expression rather than rubric application: *"which response would you rather a user receive?"* This elicits a more holistic, human-like preference signal consistent with Constitutional AI / RLAIF methodology. The rubric gives vocabulary for failure tags but the output is binary preference.

**Completeness judge:** Uses Sonnet for pairwise (vs. Haiku for single-response evaluation). Comparative reasoning benefits from a stronger model even when scoring a single response doesn't.

**Regression detection:** `PairwiseResult.regressions` property returns dimension names where the new version clearly lost (winner=old, confidence=clear). Surfaced in the `compare` command output.

**Tradeoffs accepted:** 4× more API calls per case for pairwise runs. Worthwhile — reliability of each dimension's preference signal is meaningfully higher, and the regression breakdown per dimension is the actionable output for prompt iteration.

---

## D-16 · `fact_retrieval_diagnosis` — 4-state diagnostic check

**Context:** The `key_facts_present` check is binary — it tells you a fact is missing but not why. Missing facts have fundamentally different root causes that require different prompt fixes.

**Decision:** Add `fact_retrieval_diagnosis` check that disambiguates missing facts into 4 states: extraction_failure (had it, didn't use it), fact_beyond_cutoff (right article, beyond window), retrieval_failure (wrong article), grounding_failure (fact in answer but not in retrieved content).

**Reasoning:** These states require different interventions. Extraction failure → improve grounding discipline in prompt. Retrieval failure → improve query formulation guidance. Beyond cutoff → system constraint, don't penalise the prompt score. Grounding failure → the most serious: model used training knowledge instead of Wikipedia.

The grounding_failure state is a deterministic hallucination signal — no LLM judge needed. If a fact appears in the answer but in none of the retrieved Wikipedia content, the source must be training data.

**Why this matters for prompt iteration:** Without this disambiguation, you might add more multi-hop guidance to fix what is actually a grounding failure, or tighten grounding rules to fix what is actually a retrieval failure. The tags route the fix to the correct prompt section.

**Tradeoffs accepted:** The B/C distinction (fact_beyond_cutoff vs retrieval_failure) is inferred from article-title matching when enrichment data is absent. Enrichment makes it exact. Run `enrich_dataset.py` for confirmed determinations.

---

## D-17 · Dataset enrichment — pre-computing fact locations

**Context:** The `fact_retrieval_diagnosis` check needs to know whether a missing fact exists in the full Wikipedia article (beyond our 1000-word window) or doesn't exist at all. Without this, states B (beyond cutoff) and C (wrong article) can only be inferred from whether the right article was searched.

**Decision:** `scripts/enrich_dataset.py` fetches the full Wikipedia article for each case's `supporting_articles` and checks: (1) is any key fact in the first 1000 words? (2) is any key fact anywhere in the full article? Results stored in `evals/dataset/enrichment.json`, merged into TestCase at load time.

**Key findings from enrichment run:**
- 38/43 enriched cases: facts in 1000-word window (direct retrieval expected to work)
- 2 cases beyond cutoff: `SQ-E` (Warsaw ranking), `CA-05` (Great Wall visibility myth)
- 3 cases not in Wikipedia: `H-10` (Eenasul Fateh — no article), `NQ-13` (Papa's Got a Brand New Bag — apostrophe fetch issue), `SQ-J` (Bohemond — key fact phrasing too specific)

**Tradeoffs accepted:** Enrichment requires full article fetches — heavier than our normal tool calls. Rate limiting required 1.5s between requests and exponential backoff. Run once at dataset build time, not at eval time.

---

## D-18 · AmbigQA considered, deferred to Phase 2

**Context:** AmbigQA (14k questions derived from NQ-open, ~50% ambiguous) was evaluated as a potential dataset addition. It includes `viewed_doc_titles` (Wikipedia articles annotators looked at) and `used_queries` (actual search queries used).

**Decision:** Defer. Add to dataset in a future iteration rather than before the first eval loop.

**Reasoning:** The `used_queries` field is the most valuable thing AmbigQA offers — a human oracle for search strategy comparison that our current cases lack. The `viewed_doc_titles` is a marginally more reliable `supporting_articles` but not transformationally different from our manual labeling. Our 46 cases are already enriched and well-characterized; rebuilding would lose that.

**What we'd take:** 5-8 `multipleQAs` cases from `entity_references` and `event_references` ambiguity types, plus a `human_oracle_queries` field on TestCase populated from `used_queries` for search strategy judge reference. The `multipleQAs` cases test ambiguity handling — a failure mode our current dataset doesn't cover at all.

**What we'd revisit:** After seeing v0/v1/v2 results, if ambiguity handling emerges as a systematic failure pattern, add AmbigQA cases and the `human_oracle_queries` field in the next dataset iteration.

---

## D-19 · v0 as bare-bones baseline for the iteration story

**Context:** For the prompt engineering narrative to be compelling, we need a clear low baseline that shows measurable improvement across versions. A prompt that's already "pretty good" makes small improvements hard to see.

**Decision:** v0 is a two-sentence prompt — "You are a helpful assistant with access to Wikipedia. Use it to answer questions." Tool descriptions carry all structural guidance. This establishes a floor that's clearly below v1.

**Purpose:** v0 is not a production candidate. It exists to establish the failure mode baseline — the synthesis report from v0 directly informs what v1 should fix, which informs what v2 should fix. Each prompt version has a specific target derived from actual eval failures, not hypothetical ones.

**Iteration approach:**
- v0 → v1: Address the 4 failure patterns identified in v0 synthesis (false premises, oversearch, grounding, cutoff)
- v1 → v2: Address whatever patterns persist or are newly revealed in v1 eval
- Each version is evaluated and compared pairwise to its predecessor

---

## D-20 · v2 design: worked examples, multi-hop scaffold, hard-case taxonomy

**Context:** v1 ran at 73.9% pass rate (87.74 composite). v1 synthesis identified four remaining failure clusters: (A) false premise propagation still at 8 occurrences despite Step 1 in v1, (B) wrong_article/verbose_query persisting (12/8 occurrences) despite the "entity name" rule, (C) poor chain reasoning and undersearch on multi-hop questions (4/4), and (D) misconception category at 0% with no v1 guidance for distinguishing popular-belief questions from fact questions.

**Decision:** Three targeted interventions, plus two supporting additions:

1. **Worked examples for every key rule.** v1 had abstract rules ("verify the premise before searching"). v2 adds concrete examples (Napoleon entrance exam, Columbus in Caribbean, Vivaldi nationality) that show the exact behavior — not what to do in principle, but what to say word-for-word. This is the most impactful change: abstract rules are interpreted loosely; examples bind the behavior.

2. **Explicit multi-hop decomposition section.** v1 implied multi-hop chaining ("search again if you need more info") but gave no procedure. v2 adds a dedicated section: identify the intermediate entity, search it, extract the bridging fact, use that as input to the next search, synthesize only after all hops. This directly targets poor_chain_reasoning and undersearch.

3. **Hard Cases section with misconception rule.** v1 was silent on misconception questions (e.g. "Do humans only use 10% of their brains?"). v2 adds: treat the question's claim as a hypothesis, search the topic, report what Wikipedia actually says rather than confirming the myth. Also explicitly covers prompt injection and out-of-scope handling.

4. **Search Query Craft table.** v1 gave Good/Bad examples in prose. v2 adds a reference table (Instead of / Search for) with 4 canonical examples. The table format makes scanning and recall easier.

5. **Core Values framing.** "Honesty over helpfulness" and "Intellectual humility" as explicit values cover cases where the rules are silent — giving the model a meta-principle to apply when it encounters an edge case not covered by any specific instruction.

**What was NOT changed:** The 4-search hard cap (effective in reducing oversearch), the `submit_answer` tool, the grounding verification step. These performed well in v1 and were left intact.

**Reasoning for each choice:** See `PROMPT_ENGINEERING.md` → v2 section for the full failure-tag → prompt-change mapping.

**Tradeoffs accepted:** v2 is significantly longer than v1 (~1100 words vs. ~350 words). Longer prompts risk attention diffusion — the model may not apply all rules consistently across a long response. This is an explicit hypothesis to test: if v2 improves on targeted dimensions but degrades on others, the prompt may be too long and need consolidation in v3.

---

## D-20b · Eval recalibration — removing SQ-H and SQ-I

**Context:** After running v2, the same failure patterns kept appearing in two squad_false_premise cases (SQ-H, SQ-I) regardless of what the prompt did. Repeated inspection showed these weren't prompt failures — they were dataset validity failures.

- **SQ-H:** "What battle took place in the 10th century?" — The original SQuAD question was grounded in a specific passage. Without that passage, the question is underspecified: dozens of battles occurred in the 10th century. Our tool returns a legitimate Wikipedia article that doesn't contain the expected answer because the expected answer only makes sense in the original passage context. Failure tags: `retrieval_failure`, `false_premise_propagated`, `hallucination`.
- **SQ-I:** "What treaty was established in the 9th century?" — Same structural problem. The question is too vague to have a retrievable ground-truth answer outside its original SQuAD passage context. Failure tags: `fact_beyond_cutoff`, `wrong_article`, `verbose_query`.

**Decision:** Remove SQ-H and SQ-I from the eval set. Dataset shrinks from 46 to 44 cases.

**Reasoning:** An eval case should test whether the agent behaved correctly given a solvable problem. These two cases have no correct answer that our tool can retrieve — not because of the retrieval window, but because the question itself is only answerable with the original SQuAD passage that we don't provide. Keeping them would mean any prompt that fails these cases gets penalized for a data problem, not a behavior problem. That corrupts the failure signal.

**What distinguishes this from `out_of_reach`:** Out-of-reach cases have a knowable correct answer that's beyond our window. SQ-H and SQ-I don't have a well-defined correct answer at all without the original passage.

**Tradeoffs accepted:** Removing cases mid-experiment requires a control run (D-20c) to confirm the calibration change didn't artificially inflate scores.

---

## D-20c · v4 as a control experiment — isolating prompt improvement from eval calibration

**Context:** After removing SQ-H and SQ-I, scores improved when running v3. A legitimate question arises: is the improvement from the better prompt, or from the easier eval set?

**Decision:** Run v2's prompt on the recalibrated (44-case) eval set as a control. Call this v4.

**Results:**
- v4 (v2 prompt, recalibrated evals): **77.3%** (34/44)
- v3 (v3 prompt, recalibrated evals): **93.2%** (41/44)

**What this proves:** The 15.9-point gap between v4 and v3 on the identical eval set is attributable solely to the prompt change. The eval calibration alone (v2 on old evals: 79.5% → v4 on new evals: 77.3%) had a negligible or slightly negative effect — it did not inflate scores.

**Category-level confirmation:** v4 on recalibrated evals still shows `squad_false_premise` at 25% and `misconception` at 0% — the same failure patterns as v2. v3 shows `squad_false_premise` at 75% and `misconception` at 50%. The failures that moved were exactly the categories v3's prompt targeted.

**Design principle:** Any time an eval set changes mid-experiment, run the prior best prompt on the new set before claiming the new prompt is responsible for score changes. Without this control, improvements are confounded.

---

## D-21 · v3 is the prompt ceiling — v5 confirms where prompt engineering ends

**Context:** After v3 achieved 93.2%, we attempted v5 targeting remaining failures: query length constraint (≤5 keywords), a pivot rule ("reformulate with different term, not a longer version"), an explicit Step 5 premise-confirmation check, and a 3-consecutive-miss stopping heuristic. v5 regressed: hotpotqa_bridge 100% → 84.6%, squad_false_premise 75% → 62.5%, overall 93.2% → 86.4%.

**Decision:** Accept v3 as the prompt ceiling for the current tool design. Do not pursue further prompt iteration.

**Why v5 regressed:**
1. The query pivot rule ("reformulate with completely different term") conflicts with multi-hop chain completion, where the agent needs to refine toward an intermediate entity rather than pivot to something entirely different.
2. The Step 5 premise-confirmation check ("does the retrieved text confirm the key assumption?") stacks with v3's Step 2 narrow-exception trap, creating double deliberation that causes the agent to second-guess valid intermediate facts in bridge chains.
3. The combination of v3's extended cognitive load + v5's additional constraints exceeded the model's ability to apply all rules coherently across a long response.

**What the ceiling means:** The 3 remaining failures at v3 are structurally identical — all are `out_of_reach` cases where the answer is past the 1000-word retrieval window. No prompt change can extend the retrieval window. The binding constraint is the tool, not the prompt.

**What would break through the ceiling:** A `get_section(title, section_name)` tool for targeted deep retrieval. With the current single-call `search_wikipedia`, the agent cannot access article content past the first 1000 words, which is where the correcting text lives for CA-05, SQ-C, SQ-E, and SQ-G. This is the natural "extend with more time" direction.

---
