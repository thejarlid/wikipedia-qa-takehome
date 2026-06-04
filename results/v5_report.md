# Eval Report

**Cases evaluated:** 44  
**Overall pass rate:** 86.4% (38/44)

---

## Pass Rates by Category

| Category | Passed | Total | Rate |
|----------|--------|-------|------|
| disambiguation | 1 | 1 | 100.0% |
| false_premise | 1 | 1 | 100.0% |
| hotpotqa_bridge | 11 | 13 | 84.6% |
| hotpotqa_comparison | 3 | 3 | 100.0% |
| jargon_obfuscation | 1 | 1 | 100.0% |
| misconception | 1 | 2 | 50.0% |
| nq_factual | 10 | 10 | 100.0% |
| out_of_scope | 3 | 3 | 100.0% |
| prompt_injection | 2 | 2 | 100.0% |
| squad_false_premise | 5 | 8 | 62.5% |

## Pass Rates by Retrievability Tier

| Tier | Passed | Total | Rate |
|------|--------|-------|------|
| direct | 24 | 26 | 92.3% |
| out_of_reach | 3 | 5 | 60.0% |
| strategic | 11 | 13 | 84.6% |

## Out-of-Scope Handling
- Correctly declined: 3
- Scope violations (answered when should decline): 0

## Judge Scores

| Judge | Avg Score (1–5) | Pass Rate |
|-------|-----------------|-----------|
| groundedness | 4.85 | 97.6% |
| correctness | 4.71 | 87.8% |
| completeness | 4.88 | 97.6% |
| search_strategy | 4.46 | 97.6% |

## Failure Tag Frequency

| Tag | Count |
|-----|-------|
| `fact_beyond_cutoff` | 11 |
| `oversearch` | 6 |
| `answer_exceeds_retrieval_window` | 5 |
| `extraction_failure` | 4 |
| `wrong_article` | 4 |
| `retrieval_failure` | 4 |
| `verbose_query` | 3 |
| `wrong_answer` | 3 |
| `unanswerable_not_acknowledged` | 2 |
| `overclaiming` | 2 |
| `false_premise_propagated` | 2 |
| `hallucination` | 2 |
| `undersearch` | 1 |
| `grounding_failure` | 1 |
| `poor_chain_reasoning` | 1 |
| `incomplete_answer` | 1 |

---

## Diagnostic Analysis

# Diagnostic Narrative — Prompt v5

## 1. Systematic Failure Patterns

**Pattern A: Search Strategy Inefficiency (oversearch + verbose_query + wrong_article)**
Tags `oversearch` (6), `verbose_query` (3), and `wrong_article` (4) cluster together in multi-hop bridge questions (H-03, H-07, H-10, H-13). The agent issues long, compound queries that either retrieve irrelevant articles or keep searching past the point of diminishing returns. This is the single most consistent behavioral failure despite `search_strategy` having a 97.6% pass rate — the judge rewards effort, but the underlying retrieval is misdirected.

**Pattern B: False Premise Propagation and Overclaiming on Unanswerable Questions**
Tags `unanswerable_not_acknowledged` (2), `overclaiming` (2), and `false_premise_propagated` (2) co-occur on SQ-C, SQ-E, and SQ-J. When retrieved content doesn't confirm the question's premise, the agent answers anyway rather than flagging the gap. This is distinct from the `squad_false_premise` category's 62.5% pass rate — the agent handles explicit false premises better than implicit ones embedded in factual questions.

**Pattern C: Retrieval Window and Extraction Failures**
Tags `answer_exceeds_retrieval_window` (5) and `extraction_failure` (4) indicate the agent finds the right article but fails to surface the specific fact — either because the answer sits outside the retrieved text chunk or because the agent doesn't re-query with a more targeted term. Cases H-13, SQ-D, and SQ-A exemplify this.

**Pattern D: Hallucination on Ambiguous/Broad Queries**
Tags `hallucination` (2) appear on CA-05 and CA-07 — misconception-type and broad topic questions. The agent generates plausible-sounding content not grounded in retrieved text.

---

## 2. What Each Pattern Reveals About the System Prompt

- **Pattern A**: The prompt lacks explicit query formulation rules — specifically, no instruction to decompose multi-hop questions into atomic single-entity searches, and no cap on query length or search iterations before pivoting strategy.
- **Pattern B**: The prompt has no explicit instruction for handling *implicit* false premises (where the question assumes a fact that retrieval neither confirms nor denies). The existing false-premise handling likely only triggers on obvious contradictions.
- **Pattern C**: There is no guidance on what to do when a retrieved article is confirmed relevant but the specific answer isn't visible — no instruction to re-query with a narrower or differently-phrased term targeting the specific sub-fact.
- **Pattern D**: The prompt likely lacks a strict grounding rule: "only assert facts that appear verbatim or by clear inference in retrieved text." The hallucination cases suggest the agent fills gaps from parametric memory when retrieval is thin.

---

## 3. Priority Order of Fixes

1. **Add atomic query decomposition rules** (Pattern A — high frequency, high impact): Instruct the agent to break multi-hop questions into sequential single-entity lookups. Cap query length at ~5–7 words. Limit total search rounds before declaring partial retrieval.

2. **Add implicit false-premise detection** (Pattern B — medium frequency, correctness impact): Instruct the agent: "If retrieval neither confirms nor contradicts a question's assumed fact, explicitly state that the premise could not be verified rather than answering as if it were true."

3. **Add targeted re-query on extraction failure** (Pattern C — medium frequency): Add a rule: "If the relevant article is found but the specific answer is not visible in the retrieved passage, issue a follow-up search using the specific sub-fact term rather than the original question."

4. **Enforce strict grounding / no parametric fill** (Pattern D): Add explicit instruction: "Never assert a fact that is not present in retrieved content. If retrieval is insufficient, say so."

---

## 4. What the System Reliably Gets Right

- **Direct factual retrieval** (`nq_factual`: 100%, `direct` retrievability: 92.3%) — clean, well-grounded single-hop answers.
- **Scope and injection handling** (`out_of_scope`: 100%, `prompt_injection`: 100%, `early_stop` 3/3 correct) — the agent correctly declines out-of-bounds queries with zero false positives.
- **Comparison reasoning** (`hotpotqa_comparison`: 100%) — structured two-entity comparisons are handled reliably.
- **Explicit false premises** (`false_premise`: 100%) — clearly flagged false premises are caught consistently.
- **Groundedness overall** (judge score 4.85, 97.6% pass) — when the agent does retrieve correctly, it stays grounded.