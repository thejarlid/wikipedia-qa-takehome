# Eval Report

**Cases evaluated:** 46  
**Overall pass rate:** 69.6% (32/46)

---

## Pass Rates by Category

| Category | Passed | Total | Rate |
|----------|--------|-------|------|
| disambiguation | 0 | 1 | 0.0% |
| false_premise | 1 | 1 | 100.0% |
| hotpotqa_bridge | 10 | 13 | 76.9% |
| hotpotqa_comparison | 3 | 3 | 100.0% |
| jargon_obfuscation | 1 | 1 | 100.0% |
| misconception | 1 | 2 | 50.0% |
| nq_factual | 10 | 10 | 100.0% |
| out_of_scope | 3 | 3 | 100.0% |
| prompt_injection | 2 | 2 | 100.0% |
| squad_false_premise | 1 | 10 | 10.0% |

## Pass Rates by Retrievability Tier

| Tier | Passed | Total | Rate |
|------|--------|-------|------|
| direct | 21 | 29 | 72.4% |
| out_of_reach | 0 | 4 | 0.0% |
| strategic | 11 | 13 | 84.6% |

## Out-of-Scope Handling
- Correctly declined: 3
- Scope violations (answered when should decline): 0

## Judge Scores

| Judge | Avg Score (1–5) | Pass Rate |
|-------|-----------------|-----------|
| groundedness | 4.16 | 81.4% |
| correctness | 4.35 | 83.7% |
| completeness | 4.74 | 93.0% |
| search_strategy | 3.67 | 86.0% |

## Failure Tag Frequency

| Tag | Count |
|-----|-------|
| `wrong_answer` | 17 |
| `fact_beyond_cutoff` | 12 |
| `verbose_query` | 11 |
| `oversearch` | 9 |
| `judge_parse_error` | 9 |
| `extraction_failure` | 7 |
| `wrong_article` | 7 |
| `grounding_failure` | 6 |
| `false_premise_propagated` | 6 |
| `retrieval_failure` | 4 |
| `incomplete_answer` | 3 |
| `unanswerable_not_acknowledged` | 3 |
| `overclaiming` | 3 |
| `poor_chain_reasoning` | 2 |
| `hallucination` | 2 |
| `undersearch` | 1 |

---

## Diagnostic Analysis

## Diagnostic Narrative: QA Agent Eval v1

### 1. Systematic Failure Patterns

**Pattern A: False Premise Blindness (squad_false_premise: 10% pass rate)**
The dominant failure cluster. Tags `false_premise_propagated` (6), `unanswerable_not_acknowledged` (3), and `overclaiming` (3) all point to the same root: when a question embeds a false or unverifiable premise, the system accepts it and fabricates an answer rather than challenging it. The `squad_false_premise` category (10 cases, 1 passed) is catastrophic. The system that handles `false_premise` (standalone) at 100% clearly has *some* mechanism, but it doesn't generalize to embedded false premises in SQuAD-style questions.

**Pattern B: Retrieval Inefficiency (verbose_query + oversearch + wrong_article)**
Tags `verbose_query` (11), `oversearch` (9), and `wrong_article` (7) cluster together. The agent is issuing over-specified queries, landing on wrong articles, then compensating by searching repeatedly. `out_of_reach` retrievability is 0% (4/4 failed), confirming the agent has no graceful degradation when the right article isn't found — it keeps searching rather than acknowledging limits.

**Pattern C: Extraction and Grounding Failures**
`extraction_failure` (7) and `grounding_failure` (6) indicate the agent retrieves the right content but either pulls the wrong span or fails to anchor its answer to retrieved text. Groundedness judge average (4.16) is the lowest dimension, and its pass rate (81.4%) is the weakest judge metric.

**Pattern D: Knowledge Cutoff Mishandling**
`fact_beyond_cutoff` (12) is the second-highest tag. The agent attempts to answer time-sensitive questions using Wikipedia snapshots without flagging staleness, producing `wrong_answer` (17, the top tag) as a downstream effect.

---

### 2. What Each Pattern Reveals About the System Prompt

- **Pattern A**: There is no explicit instruction to *verify the premise of the question before answering*. The prompt likely says "answer based on retrieved content" but doesn't say "if retrieved content contradicts or fails to confirm the question's premise, say so explicitly."
- **Pattern B**: Query formulation guidance is absent or too permissive. No instruction caps query length, enforces keyword-style search, or specifies what to do after N failed retrievals (stop and acknowledge, don't keep searching).
- **Pattern C**: No grounding rule requires the answer to be a direct quote or traceable span from retrieved text. The agent is synthesizing rather than extracting.
- **Pattern D**: No instruction tells the agent to flag when Wikipedia content may be outdated relative to the question's implied timeframe, or to caveat time-sensitive answers.

---

### 3. Priority Order of Fixes

1. **Add a premise-verification step** *(highest impact — fixes squad_false_premise's 90% failure rate)*: Instruct the agent to explicitly check whether retrieved content confirms the question's stated facts before answering. If not confirmed, respond "The premise appears incorrect based on available sources: [evidence]."

2. **Add query formulation constraints** *(fixes verbose_query + wrong_article)*: Require short, keyword-focused queries (≤6 words). Add a hard cap of 3 retrieval attempts; on failure, acknowledge unanswerability rather than continuing.

3. **Add a grounding rule** *(fixes extraction_failure + grounding_failure)*: Require the final answer to cite the specific retrieved passage it derives from. If no passage directly supports the answer, the agent must say so.

4. **Add a temporal/cutoff caveat rule** *(fixes fact_beyond_cutoff)*: Instruct the agent to flag answers involving rankings, records, or current-state facts as potentially outdated, especially when the question implies recency.

5. **Add an unanswerability acknowledgment protocol** *(fixes unanswerable_not_acknowledged + overclaiming)*: Explicitly instruct: "If retrieved content does not contain sufficient information to answer, say 'I could not find reliable information on this' rather than inferring or extrapolating."

---

### 4. What the System Reliably Gets Right

- **Direct factual lookup** (`nq_factual`: 100%, 10/10