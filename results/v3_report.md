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

**Pattern A: Retrieval Thrashing (oversearch + verbose_query + wrong_article + retrieval_failure)**
Tags: `oversearch` (5), `verbose_query` (3), `wrong_article` (4), `retrieval_failure` (4). The system frequently issues over-specified queries, lands on the wrong article, then keeps searching rather than pivoting strategy. Cases like H-03, H-10, and SQ-F show the agent burning turns without converging on the right source.

**Pattern B: Content Window Exhaustion (extraction_failure + answer_exceeds_retrieval_window)**
Tags: `extraction_failure` (6), `answer_exceeds_retrieval_window` (5). When the relevant fact sits deep in a long article, the agent fails to extract it — either because it reads only the top of the article or doesn't request additional content. H-07, H-13, SQ-B, SQ-C, and SQ-D all exhibit this.

**Pattern C: Ungrounded Confidence on Unanswerable Questions (unanswerable_not_acknowledged + overclaiming + false_premise_propagated + hallucination)**
Tags: `unanswerable_not_acknowledged` (2), `overclaiming` (2), `false_premise_propagated` (1), `hallucination` (1). When retrieved content doesn't cleanly support an answer — especially for `squad_false_premise` and `misconception` cases — the system fills the gap with confident-sounding claims rather than flagging uncertainty. CA-05 and SQ-C are the clearest examples.

**Pattern D: Out-of-Reach Facts (fact_beyond_cutoff)**
Tag: `fact_beyond_cutoff` (10). This is the highest-frequency tag but largely a retrieval-environment ceiling issue; however, the agent sometimes keeps searching rather than acknowledging the limit, compounding with Pattern A.

---

## 2. What Each Pattern Reveals About the System Prompt

**Pattern A** — The prompt lacks explicit query formulation discipline: no instruction to use short, keyword-focused queries, no rule about switching search terms after one failed attempt, and no guidance on how to select among multiple candidate articles before reading.

**Pattern B** — There is no instruction telling the agent to paginate or request deeper sections of an article when the initial content doesn't contain the answer. The prompt appears to treat a single article read as sufficient, with no "scroll further" or "retrieve next section" directive.

**Pattern C** — The prompt has no explicit fallback rule for when retrieved content is absent or contradicts the question's premise. There is no instruction like "if the article does not confirm the claim, say so explicitly rather than inferring." The `squad_false_premise` failures (75% pass rate) confirm this gap.

**Pattern D** — The prompt likely lacks a concise heuristic for recognizing when a fact is genuinely unretrievable and stopping gracefully, causing the agent to over-iterate.

---

## 3. Priority Order of Fixes

1. **Add a false-premise / unanswerable acknowledgment rule** *(Pattern C — highest risk, affects correctness and groundedness)*: Instruct the agent: "If retrieved content does not confirm the question's premise, explicitly state that the premise may be incorrect rather than constructing an answer."

2. **Add article pagination / deep-read instruction** *(Pattern B — high frequency)*: "If the initial article excerpt does not contain the answer, retrieve additional sections before concluding the fact is absent."

3. **Enforce short, keyword-only queries with a pivot rule** *(Pattern A)*: "Queries must be ≤5 keywords. If the first query returns the wrong article, reformulate with different terms — do not repeat the same query."

4. **Add an out-of-reach stopping heuristic** *(Pattern D)*: "After two failed retrieval attempts, acknowledge the information may not be available rather than continuing to search."

5. **Clarify article selection before reading** *(Pattern A — wrong_article)*: "Before reading an article, confirm its title matches the entity in the question."

---

## 4. What the System Reliably Gets Right

v3 performs excellently on **multi-hop bridge questions** (`hotpotqa_bridge`: 100%), **direct factual lookups** (`nq_factual`: 100%), and