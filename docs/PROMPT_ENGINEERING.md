# Prompt Engineering Log

> Living document. Tracks each prompt version: design intent, changes made, what failure patterns it targets, and eval results. Updated after every eval run and iteration.

The prompt engineering loop:
1. Run eval → synthesis report surfaces failure patterns with failure tags
2. Identify which patterns are prompt-fixable vs. system-level constraints
3. Write next version targeting specific tags
4. Run eval + pairwise comparison → measure delta per dimension
5. Repeat

---

## Version Summary

**Eval note:** v0–v2 ran on the original eval suite. Calibration applied after v2 (key_facts ANY, search_strategy out_of_reach rule, pairwise bug fix). v3+ run on calibrated eval. v4 = v2 prompt re-run on calibrated eval to isolate calibration effect from prompt effect.

| Version | Prompt | Eval | Composite | Pass Rate | Key change |
|---------|--------|------|-----------|-----------|------------|
| v0 | v0 | original | 81.03 | 69.6% (32/46) | Baseline — no guidance |
| v1 | v1 | original | 87.74 | 73.9% (34/46) | Structured steps, grounding requirement, 4-search cap |
| v2 | v2 | original | 89.35 | 79.5% (35/44) | Multi-hop scaffold, worked examples, query craft table |
| v4 | v2 | **calibrated** | 91.39 | 77.3% (34/44) | Same prompt as v2 — isolates calibration effect (≈0 net) |
| v3 | v3 | **calibrated** | 95.63 | 93.2% (41/44) | Narrow-exception trap, delete-not-hedge grounding |
| v5 | v5 | **calibrated** | 93.64 | 86.4% (38/44) | Query constraints + stopping heuristic — regression from v3 |

**Clean attribution:**
- Prompt progression (original eval): v0 → v1 → v2 = +9.9pp (+8.32 composite)
- Calibration effect (v2 prompt): v2 79.5% → v4 77.3% = **≈0** (within non-determinism noise)
- Prompt improvement v2→v3 (both calibrated): v4 77.3% → v3 93.2% = **+15.9pp (+4.24 composite)** — genuine
- v5 over-tightened: hotpotqa_bridge 100%→84.6%, squad_false_premise 75%→62.5% — **v3 is the prompt ceiling**

---

## Cross-Version Failure Class Evolution

This table tracks the key failure classes across iterations. It's the primary tool for understanding which prompt changes actually moved the needle and which failures are structural vs. prompt-addressable.

### Search Targeting (finding the right article)

| Tag | v0 | v1 | v1 Δ | v2 target? | v2 expected |
|-----|----|----|-------|------------|-------------|
| `verbose_query` | 11 | 8 | ↓ improved | Yes (query craft table) | Should drop further |
| `wrong_article` | 7 | 12 | ↑ **worse** | Yes (query craft table + examples) | Should drop |
| `oversearch` | 9 | 6 | ↓ improved | Partial (4-search cap remains) | Stable |
| `undersearch` | — | 4 | new | Yes (multi-hop section) | Should drop |
| `retrieval_failure` | — | 5 | new | Yes (query craft guidance) | Should drop |

The `wrong_article` regression (7→12) in v1 is the key counter-intuitive finding. The 4-search cap likely caused the model to commit to wrong articles rather than retrying. v2's search query craft table addresses this differently: improve article selection quality rather than just capping search count.

### Reasoning Quality (correct inference from retrieved content)

| Tag | v0 | v1 | v1 Δ | v2 target? | v2 expected |
|-----|----|----|-------|------------|-------------|
| `false_premise_propagated` | 6 | 8 | ↑ **worse** | Yes (worked examples) | Should drop significantly |
| `poor_chain_reasoning` | — | 4 | new | Yes (multi-hop section) | Should drop |
| `unanswerable_not_acknowledged` | 3 | 3 | ↔ same | Partial (Hard Cases section) | Moderate improvement |
| `overclaiming` | 3 | 4 | ↑ slightly worse | Yes (Step 5 verify grounding) | Should stabilize |

`false_premise_propagated` going up (6→8) despite v1's Step 1 is the most important insight: having a rule ("check the premise") is insufficient. The model needs a worked example showing *how* to challenge a wrong premise and *what to say*. v2 addresses this with three explicit examples.

