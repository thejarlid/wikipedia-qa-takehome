# Eval Report

**Cases evaluated:** 44  
**Overall pass rate:** 93.2% (41/44)

---

## Pass Rates by Category

| Category | Passed | Total | Rate |
|----------|--------|-------|------|
| disambiguation | 1 | 1 | 100.0% |
| false_premise | 1 | 1 | 100.0% |
| hotpotqa_bridge | 13 | 13 | 100.0% |
| hotpotqa_comparison | 3 | 3 | 100.0% |
| jargon_obfuscation | 1 | 1 | 100.0% |
| misconception | 1 | 2 | 50.0% |
| nq_factual | 10 | 10 | 100.0% |
| out_of_scope | 3 | 3 | 100.0% |
| prompt_injection | 2 | 2 | 100.0% |
| squad_false_premise | 6 | 8 | 75.0% |

## Pass Rates by Retrievability Tier

| Tier | Passed | Total | Rate |
|------|--------|-------|------|
| direct | 25 | 26 | 96.2% |
| out_of_reach | 3 | 5 | 60.0% |
| strategic | 13 | 13 | 100.0% |

## Out-of-Scope Handling
- Correctly declined: 3
- Scope violations (answered when should decline): 0

## Judge Scores

| Judge | Avg Score (1–5) | Pass Rate |
|-------|-----------------|-----------|
| groundedness | 4.9 | 97.6% |
| correctness | 4.8 | 95.1% |
| completeness | 4.93 | 100.0% |
| search_strategy | 4.61 | 97.6% |

## Failure Tag Frequency

| Tag | Count |
|-----|-------|
| `fact_beyond_cutoff` | 10 |
| `extraction_failure` | 6 |
| `oversearch` | 5 |
| `answer_exceeds_retrieval_window` | 5 |
| `wrong_article` | 4 |
| `retrieval_failure` | 4 |
| `verbose_query` | 3 |
| `grounding_failure` | 2 |
| `unanswerable_not_acknowledged` | 2 |
| `overclaiming` | 2 |
| `undersearch` | 1 |
| `underclaiming` | 1 |
| `false_premise_propagated` | 1 |
| `wrong_answer` | 1 |
| `poor_chain_reasoning` | 1 |
| `hallucination` | 1 |

---

## Diagnostic Analysis

# Diagnostic Narrative — Prompt v3

## 1. Systematic Failure Patterns

**Pattern A: Retrieval Boundary Failures (extraction_failure × 6, answer_exceeds_retrieval_window × 5, wrong_article × 4, retrieval_failure × 4)**
The system frequently retrieves *something* but either lands on the wrong article, fails to extract the relevant passage, or the answer sits outside the retrieved window. These tags cluster together on multi-hop questions (H-07, H-08, H-12, H-13) and SQuAD-style questions (SQ-A through SQ-F), suggesting the system isn't drilling into the right section of long articles or isn't pivoting to a second article when the first is a near-miss.

**Pattern B: Search Inefficiency (oversearch × 5, verbose_query × 3, undersearch × 1)**
The system over-queries on hard cases (H-03, H-10, SQ-F) while occasionally under-querying on simpler ones (H-08). Verbose queries likely dilute retrieval precision. This is the lowest-scoring judge dimension (search_strategy: 4.61).

**Pattern C: False-Premise / Unanswerable Handling (unanswerable_not_acknowledged × 2, overclaiming × 2, false_premise_propagated × 1, hallucination × 1)**
When retrieved content doesn't cleanly support an answer — especially for squad_false_premise (75% pass) and misconception (50% pass) — the system sometimes asserts an answer anyway rather than flagging the premise as flawed or the question as unanswerable. CA-05 (Great Wall visibility) is the clearest example: the system overclaims, hallucinates, and fails to acknowledge unanswerability simultaneously.

**Pattern D: Out-of-Reach Knowledge (fact_beyond_cutoff × 10, out_of_reach retrievability: 60%)**
The most-tagged failure mode by raw count, though many of these are *diagnostic* tags on cases that were always going to be hard. Still, the system doesn't consistently signal when a fact is likely beyond retrieval reach.

---

## 2. What Each Pattern Reveals About the System Prompt

