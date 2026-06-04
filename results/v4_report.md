# Eval Report

**Cases evaluated:** 44  
**Overall pass rate:** 77.3% (34/44)

---

## Pass Rates by Category

| Category | Passed | Total | Rate |
|----------|--------|-------|------|
| disambiguation | 1 | 1 | 100.0% |
| false_premise | 0 | 1 | 0.0% |
| hotpotqa_bridge | 12 | 13 | 92.3% |
| hotpotqa_comparison | 3 | 3 | 100.0% |
| jargon_obfuscation | 1 | 1 | 100.0% |
| misconception | 0 | 2 | 0.0% |
| nq_factual | 10 | 10 | 100.0% |
| out_of_scope | 3 | 3 | 100.0% |
| prompt_injection | 2 | 2 | 100.0% |
| squad_false_premise | 2 | 8 | 25.0% |

## Pass Rates by Retrievability Tier

| Tier | Passed | Total | Rate |
|------|--------|-------|------|
| direct | 20 | 26 | 76.9% |
| out_of_reach | 2 | 5 | 40.0% |
| strategic | 12 | 13 | 92.3% |

## Out-of-Scope Handling
- Correctly declined: 3
- Scope violations (answered when should decline): 0

## Judge Scores

| Judge | Avg Score (1–5) | Pass Rate |
|-------|-----------------|-----------|
| groundedness | 4.68 | 92.7% |
| correctness | 4.61 | 87.8% |
| completeness | 4.9 | 97.6% |
| search_strategy | 4.44 | 97.6% |

## Failure Tag Frequency

| Tag | Count |
|-----|-------|
| `fact_beyond_cutoff` | 10 |
| `extraction_failure` | 6 |
| `answer_exceeds_retrieval_window` | 6 |
| `false_premise_propagated` | 6 |
| `wrong_article` | 5 |
| `oversearch` | 5 |
| `hallucination` | 3 |
| `retrieval_failure` | 3 |
| `grounding_failure` | 3 |
| `verbose_query` | 2 |
| `wrong_answer` | 2 |
| `unanswerable_not_acknowledged` | 2 |
| `overclaiming` | 2 |
| `poor_chain_reasoning` | 2 |
| `undersearch` | 1 |
| `incomplete_answer` | 1 |

---

## Diagnostic Analysis

# Diagnostic Narrative — Prompt v4

## 1. Systematic Failure Patterns

**Pattern A: False Premise Acceptance (squad_false_premise 25%, misconception 0%)**
Tags `false_premise_propagated` (6), `unanswerable_not_acknowledged` (2), and `overclaiming` (2) cluster tightly. The system regularly accepts flawed question premises as true and answers them rather than challenging or correcting them. SQ-A ("most abundant element after hydrogen and helium"), SQ-C, and SQ-D all embed incorrect factual frames that the agent propagates instead of refuting.

**Pattern B: Retrieval Quality Degradation**
Tags `wrong_article` (5), `oversearch` (5), `extraction_failure` (6), and `verbose_query` (2) form a coherent retrieval dysfunction cluster. The agent either fetches the wrong article, issues bloated multi-clause queries that confuse the retriever, or retrieves the right article but fails to extract the relevant span. This is the dominant driver of `direct` retrievability failures (76.9% pass rate vs. 92.3% for `strategic`).

**Pattern C: Out-of-Reach / Cutoff Handling**
`fact_beyond_cutoff` (10) and `answer_exceeds_retrieval_window` (6) are the highest-frequency tags overall. The `out_of_reach` retrievability bucket passes at only 40%. The agent frequently attempts to answer questions whose answers aren't in the retrieved content, producing hallucinations (3) and grounding failures (3) rather than gracefully declining.

**Pattern D: Multi-Hop Reasoning Breakdown**
`poor_chain_reasoning` (2) and `extraction_failure` on bridge questions (H-07, H-13) indicate that when the agent must chain two retrieved facts, it sometimes short-circuits — either hallucinating the intermediate entity or failing to carry the first hop's result into the second query.

---

## 2. What Each Pattern Reveals About the System Prompt

- **Pattern A**: v4 has no explicit instruction to *scrutinize question premises before answering*. There is no directive like "if the question contains a factual claim, verify it against retrieved content before accepting it."
- **Pattern B**: Query formulation guidance is either absent or too permissive. The prompt doesn't constrain query length/focus, nor does it instruct the agent to prefer narrow, entity-focused queries. There's also no fallback rule for when the retrieved article doesn't match the expected entity.
- **Pattern C**: The prompt lacks a clear "epistemic ceiling" rule — no instruction to compare retrieved content against the question's implied facts and explicitly decline when the answer cannot be grounded. The agent defaults to answering rather than abstaining.
- **Pattern D**: No explicit multi-hop scaffolding: the prompt doesn't instruct the agent to resolve intermediate entities fully before issuing the second retrieval, leading to premature answer synthesis.

---

## 3. Priority Order of Fixes

1. **Add a premise-verification step** (highest impact on false_premise + misconception categories): Before answering, instruct the agent to check whether the question's embedded claims are supported by retrieved content; if not, correct or flag them.

2. **Add an explicit abstention rule for ungrounded answers** (fixes Pattern C): "If the retrieved content does not contain sufficient information to answer, say so explicitly — do not infer or extrapolate." This directly targets `fact_beyond_cutoff`, `hallucination`, and `grounding_failure`.

3. **Constrain query formulation** (fixes Pattern B): Add a rule requiring queries to be short, entity-focused noun phrases (≤8 words). Add a wrong-article recovery instruction: if the retrieved article title doesn't match the expected entity, re-query with the entity name alone.

4. **Scaffold multi-hop reasoning** (fixes Pattern D): Instruct the agent to explicitly state the intermediate answer before issuing the second retrieval, preventing premature synthesis.

5. **Extraction discipline** (secondary fix for Pattern B): Instruct the agent to quote the specific sentence supporting its answer before formulating the final response, reducing extraction failures.

---

## 4. What the System Reliably Gets Right

v4 performs strongly on **factual lookups** (`nq_factual` 100%), **comparison questions** (`hotpotqa_comparison` 100%), **scope/injection resistance** (`out_of_scope` 100%, `prompt_injection` 100%), and **strategic multi-step retrieval** (92.3%). Judge scores for completeness (4.9) and search strategy (4.44) confirm the agent structures its searches well when premises are clean and content is retrievable. The early-stop mechanism is also reliable (3/3 correct declines, 0 scope violations).