### Grounding Discipline (answering only from retrieved text)

| Tag | v0 | v1 | v1 Δ | v2 target? | v2 expected |
|-----|----|----|-------|------------|-------------|
| `grounding_failure` | 6 | 2 | ↓ **significantly improved** | No (v1 fix worked) | Should remain low |
| `extraction_failure` | 7 | 5 | ↓ improved | No | Should remain stable |
| `answer_exceeds_retrieval_window` | — | 5 | new | Partial (Hard Cases: "when Wikipedia doesn't have the answer") | Moderate improvement |

Grounding is v1's clearest win. The explicit "quote or closely paraphrase" requirement in Step 3 substantially reduced hallucination from retrieved content.

### Knowledge Limitations (system constraints, not prompt failures)

| Tag | v0 | v1 | v1 Δ | v2 target? | v2 expected |
|-----|----|----|-------|------------|-------------|
| `fact_beyond_cutoff` | 12 | 11 | ↔ marginal | Minimal (Hard Cases: acknowledge rather than infer) | Small improvement |

These are structural — the 1000-word retrieval window means some facts are simply out of reach. The eval tiers (`out_of_reach`) handle these with different success criteria. Prompt changes can improve *acknowledgment* but can't extend retrieval.

### Robustness (adversarial and edge cases)

| Category | v0 pass rate | v1 pass rate | v1 Δ | v2 target? | v2 expected |
|----------|-------------|-------------|-------|------------|-------------|
| `misconception` | 50% (1/2) | 0% (0/2) | ↓ **regression** | Yes (Hard Cases section) | Should recover |
| `out_of_scope` | 100% | 100% | ✅ stable | No | Stable |
| `prompt_injection` | 100% | 100% | ✅ stable | No | Stable |

The `misconception` regression from 50%→0% in v1 is unexpected. v1's premise-verification step may be causing the model to search for confirmation of the premise rather than testing it as a hypothesis. v2 adds an explicit rule: for misconception-type questions, treat the claim as a hypothesis and report what Wikipedia says.

### Category-Level Pass Rates

Note: v4 = v2 prompt on calibrated eval (baseline isolation). Best performing version per category marked **bold**.

| Category | v0 | v1 | v2 | v4 (v2 cal.) | v3 | v5 |
|----------|----|----|----|----|----|----|
| `hotpotqa_bridge` | 76.9% | 92.3% | 92.3% | 92.3% | **100%** | 84.6% |
| `hotpotqa_comparison` | 100% | 100% | 100% | 100% | 100% | 100% |
| `nq_factual` | 100% | 100% | 90% | 100% | 100% | 100% |
| `squad_false_premise` | 10% | 10% | 37.5% | 25% | **75%** | 62.5% |
| `out_of_scope` | 100% | 100% | 100% | 100% | 100% | 100% |
| `misconception` | 50% | 0% | 0% | 0% | **50%** | **50%** |
| `false_premise` | 100% | 100% | 100% | 0% | 100% | 100% |
| `jargon_obfuscation` | 100% | 100% | 100% | 100% | 100% | 100% |
| `disambiguation` | 0% | 100% | 100% | 100% | 100% | 100% |
| `prompt_injection` | 100% | 100% | 100% | 100% | 100% | 100% |
| **out_of_reach tier** | 0% | 0% | 0% | **40%** | **60%** | **60%** |

**What this tells us about where to move the needle:**
- `squad_false_premise` (10% in both v0 and v1) is the clearest opportunity for v2 — it's unambiguously stuck, directly targeted by v2's worked examples and premise-check guidance.
- `misconception` regression is a quick win: v2 adds an explicit rule for this case class, so recovery to 50%+ is expected.
- `hotpotqa_bridge` improvement (76.9%→92.3%) was driven by grounding improvements in v1. Further improvement in v2 is possible via explicit multi-hop scaffold.
- Everything at 100% should be monitored for regression — if v2's added length causes attention diffusion, these may slip.

---

## v0 — Bare-bones Baseline

**Intent:** Establish a floor. No guidance beyond "use Wikipedia to answer questions." All structural behavior (search invocation, submit tool usage) comes from tool descriptions alone, not from system prompt reasoning.