- **Pattern A**: No explicit instruction on *section targeting* within long articles, and no fallback rule like "if the retrieved article doesn't contain the answer entity, immediately pivot to a more specific article." The prompt likely says "search Wikipedia" without specifying how to navigate multi-section or disambiguation pages.
- **Pattern B**: Query construction guidance is underspecified. The prompt probably lacks a rule like "use the shortest unambiguous query" or a cap on search attempts before concluding unanswerability.
- **Pattern C**: The false-premise handling instruction is either absent or too weak. There's no explicit directive: "If retrieved content contradicts the question's premise, state the premise is incorrect rather than answering." The overclaiming/hallucination on CA-05 suggests the system fills gaps with prior knowledge when retrieval is thin.
- **Pattern D**: No explicit instruction to say "this fact may not be in Wikipedia or may be outdated — I cannot confirm" when multiple searches return nothing relevant.

---

## 3. Priority Order of Fixes

1. **Add a false-premise / unanswerable escalation rule** *(Pattern C — high impact, directly causes failures in squad_false_premise and misconception categories)*: "If retrieved content contradicts or does not support the question's premise, explicitly state the premise appears incorrect. Never fill gaps with unverified prior knowledge."

2. **Add article-pivot and section-targeting guidance** *(Pattern A — highest frequency tags)*: "If the first retrieved article doesn't contain the answer, identify the specific entity or concept that needs its own article and search for it directly. For long articles, note which section heading is relevant."

3. **Constrain query length and search count** *(Pattern B)*: "Queries must be ≤ 6 words. Stop searching after 3 attempts and declare the question unanswerable if no relevant content is found."

4. **Add an out-of-reach acknowledgment rule** *(Pattern D)*: "If repeated searches return no relevant content, state explicitly that the information could not be found in Wikipedia rather than speculating."

---

## 4. What the System Reliably Gets Right

v3 is strong across the board on well-scoped factual retrieval: **nq_factual (100%)**, **hotpotqa_bridge (100%)**, **hotpotqa_comparison (100%)**, and **strategic retrievability (100%)** all pass perfectly. Prompt injection and out-of-scope refusals are handled flawlessly (early_stop: 3/3, no scope violations). Groundedness and completeness judge scores are near-ceiling (4.90–4.93), meaning when the system does answer, the answers are well-grounded and complete. The core retrieval-and-answer loop is solid; the remaining failures are concentrated in edge-case reasoning about premises and retrieval boundary navigation.

---

## Pairwise Comparison (v1 vs v2)

## Pairwise Comparison Summary: v1 → v2

### Where v2 Improved
v2 shows its clearest gains in **completeness** (10 wins vs. 5, 22.7% win rate) and **groundedness** (8 wins vs. 7). In factual NQ cases like NQ-05 ("Sugar Sugar") and NQ-14 (oligodynamic effect), v2 consistently extracted richer detail from retrieved articles—additional chart statistics, mechanistic explanations, and proper attributions—without hallucinating. These wins suggest v2 is better at leveraging retrieved content fully rather than stopping at a minimal correct answer.

### Where v2 Regressed or Tied Unexpectedly
**Search strategy** is v2's clear regression point (3 wins vs. 7, only 6.8% win rate). In difficult cases like H-10 (Aladin consultant) and SQ-E (Warsaw liveability ranking), v2 issued noisier, less systematic queries, went down wrong paths (e.g., chasing a French rapper), and occasionally introduced hallucinated framing (SQ-E: asserting EIU is "most widely cited" without source support). v2 also underperformed on out-of-reach and false-premise questions, where v1's more cautious, transparent hedging was preferred.

### Alignment with Intended Changes
The improvements in completeness and groundedness align with prompt changes likely aimed at encouraging fuller use of retrieved content. However, the search strategy regression suggests the prompt may have inadvertently loosened query discipline or reduced the system's ability to recognize dead ends efficiently.

### Key Pairwise Insight
The pairwise comparison reveals a **quality-vs-efficiency tradeoff** invisible in per-case scoring: v2 produces richer answers when retrieval succeeds, but its search behavior degrades on harder questions—a pattern that aggregate scores would mask by averaging wins across easy factual cases against losses on complex multi-hop ones.