# Eval Report

**Cases evaluated:** 44  
**Overall pass rate:** 79.5% (35/44)

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
| nq_factual | 9 | 10 | 90.0% |
| out_of_scope | 3 | 3 | 100.0% |
| prompt_injection | 2 | 2 | 100.0% |
| squad_false_premise | 3 | 8 | 37.5% |

## Pass Rates by Retrievability Tier

| Tier | Passed | Total | Rate |
|------|--------|-------|------|
| direct | 22 | 26 | 84.6% |
| out_of_reach | 0 | 5 | 0.0% |
| strategic | 13 | 13 | 100.0% |

## Out-of-Scope Handling
- Correctly declined: 3
- Scope violations (answered when should decline): 0

## Judge Scores

| Judge | Avg Score (1–5) | Pass Rate |
|-------|-----------------|-----------|
| groundedness | 4.59 | 85.4% |
| correctness | 4.61 | 92.7% |
| completeness | 4.85 | 97.6% |
| search_strategy | 4.2 | 92.7% |

## Failure Tag Frequency

| Tag | Count |
|-----|-------|
| `wrong_answer` | 14 |
| `fact_beyond_cutoff` | 10 |
| `wrong_article` | 7 |
| `oversearch` | 5 |
| `extraction_failure` | 5 |
| `answer_exceeds_retrieval_window` | 5 |
| `retrieval_failure` | 4 |
| `poor_chain_reasoning` | 4 |
| `hallucination` | 4 |
| `grounding_failure` | 3 |
| `false_premise_propagated` | 3 |
| `undersearch` | 2 |
| `verbose_query` | 2 |
| `unanswerable_not_acknowledged` | 2 |
| `underclaiming` | 1 |
| `overclaiming` | 1 |
| `incomplete_answer` | 1 |

---

## Diagnostic Analysis

## Diagnostic Narrative: QA Agent Eval v1

### 1. Systematic Failure Patterns

**Pattern A: Knowledge Cutoff Blindness (10 `fact_beyond_cutoff` + 5 `answer_exceeds_retrieval_window`)**
The agent retrieves articles but fails to recognize when the specific fact needed falls outside the Wikipedia snapshot's coverage window. Rather than acknowledging the gap, it either hallucinates an answer or returns stale data confidently. This is the single largest failure cluster.

**Pattern B: False Premise Propagation (3 `false_premise_propagated` + 0.0% on `squad_false_premise`)**
The `squad_false_premise` category is the worst-performing at 37.5%. The agent accepts embedded false premises in questions and searches for answers that confirm them, rather than challenging the premise. The `misconception` category (0%) shows the same failure. The system treats all questions as valid.

**Pattern C: Retrieval Targeting Failures (7 `wrong_article` + 4 `retrieval_failure` + 5 `extraction_failure`)**
The agent frequently lands on the wrong article or the right article but wrong section. Combined with `verbose_query` (2), this suggests query formulation is imprecise — over-specified queries miss the canonical article, and once on the wrong page, extraction compounds the error. The `out_of_reach` retrievability bucket is 0/5, confirming the agent has no graceful fallback when retrieval doesn't surface the answer.

**Pattern D: Search Strategy Inefficiency (5 `oversearch` + 2 `undersearch` + 4 `poor_chain_reasoning`)**
The lowest judge score is `search_strategy` (4.2). The agent both over-searches (redundant queries on already-answered sub-questions) and under-searches (stops before resolving a bridge hop). Multi-hop reasoning chains break down mid-chain.

---

### 2. What Each Pattern Reveals About the System Prompt

- **Pattern A**: No instruction exists for handling temporal uncertainty. The prompt likely says "use retrieved content to answer" but doesn't say "if the content may be outdated or the fact is time-sensitive, flag this explicitly."
- **Pattern B**: The prompt lacks a premise-validation step. There is no instruction to check whether the question's embedded assumptions are supported by retrieved content before answering.
- **Pattern C**: Query formulation guidance is absent or weak. No instruction specifies to use short, canonical entity-name queries, nor is there a fallback strategy when the first retrieval misses (e.g., "try a shorter reformulation").
- **Pattern D**: No explicit multi-hop search protocol is defined. The prompt doesn't specify when to stop searching, how to chain sub-queries, or how to recognize a complete vs. incomplete evidence chain.

---

### 3. Priority Order of Fixes

1. **Add false-premise detection instruction** *(impact: high, fixes 37.5% → ~90% on `squad_false_premise`, `misconception`)* — Instruct the agent to verify each question's core assumption against retrieved content before answering; if unsupported, explicitly state the premise is unverified.

2. **Add cutoff/staleness acknowledgment rule** *(impact: high, frequency: 15 cases)* — Add explicit instruction: "If retrieved content does not contain the specific fact, or if the fact is likely time-sensitive, state that the information may be unavailable or outdated rather than inferring."

3. **Tighten query formulation guidance** *(impact: medium-high, fixes `wrong_article`, `verbose_query`)* — Instruct the agent to start with the shortest canonical entity name as the query, then broaden only if needed. Prohibit multi-clause queries on first attempt.

4. **Define a multi-hop search protocol** *(impact: medium, fixes `poor_chain_reasoning`, `oversearch`, `undersearch`)* — Add explicit steps: resolve one entity per query, confirm each hop before proceeding, stop when all sub-questions are answered.

5. **Add unanswerable acknowledgment for retrieval dead-ends** *(impact: medium, fixes `out_of_reach` 0%)* — Instruct the agent to say "I could not find this in the available sources" after N failed retrieval attempts rather than hallucinating.

---

### 4. What the System Reliably Gets Right

The agent is