**System prompt:** 2 sentences. Mentions the search tool and submit tool. No rules.

**Tool descriptions:** Same as v1 — carry full query guidance with Good/Bad examples and submit_answer field descriptions.

**Expected failures (hypotheses before eval):**
- False premise questions → model will accept premise and answer as-asked
- Multi-hop questions → model may stop after first search without chaining
- Out-of-scope questions → may attempt to answer despite no scope guidance
- Prompt injection → model may follow instructions in user message

**Actual v0 eval results:**

*Composite score:* 81.03 | *Pass rate:* 69.6% (32/46)

**Synthesis findings (verbatim from v0 report):**

> Pattern A: False Premise Blindness (squad_false_premise: 10% pass rate)
> The dominant failure cluster. Tags false_premise_propagated (6), unanswerable_not_acknowledged (3), and overclaiming (3) all point to the same root: when a question embeds a false or unverifiable premise, the system accepts it and fabricates an answer rather than challenging it.

> Pattern B: Retrieval Inefficiency (verbose_query + oversearch + wrong_article)
> Tags verbose_query (11), oversearch (9), and wrong_article (7) cluster together. The agent is issuing over-specified queries, landing on wrong articles, then compensating by searching repeatedly. out_of_reach retrievability is 0% (4/4 failed), confirming the agent has no graceful degradation when the right article isn't found.

> Pattern C: Extraction and Grounding Failures
> extraction_failure (7) and grounding_failure (6) indicate the agent retrieves the right content but either pulls the wrong span or fails to anchor its answer to retrieved text. Groundedness judge average (4.16) is the lowest dimension.

> Pattern D: Knowledge Cutoff Mishandling
> fact_beyond_cutoff (12) is the second-highest tag. The agent attempts to answer time-sensitive questions using Wikipedia snapshots without flagging staleness, producing wrong_answer (17, the top tag) as a downstream effect.

**Top failure tags (v0):**

| Tag | Count | Pattern |
|-----|-------|---------|
| `wrong_answer` | 17 | — |
| `fact_beyond_cutoff` | 12 | D |
| `verbose_query` | 11 | B |
| `oversearch` | 9 | B |
| `extraction_failure` | 7 | C |
| `wrong_article` | 7 | B |
| `grounding_failure` | 6 | C |
| `false_premise_propagated` | 6 | A |
| `unanswerable_not_acknowledged` | 3 | A/D |
| `overclaiming` | 3 | A/D |

**v0 → v1 decisions:**
- Pattern A (false premises): Add explicit premise verification step before searching
- Pattern B (oversearch): Add 4-search hard cap; add graceful degradation rule
- Pattern C (grounding): Replace vague "only state what Wikipedia confirms" with traceable standard (quote/paraphrase requirement)
- Pattern D (cutoff): Add time-sensitivity caveat instruction

---

## v1 — Structured Guidance

**Intent:** Address all four v0 failure patterns with targeted, measurable prompt additions. Each section corresponds to one failure cluster.

**Changes from v0:**

| Section added | Targets |
|---------------|---------|
| "Step 1 — Verify the premise before searching" | Pattern A: false_premise_propagated |
| "Step 2 — Search with entity names, stop after 4 attempts" | Pattern B: verbose_query, oversearch, wrong_article |
| "Step 3 — Ground your answer directly in retrieved text" | Pattern C: extraction_failure, grounding_failure |
| "Step 4 — Flag time-sensitive or out-of-reach information" | Pattern D: fact_beyond_cutoff, overclaiming |
| "Step 5 — Cite your sources" | Consistency of citation |

**Key design choices:**

*Step 1 (premise verification)* runs before the first search, not after. The model must identify the question's assumption, then check it against what Wikipedia says. The Napoleon example concretizes the behavior: if Wikipedia says he didn't fail his entrance exam, report that instead of searching for a year.

*Step 2 (search limit = 4)* gives a hard stop. Pattern B was the model overcompensating for bad queries by trying variations — the 4-search cap forces a fix-or-acknowledge decision rather than thrashing.

*Step 3 (grounding)* replaces vague "only state what Wikipedia confirms" with a traceable standard. "Quote or closely paraphrase" is something the model can verify about its own output before submitting.

