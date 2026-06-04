# Eval Report

**Cases evaluated:** 46  
**Overall pass rate:** 73.9% (34/46)

---

## Pass Rates by Category

| Category | Passed | Total | Rate |
|----------|--------|-------|------|
| disambiguation | 1 | 1 | 100.0% |
| false_premise | 1 | 1 | 100.0% |
| hotpotqa_bridge | 12 | 13 | 92.3% |
| hotpotqa_comparison | 3 | 3 | 100.0% |
| jargon_obfuscation | 1 | 1 | 100.0% |
| misconception | 0 | 2 | 0.0% |
| nq_factual | 10 | 10 | 100.0% |
| out_of_scope | 3 | 3 | 100.0% |
| prompt_injection | 2 | 2 | 100.0% |
| squad_false_premise | 1 | 10 | 10.0% |

## Pass Rates by Retrievability Tier

| Tier | Passed | Total | Rate |
|------|--------|-------|------|
| direct | 21 | 28 | 75.0% |
| out_of_reach | 0 | 5 | 0.0% |
| strategic | 13 | 13 | 100.0% |

## Out-of-Scope Handling
- Correctly declined: 3
- Scope violations (answered when should decline): 0

## Judge Scores

| Judge | Avg Score (1–5) | Pass Rate |
|-------|-----------------|-----------|
| groundedness | 4.74 | 93.0% |
| correctness | 4.44 | 86.0% |
| completeness | 4.88 | 97.7% |
| search_strategy | 3.86 | 86.0% |

## Failure Tag Frequency

| Tag | Count |
|-----|-------|
| `wrong_answer` | 14 |
| `wrong_article` | 12 |
| `fact_beyond_cutoff` | 11 |
| `verbose_query` | 8 |
| `false_premise_propagated` | 8 |
| `oversearch` | 6 |
| `extraction_failure` | 5 |
| `retrieval_failure` | 5 |
| `answer_exceeds_retrieval_window` | 5 |
| `undersearch` | 4 |
| `poor_chain_reasoning` | 4 |
| `overclaiming` | 4 |
| `unanswerable_not_acknowledged` | 3 |
| `hallucination` | 3 |
| `grounding_failure` | 2 |
| `incomplete_answer` | 1 |

---

## Diagnostic Analysis

## Diagnostic Narrative: QA Agent Eval v1

### 1. Systematic Failure Patterns

**Pattern A: False Premise Propagation (squad_false_premise collapse)**
The most damaging single failure cluster. `squad_false_premise` passes at only 10%, driven by `false_premise_propagated` (8), `unanswerable_not_acknowledged` (3), `overclaiming` (4), and `hallucination` (3). When a question embeds a false or misleading premise, the system accepts it uncritically and attempts to answer rather than challenge or flag it. This is compounded by `answer_exceeds_retrieval_window` (5) — the system answers even when retrieved content doesn't actually support the claim.

**Pattern B: Retrieval Targeting Failures**
`wrong_article` (12) and `verbose_query` (8) cluster together, indicating the system is formulating queries that are too long or semantically diffuse, landing on the wrong Wikipedia article. `oversearch` (6) and `undersearch` (4) add to this: the system doesn't have a clear stopping rule for when it has enough evidence. `out_of_reach` retrievability scores 0% — the system never gracefully handles questions where the answer simply isn't in Wikipedia.

**Pattern C: Extraction and Reasoning Failures**
`extraction_failure` (5), `poor_chain_reasoning` (4), and `retrieval_failure` (5) indicate that even when the right article is found, the system fails to pull the correct span or chain multi-hop logic correctly. This is reflected in the lowest judge score: `search_strategy` at 3.86.

**Pattern D: Knowledge Cutoff Confusion**
`fact_beyond_cutoff` (11) is the third-highest tag. The system doesn't distinguish between "not in Wikipedia" and "not in my training" — it either hallucinates or silently answers with stale data.

---

### 2. What Each Pattern Reveals About the System Prompt

- **Pattern A**: There is no explicit instruction to *detect and challenge false premises before answering*. The prompt likely says "answer based on retrieved content" without a prior step: "check whether the question's assumptions are supported."
- **Pattern B**: Query formulation guidance is absent or too permissive. No instruction to keep queries short, entity-focused, or to prefer article titles over full question text. No explicit rule for when to stop searching or retry with a different query.
- **Pattern C**: No chain-of-thought scaffolding for multi-hop questions. The prompt doesn't instruct the system to decompose bridge questions into sub-queries and verify each hop independently.
- **Pattern D**: No instruction distinguishing "Wikipedia doesn't contain this" from "this is beyond knowledge cutoff" — and no fallback behavior for either case.

---

### 3. Priority Order of Fixes

1. **Add false-premise detection step** *(impact: high, fixes ~10 failures)*: Before answering, explicitly instruct the system to verify that the question's stated facts are supported by retrieved content. If not, flag the premise as unverified and decline to answer.

2. **Constrain query formulation** *(impact: high, fixes ~8–12 failures)*: Add explicit rules: queries should be short (≤6 words), entity-focused, and prefer likely Wikipedia article titles. Prohibit full-sentence queries.

3. **Add unanswerable/out-of-scope handling for retrieval gaps** *(impact: medium-high, fixes ~8 failures)*: Instruct the system that if retrieved content doesn't contain the answer after N attempts, respond "I cannot find this in Wikipedia" rather than inferring or hallucinating.

4. **Add multi-hop decomposition scaffolding** *(impact: medium, fixes ~4–5 failures)*: For bridge questions, instruct the system to explicitly resolve each entity hop as a separate sub-query before synthesizing.

5. **Clarify knowledge cutoff behavior** *(impact: medium, fixes ~3–4 failures)*: Add explicit instruction: if the question concerns events or facts not present in retrieved articles, state that the information is unavailable rather than answering from parametric memory.

---

### 4. What the System Reliably Gets Right

The system is strong on **direct factual retrieval** (`nq_factual`: 100%), **comparison questions** (`hotpotqa_comparison`: 100%), and **adversa