*Step 4 (time-sensitivity)* is lightweight — a caveat instruction, not a new research step. Should reduce `fact_beyond_cutoff` tagging by encouraging acknowledgment rather than confident wrong answers.

**Expected improvements (hypotheses):**
- `false_premise_propagated`: should drop significantly (direct target of Step 1)
- `verbose_query` / `oversearch`: should drop (Step 2 hard cap + entity-name enforcement)
- `grounding_failure` / `extraction_failure`: should drop (Step 3 traceability requirement)
- `fact_beyond_cutoff` / `overclaiming`: should drop (Step 4 caveat instruction)
- `wrong_answer`: should drop as a downstream effect of the above

**Expected non-improvements:**
- `retrieval_failure` (wrong article): Step 2 helps query format but not article selection judgment
- Multi-hop cases: Step 2 says "search again if needed" but doesn't give a structured chaining procedure — may still undersearch on complex chains

**Actual v1 eval results:**

*Composite score:* 87.74 | *Pass rate:* 73.9% (34/46)

**Improvements over v0:**
- Groundedness: 4.16 → 4.74 (pass rate 81.4% → 93.0%) — Step 3 grounding requirement worked
- Search strategy: 3.67 → 3.86 (pass rate 86%) — some improvement from 4-search cap
- Bridge questions: hotpotqa_bridge 76.9% → 92.3%
- `oversearch` dropped: 9 → 6; `verbose_query` dropped: 11 → 8; `grounding_failure` dropped: 6 → 2

**Remaining failures (v1 → what v2 targets):**
- `squad_false_premise` still 10% — premise detection exists but not concrete enough; needs worked examples
- `wrong_article` persists (12): query craft still too loose; needs explicit table + rules
- `false_premise_propagated` persists (8): rule exists in v1 but no example of *how* to challenge a wrong premise
- `poor_chain_reasoning` (4), `undersearch` (4): multi-hop decomposition still not explicit
- `misconception` 0%: v1 has no guidance on treating popular-belief questions differently

**Top failure tags (v1):**

| Tag | Count | Pattern |
|-----|-------|---------|
| `wrong_answer` | 14 | — downstream |
| `wrong_article` | 12 | B |
| `fact_beyond_cutoff` | 11 | D |
| `verbose_query` | 8 | B |
| `false_premise_propagated` | 8 | A |
| `oversearch` | 6 | B |
| `extraction_failure` | 5 | C |
| `retrieval_failure` | 5 | B |
| `answer_exceeds_retrieval_window` | 5 | D |
| `undersearch` | 4 | C |
| `poor_chain_reasoning` | 4 | C |
| `overclaiming` | 4 | A/D |

---

## v2 — Structured Process + Worked Examples

**Intent:** Three-pronged attack on v1's remaining failure clusters: (A) false premise + misconception with concrete worked examples, (B) search query craft with explicit rules + table, (C) multi-hop decomposition with explicit chaining step. Also adds Core Values framing, search tool mechanics explanation, and Hard Cases section covering prompt injection, misconceptions, and out-of-scope requests.

**Changes from v1:**

| Section added/changed | Targets |
|----------------------|---------|
| Core Values (Honesty over helpfulness, Precision over completeness, Intellectual humility) | Framing — grounds all behaviors in explicit values |
| "Understanding Your Search Tool" — explains title-match vs semantic-match | `wrong_article`, `verbose_query` — explains *why* entity-name queries are required |
| Renamed to "Think, Plan, Search, Verify, Answer" 5-step process | Structural clarity for all patterns |
| Step 2 (Check the premise) — added Napoleon false-premise *example* | `false_premise_propagated` — worked example shows the correction behavior |
| Step 3 (Plan your searches) — explicit chain decomposition for multi-hop | `poor_chain_reasoning`, `undersearch` — "what do I need first? what does that unlock?" |
| Step 4 (Search and extract) — "did I find what I needed?" after each result | `oversearch`, `extraction_failure` |
| Step 5 (Verify grounding) — "can I point to the exact sentence?" | `overclaiming`, `grounding_failure` |
| Search Query Craft table (Instead of / Search for) | `verbose_query`, `wrong_article` — concrete examples bind behavior |
| Multi-hop Questions section — numbered 3-step chain procedure | `poor_chain_reasoning`, `undersearch` |
| Hard Cases section — Misconceptions, False-premise, Out-of-scope, Prompt injection, Wikipedia gaps | `misconception` (0% in v1), robustness to prompt injection |
| Citing Sources — named examples of citation language | Groundedness consistency |

**Key design choices:**

*Worked examples* throughout (Napoleon, Columbus, Darwin, Vivaldi) — v1 had only abstract rules; v2 binds each rule to a concrete case. The example is not decoration; it's the primary specification of the behavior.

*Search Query Craft table* explicitly lists bad-query forms. v1 said "use entity names" but the model was still using question-sentence queries. The table shows the exact anti-pattern to avoid.

*Multi-hop decomposition* is now a first-class step: identify the intermediate entity, search it, extract the bridge fact, then search the next entity. v1 implied this but didn't scaffold it.

*Misconceptions* get their own rule: treat the question's claim as a hypothesis to test, then report what Wikipedia says. v1 had no such guidance, which caused the 0% pass rate on `misconception` cases.

*Core Values* are new — they provide a meta-level guide when rules conflict or are silent (e.g., when Wikipedia is ambiguous, "Honesty over helpfulness" says don't paper over the gap).

**Expected improvements:**
- `false_premise_propagated`: should drop further (worked examples + explicit check-premise step with Napoleon example)
- `verbose_query` / `wrong_article`: should drop (query craft table with exact bad-query patterns shown)
- `poor_chain_reasoning` / `undersearch`: should drop (explicit multi-hop section)
- `misconception`: should improve from 0% (now explicitly handled in Hard Cases)
- `prompt_injection` resistance: already 100% in v1, should stay 100%

**Expected non-improvements:**
- `fact_beyond_cutoff`: system constraint — 1000-word window; prompt additions help acknowledgment but not retrieval
- `squad_false_premise` category may still be hard — some cases require detecting subtle embedded assumptions

**Actual v2 eval results:**

*Composite score:* 89.35 | *Pass rate:* 79.5% (35/44) — 2 cases had eval errors and were excluded

**Improvements over v1:**
- squad_false_premise: 10% → 37.5% (1/10 → 3/8 comparable cases) — biggest win; worked examples helped
- search_strategy judge: 3.86 → 4.2 avg (86% → 92.7% pass) — query craft table had clear effect
- correctness judge: 4.44 → 4.61 avg (86% → 92.7% pass) — better false premise detection
- false_premise_propagated: dropped from 8 → 3 — worked examples improved premise detection
- verbose_query: dropped from 8 → 2 — query craft table directly targeted this
- wrong_article: dropped from 12 → 7 — better query formulation helped article selection

**No improvement:**
- misconception: 0% in both v1 and v2 — CA-05 is out_of_reach (debunking past 1000-word window); CA-04 likely fails key_facts check which requires ALL of: "misconception", "myth", "excelled", "did not fail", "good at math"
- out_of_reach tier: 0% in both (structural eval issue — search_strategy judge penalizes for not finding articles that don't exist; fix applied to search_strategy judge post-eval)
- strategic tier: 100% in both (already saturated)

**Regressions:**
- groundedness judge: 4.74 → 4.59 avg (93% → 85.4% pass) — slight regression; longer v2 prompt may diffuse grounding discipline
- nq_factual: 100% → 90% (10/10 → 9/10) — one NQ case regressed

**Pairwise comparison v1 vs v2 (44 common cases, A=v1, B=v2):**

| Dimension | v2 (B) wins | v1 (A) wins | Ties | v2 win% |
|-----------|------------|------------|------|---------|
| groundedness | 8 | 9 | 27 | 18.2% |
| correctness | 6 | 2 | 36 | 13.6% |
| completeness | 7 | 7 | 30 | 15.9% |
| search_strategy | 15 | 7 | 22 | 34.1% |
| **OVERALL** | **20** | **9** | **15** | **45.5%** |

v2 wins 20/44 cases overall vs v1 wins 9/44 — a clear improvement. search_strategy is the dominant win dimension (15-7), matching the query craft table changes. Groundedness shows a slight regression (8-9) consistent with the judge score drop.

Note: The comparison_report.md pairwise summary was incorrect due to a bug in `_pairwise_summary` that looked for "v1"/"v2" winner keys but `PairwiseResult` stores "A"/"B". Bug fixed in `report.py` and `run_evals.py` post-eval.

**Top failure tags (v2):**

| Tag | Count | v1 count | Δ |
|-----|-------|----------|---|
| `wrong_answer` | 14 | 14 | ↔ |
| `fact_beyond_cutoff` | 10 | 11 | ↓ |
| `wrong_article` | 7 | 12 | ↓ |
| `oversearch` | 5 | 6 | ↓ |
| `extraction_failure` | 5 | 5 | ↔ |
| `answer_exceeds_retrieval_window` | 5 | 5 | ↔ |
| `retrieval_failure` | 4 | 5 | ↓ |
| `poor_chain_reasoning` | 4 | 4 | ↔ |
| `hallucination` | 4 | 3 | ↑ |
| `grounding_failure` | 3 | 2 | ↑ |
| `false_premise_propagated` | 3 | 8 | ↓↓ |
| `verbose_query` | 2 | 8 | ↓↓ |

---

## v3 — Narrow-Exception Trap + Delete-Not-Hedge Grounding

**Intent:** Two targeted changes over v2: (1) teach the model to distinguish a general false premise from a narrow true exception that superficially validates it; (2) harden the grounding verification rule from "remove or hedge" to "delete only" to fix the groundedness regression.

**Root cause analysis from v2 failures:**
- SQ-D failed because the agent found the autoimmunity exception ("the immune system is unable to distinguish in autoimmune disease") and answered with it, rather than recognising the general premise was false
- SQ-F failed because "Stirling cycle" is used in some solar applications — the agent found a narrow true match for the false entity "solar engine"
- Groundedness regression: v2's "remove or hedge" language gave the model license to add softened unverifiable claims; these accumulated into measurable judge score decline

**Changes from v2:**

| Change | Section | Targets |
|--------|---------|---------|
| "Narrow-exception trap" rule + immune system worked example | Step 2 | SQ-D, SQ-F false_premise_propagated |
| "Unrecognised entity" signal (if term has no Wikipedia article, treat as false entity) | Step 2 | SQ-F type entity substitution |
| Step 5 hardened: "delete entirely — do not rephrase, soften, or hedge" | Step 5 | Groundedness regression |
| Misconceptions: "only assert correction if debunking is in retrieved portion" | Hard Cases | CA-05, grounding failures |

**Actual v3 eval results:**

*Composite score:* 95.63 | *Pass rate:* 93.2% (41/44) — same 2 eval errors as v2 excluded

**Improvements over v2:**
- squad_false_premise: 37.5% → **75.0%** — narrow-exception example worked
- out_of_reach: 0% → **60.0%** — split: calibration (search_strategy judge fix) accounts for 40pp (as confirmed by v4); v3's retrieved-portion-only misconception rule accounts for the remaining 20pp
- hotpotqa_bridge: 92.3% → **100%**
- misconception: 0% → **50%** (CA-04 now passing)
- nq_factual: 90% → **100%**
- groundedness: 4.59 → **4.90** avg (85.4% → 97.6%) — delete-not-hedge rule fixed the regression
- correctness: 4.61 → **4.80** (92.7% → 95.1%)
- search_strategy: 4.20 → **4.61** (92.7% → 97.6%)
- `wrong_answer`: 14 → **1** — was the #1 tag in every prior version

**Remaining failures (3 cases):**
- SQ-C, SQ-E (squad_false_premise, out_of_reach): correcting text past 1000-word window; structural limit
- CA-05 (misconception, out_of_reach): Great Wall visibility myth past retrieval window; agent asserts from training knowledge

**Top failure tags (v3):**

| Tag | Count | v2 count | Δ |
|-----|-------|----------|---|
| `fact_beyond_cutoff` | 10 | 10 | ↔ structural |
| `extraction_failure` | 6 | 5 | ↑ slight |
| `oversearch` | 5 | 5 | ↔ |
| `answer_exceeds_retrieval_window` | 5 | 5 | ↔ structural |
| `wrong_article` | 4 | 7 | ↓ |
| `retrieval_failure` | 4 | 4 | ↔ |
| `wrong_answer` | 1 | 14 | ↓↓↓ |
| `false_premise_propagated` | 1 | 3 | ↓↓ |
| `hallucination` | 1 | 4 | ↓↓ |
| `poor_chain_reasoning` | 1 | 4 | ↓↓ |

Dominant remaining tags are structural (`fact_beyond_cutoff`, `answer_exceeds_retrieval_window`) — these reflect the 1000-word retrieval ceiling, not prompt failures.

**Pairwise comparison v2 vs v3 (44 cases, A=v2, B=v3):**

| Dimension | v3 (B) wins | v2 (A) wins | Ties | v3 win% |
|-----------|------------|------------|------|---------|
| groundedness | 10 | 6 | 28 | 22.7% |
| correctness | 5 | 4 | 35 | 11.4% |
| completeness | 11 | 8 | 25 | 25.0% |
| search_strategy | 6 | 8 | 30 | 13.6% |
| **OVERALL** | **10** | **8** | **26** | **22.7%** |

Groundedness is the clearest win (10-6): the delete-not-hedge rule had a direct measurable effect. The search_strategy slight regression (6-8) suggests v3's longer Step 2 premise analysis causes some over-deliberation before committing to searches. Overall v3 wins 10-8 — a modest but genuine prompt improvement, independent of eval calibration.

---

## v4 — Control Run (v2 Prompt, Calibrated Eval)

**Intent:** Not a prompt iteration — a methodological control. Re-runs the v2 prompt on the calibrated eval to isolate how much of the v2→v3 pass rate jump was due to eval calibration vs. genuine prompt improvement.

**Result:** *Composite score:* 91.39 | *Pass rate:* 77.3% (34/44)

**What v4 proves:** Calibration had ≈0 net effect on the v2 prompt (79.5% → 77.3%, within non-determinism noise). The out_of_reach tier improved (0% → 40%) from the search_strategy judge fix, but this was offset by non-determinism elsewhere. Conclusion: v3's +15.9pp improvement over v4 is attributable entirely to the prompt changes in v3, not to eval calibration.

---

## v5 — Query Constraints + Stopping Heuristic (Regression)

**Intent:** Target the remaining v3 failures: `wrong_article` (4), `oversearch` (5), `extraction_failure` (6). Three changes: (1) query length cap (≤5 keywords) + pivot-not-lengthen rule; (2) Step 5 premise confirmation check; (3) 2-consecutive-miss stop rule ("strong signal to stop, not a hard stop — a genuinely different article title you haven't tried is a valid reason to continue").

**Changes from v3:**

| Change | Targets |
|--------|---------|
| Query ≤5 keywords + pivot-not-lengthen rule | `wrong_article`, `verbose_query`, `oversearch` |
| Step 5 premise confirmation check | `false_premise_propagated`, remaining `squad_false_premise` |
| 2-consecutive-miss stop rule (strong signal, not hard stop) | `oversearch`, `unanswerable_not_acknowledged` |

**Actual v5 eval results:**

*Composite score:* 93.64 | *Pass rate:* 86.4% (38/44) — **regression from v3**

| Category | v3 | v5 | Δ |
|----------|----|----|---|
| hotpotqa_bridge | **100%** | 84.6% | ↓ -15.4pp |
| squad_false_premise | **75%** | 62.5% | ↓ -12.5pp |
| out_of_reach | 60% | 60% | ↔ |
| all others | 100% | 100% | ↔ |

**Why it regressed:** The ≤5 keyword rule and pivot-not-lengthen instruction disrupted multi-hop bridge question chains. Bridge cases require 2–4 deliberate searches through a chain — the new constraints caused the agent to abandon partially-correct chains rather than completing them. The Step 5 premise confirmation compounded this by making the agent doubt intermediate facts in multi-hop chains that were actually correct. `wrong_answer` went 1→3, `false_premise_propagated` went 1→2.

**The ceiling finding:** v3 is the prompt ceiling for this tool design. The 3 remaining v3 failures are structurally identical — all `out_of_reach` cases where the answer is past the 1000-word retrieval window. v5 demonstrated the ceiling: when further prompt changes regress already-solved categories without fixing structural failures, you have reached the prompt ceiling. The right fix is a system change (`get_section(title, section_name)` tool), not more prompt engineering.

---

## Pairwise Comparison Log

| Comparison | Overall winner | Groundedness | Correctness | Completeness | Search Strategy |
|------------|---------------|-------------|-------------|-------------|----------------|
| v0 → v1 | v1 (tag-level: grounding ↑↑, oversearch ↓, verbose_query ↓) | — | — | — | — |
| v1 → v2 | v2 (20-9 on 44 common cases) | v1 slight (9-8) | v2 (6-2) | tie (7-7) | v2 clear (15-7) |
| v2 → v3 | v3 slight (10-8, 44 cases) | v3 (10-6) | tie (5-4) | v3 slight (11-8) | v2 (6-8) |
| v4 (control) | N/A — v2 prompt, calibrated eval. 77.3% pass rate confirms calibration effect ≈0 | — | — | — | — |

Clear regressions (new version worse with high confidence) will be noted here and investigated before proceeding to the next version.

**v2→v3 interpretation:** The absolute pass rate jump (79.5% → 93.2%) is **genuinely prompt-driven**. v4 (v2 prompt re-run on the calibrated eval) scored 77.3% — nearly identical to v2's 79.5% — proving eval calibration had ≈0 net effect on the v2 prompt. The true comparison is v4 (77.3%) → v3 (93.2%) = **+15.9pp genuine prompt improvement**. The pairwise confirms this: v3 wins 10-8 overall, with groundedness as the clearest win (10-6). The search_strategy slight regression (6-8) suggests v3's longer Step 2 premise analysis causes some over-deliberation before committing to searches. The pairwise is the reliable signal — it compares actual responses independent of eval calibration changes.

---

## Prompt Engineering Principles (Observed)

These are lessons learned from the iteration process, updated as new insights emerge.

**1. Failure tags are more useful than scores.** A composite score of 62 tells you nothing about where to fix the prompt. The tag `false_premise_propagated` appearing 6 times tells you exactly what to add to Step 1.

**2. Distinguish prompt failures from system failures.** `fact_beyond_cutoff` is not a prompt failure — the 1000-word retrieval window is a system constraint. Adding more prompt guidance for this tag won't help; it needs a different remediation (caveat instruction, not retrieval improvement). The `fact_retrieval_diagnosis` check separates these cases.

**3. Each rule should have one measurable target.** Adding "be more careful" doesn't move any metric. Adding "if you have not found the information after 4 searches, stop and acknowledge" directly targets `oversearch` and `unanswerable_not_acknowledged`.

**4. Pairwise per-dimension reveals more than overall.** If v1 wins overall but loses on search_strategy, that's a regression that a composite score obscures. The per-dimension pairwise breakdown routes fixes to the right prompt section.

**5. The example in the prompt matters.** The Napoleon example in Step 1 is not decoration — it demonstrates the exact behavior the model should exhibit. Abstract rules ("verify the premise") are interpreted loosely; concrete examples bind the behavior.

**7. Prompt engineering has a ceiling defined by the tool, not the prompt.** v3 achieved 93.2% — the remaining 7% are three `out_of_reach` cases where the answer is past the 1000-word retrieval window. v5 demonstrated this ceiling clearly: adding more constraints (query length cap, pivot rule, stopping heuristic) regressed bridge questions from 100% to 84.6% without fixing any structural failure. The signal is: when further prompt changes regress already-solved categories without fixing the target category, you have reached the prompt ceiling. The right fix is a system change — a `get_section(title, section)` tool for targeted deep retrieval — not more prompt engineering.

**6. The eval suite is also an engineering artifact — iterate on it.** Three calibration issues found during v0→v2 iteration: (a) `_key_facts_present` requiring ALL synonyms penalised correct answers phrased differently from the expected string; (b) the `search_strategy` judge had no special case for `out_of_reach` cases and systematically penalised agents for not finding articles that don't exist; (c) the pairwise `_pairwise_summary` function looked for "v1"/"v2" winner keys but `PairwiseResult` stores "A"/"B", producing a completely wrong summary. Each of these would have sent prompt iteration in the wrong direction. The lesson: interrogate the eval itself with the same rigour as the prompt. Pairwise comparison between versions is more reliable than absolute pass rates when the eval changes between runs.
