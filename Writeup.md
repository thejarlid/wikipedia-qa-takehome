# Design Rationale 

I built a wikipedia grounded QA agent using claude sonnet and a custom ```search_wikipedia(query)``` tool backed by the MediaWiki API. The goal of the system is to always retrieve evidence from Wikipedia before answering and is designed around a simple principle: "Answers should be grounded in retrieved wikipedia content rather than model memory" 

While the final artifact is a qa system the primary focus of this project was building a prompt engineering and evaluation workflow to systematically improve the agent over time.

Total Time Spent: **~6 hours**

## Prompt Engineering Approach

I started with a minimal baseline (v0) that mimicked what an engineer might put together as a first pass. This was deliberate. Starting sparse meant the eval results would surface real failure modes rather than hypothetical ones, giving the iteration loop something concrete to act on.

That loop looked like:
1. Write prompt
2. Run evals
3. Analyze failure tags and synthesis report
4. Identify root cause
5. Modify the specific prompt section that owns that failure
6. Re-evaluate and compare against the previous version

The most important thing I learned from running this loop is that failure tags were more useful than scores as diagnostic signals. false_premise_propagated appearing 6 times told me I needed to provide more details around premise verification which is step 2 in the system prompt. A composite score of 62 helps with trends over time and that something is wrong but doesn't tell me "what is wrong". Each tag in the taxonomy maps directly to a section of the prompt. Retrieval failures point to the query guidance, grounding failures point to Step 5, false premise tags point to the premise verification step and its worked examples.

The second lesson was that rules without examples don't work as well. v1 added an explicit "verify the premise before searching" rule and false_premise_propagated got worse from 6 occurences to 8. The model interpreted the rule loosely. v2 added the Napoleon and Columbus worked examples and it dropped to 3. v3 added a narrow-exception trap rule with an immune system example and it dropped to 1. In every case the fix wasn't more rules, but to add a concrete example showing the exact behaviour. I was also careful not to use examples from the evaluation dataset so the model had to generalise the demonstrated behaviour rather than pattern-match to a seen case.

The structure the prompt converged to over these iterations was a five-step reasoning process covering premise verification, search planning, retrieval, grounding verification, and submission. Later versions became increasingly explicit about query formulation, multi-hop decomposition, false premise handling, and when to stop searching. Each of these was added after observing a specific systematic failure in the evals. The grounding requirement evolved the most. v1 introduced "quote or closely paraphrase," which cut grounding_failure from 6 to 2. v3 hardened this further to "delete the claim entirely — do not rephrase or hedge" after the v2 pairwise showed groundedness regressing despite other improvements. That single change produced a 10-6 groundedness win in the v2/v3 pairwise eval run.


## Evaluation Framework 

The evaluation framework became the most significant part of the project and where I ended up spending most of my time.

Rather than treating evaluation as a benchmark that produced a score, I wanted to design my evals as a diagnostic system attempting to answer the question **"If a query fails, what metrics and information do I need in order to debug and diagnose the root cause?"** The goal was not simply determining whether the system passed or failed a question but understanding what should be changed next and how to detect regressions over time. 

I settled upon a layered approach: 
1. Deterministic Checks
2. LLM Judges
3. Pairwise Evaluations 

### Dataset Design 

My final dataset consisted of 44 test cases from 4 sources: 
1. [HotpotQA (multi-hop reasoning)](https://hotpotqa.github.io)
2. [Natural Questions (factual retrieval)](https://github.com/google-research-datasets/natural-questions)
3. [Squad2.0 (false premise questions)](https://rajpurkar.github.io/SQuAD-explorer/)
4. Hand Curated adversarial cases

These were chosen because they contained a lot of rich metadata and ground truth information that enabled me to evaluate my response and traces for retrieval quality, grounding behaviour, and search strategy both deterministically and with a panel of llm judges. 


### Layer 1: Deterministic Assertion Based Checks

The first evaluation layer consists of deterministic, assertion-based checks that produce binary pass/fail outcomes and failure tags. These run before any LLM judge is invoked and require no API calls. Rather than just let LLM judges handle everything these deterministic assertion based checks reliably enforce specific behavioural requirements rather than the judges that evaluate quality holistically on a 1-5 scale. Judges measure how well the agent did something; deterministic checks verify that it did it. Other types of assertions we can make are whether we made a multi-hop iteration for questions that require it, how many searches were made relative to a question's reasonable threshold, whether key articles are a subset of the searches made, etc. It's also practical: with 44 cases x 4 judges, each eval run is already ~200 API calls. The deterministic checks run in microseconds at no additional cost.

A key piece of the deterministic layer is to assign tags that both the deterministic layer and the LLM judges use. The fact_retrieval_diagnosis check disambiguates a failure it into five distinct states that hint at different prompt implications:
- Retrieval failure — the agent searched the wrong article, or didn't search at all (poor query formulation instructions in the system prompt)
- Extraction failure — the correct article was retrieved, but the agent failed to use the relevant content in its answer (harden the grounding section)
- Grounding failure — a fact appears in the answer but in none of the retrieved Wikipedia content, meaning the agent drew on training knowledge rather than retrieved text (harden the grounding section)
- Fact beyond retrieval cutoff — the right article was searched but the answer lies past the 1000-word retrieval window; a system constraint, not a prompt failure (system limitation and should not be penalized)
- Answer exceeds retrieval window — the agent answered correctly and the fact is confirmed in the full Wikipedia article, but past our window; the answer implying it answered from training data. (partly a system limitation and part hallucination pointing to grounding improvements)

This disambiguation proved directly useful in the iteration loop. In v2, grounding_failure was climbing slightly despite grounding guidance already existing in the prompt. The specific tag identified that the problem was the "remove or hedge" language in Step 5. It was giving the model license to soften unverifiable claims rather than delete them and in v3 we changed this to "delete entirely, do not rephrase or hedge," and the groundedness pairwise win (10-6) confirmed it worked. 

Below is a set of tags we saw get surfaced and how we mapped this to adjustments in the actual system prompt:
- false_premise_propagated : step 2 premise verification and worked examples
- verbose_query/wrong_article : step 2 tool description and query crafting guidance 
- oversearch/undersearch : step 3 search depth guidance
- poor_chain_reasoning : step 3 multi-hop decomposition guidance
- grounding_failure/hallucination : step 5 grounding verification rule
- unanswerable_not_acknowledged : hard out of reach guidance 

One key decision I made was to keep the deterministic checks independent from the judges so that it would not influence the judges verdict. Deterministic checks can produce a lot of false negatives since identifying whether a fact is in the answer based on string matching has a lot of edge cases. I wanted the judges to make their decision independently without any possible errors in the deterministic checks cascading down. This gives us independent signals and the value comes when the two layers agree or disagree. When a check fails but a judge passes, that disagreement tells me my check is miscalibrated which is how I discovered a bug with key_facts. The check was failing cases where the agent's response used a valid synonym that the deterministic check failed but the judge passed based on semantics correctly. That disagreement surfaced the issue and I was able to calibrate the deterministic eval. The moment the layers are coupled, this cross-checking disappears. When layers agree you have convergent evidence from two independent measurement methods and you can have more trust in the signal to act upon. 


### Layer 2: LLM Judges 

The second layer leveraged LLM Judges. While deterministic checks enforce behavioural requirements, the LLM judges evaluated quality. I used four specialized judges that supported the goals of the search system to be factual and use information retrieved from wikipedia. Each focused on a single dimension rather than one general judge trying to assess everything at once.

1. Groundedness (sonnet) - sees the full retrieved wikipedia text and the answer but not the ground truth. Its only question is whether every factual claim can be traced to what was actually retrieved which is the foundational goal of the qa search agent we are building. 

2. Correctness (sonnet) - sees the ground truth, key facts, and the adversarial claim to not confirm, but not the retrieved text. It handles special cases such as information being out of reach in which case a score of 5 meant honest acknowledgement of being unable to find a supporting claim in its research to give an answer. Grounded answers can still be incorrect which is where this judge comes into play. 

3. Completeness (haiku) - sees the question, category, and answer. Answers "Did the answer address everything asked?"

4. Search Strategy (sonnet) - sees the full agent reasoning trace to see the model's thinking between every tool call as well as the answer. Tries to evaluate whether the strategy was deliberate, not just whether the right articles happened to appear. Prompt changes directly impacted search behaviour and how queries are formed. Helps evaluating query formulation, article selection, and multi-hop decomposition. 

The reason for specializing is the same reason the failure tags matter: a single judge giving a score of 3 tells you something's wrong. Four specialized judges tell you which part of the prompt to fix. Groundedness failing means Step 5 needs hardening. Search strategy failing means the query guidance or multi-hop scaffold isn't working. A composite score obscures this completely. We also used sonnet for judges that needed more reasoning abilities and Haiku for mechanical checks to balance cost.

What I learned is that a single judge score is hard to trust in isolation. A 3 versus a 4 on any one case could be noisy. But what's meaningful is the aggregate trend across an entire eval run, and how that trend shifts across versions. As groundedness goes from 4.16 -> 4.74 -> 4.59 -> 4.90 across v0 through v3, that's a signal. Not because any single number is precise, but because the direction is consistent across 44 cases simultaneously. A regression showing up in the aggregate, like groundedness dropping from v1 to v2 despite the prompt ostensibly improving, was telling me the longer v2 prompt was diffusing grounding discipline even as it fixed other things. That regression was invisible in the overall pass rate but showed up clearly in the judge average, and it pointed directly at what v3 needed to fix.

The same applies cross-dimensionally. Seeing search_strategy improve while groundedness regresses in the same eval run tells me the changes hit one part of the prompt and inadvertently weakened another. You can't get that from a single composite score, it requires watching multiple dimensions move independently over time.


### Layer 3: Pairwise Comparison

The third layer I added was pairwise comparisons that tell you whether a change was actually an improvement and it's the more reliable signal when the eval itself is changing between runs. Pairwise comparisons became especially valuable because they remain useful even when the evaluation framework itself was changing. Since both versions are judged under identical conditions, many calibration effects cancel out.

This was the critical insight from v2 to v3. The pass rate jumped from 79.5% to 93.2%, and the obvious interpretation was that v3 was a large improvement. However, the evaluation framework had also been calibrated between those runs. I changed key_facts to check for “any” rather than “all” facts and updated the search-strategy judge to account for systematically out-of-reach answers. After making these changes, I became concerned that the observed gains might be artifacts of measurement rather than genuine prompt improvements. To test this, I ran a v4 evaluation using the v2 prompt on the calibrated evaluation suite. V4 scored 77.3%, which was very close to v2’s original 79.5%, suggesting that the calibration had minimal impact on overall performance. The pairwise comparison provided independent evidence pointing to the same conclusion, with v3 winning 10-8 overall and 10-6 on groundedness. Together, the v4 control run and pairwise results gave me confidence that the gains were driven by prompt improvements rather than evaluation changes.

Pairwise compares two responses to the same question directly across the same four specialized judges concurrently. Calibration noise cancels out because both versions face the same judge on the same case and that's why it's the cleaner signal. The preference framing is also deliberately different from the rubric scoring. Rather than asking judges to apply a scale, the pairwise prompt asks: which response would you rather a user receive? This is closer to Constitutional AI preference elicitation. 

In practice, the per-dimension breakdown proved more useful than the overall winner. The v1 -> v2 pairwise showed search_strategy winning 15-7 while groundedness slightly regressed 9-8. That split was invisible in the composite score but told me exactly what changed: the query craft table worked, but the longer prompt was slightly diffusing grounding discipline. That insight directly shaped what to fix in v3, adding and repeating the need to ground its answer throughout the prompt.


## Where the System Succeeds and Fails

Our strongest prompt was v3 which we have marked as the version our cli uses for regular usage. By v3 the system reached a 93.2% overall pass rate. Our system excelled at answering questions in the following categories: multi-hop bridge questions at 100%, factual NQ questions at 100%, out-of-scope and prompt injection resistance at 100% throughout all versions. Groundedness averaged 4.90/5.0 at v3 and the grounding discipline holds consistently. wrong_answer, which was the most frequent tag in every earlier version, dropped from 17 in v0 to 1 in v3.

The harder categories are false_premise detection and out-of-reach cases. squad_false_premise reached 75% at v3, an improvement from 10% in v0 but still the weakest category. The remaining failures are the subtler premise types: negation reversals, narrow-exception traps, and entity substitutions. These are genuinely difficult because the agent finds partially supporting text and treats it as confirmation rather than stepping back to evaluate whether the premise holds as a general rule.

The 3 remaining failures at v3 are all structural. The answer exists in Wikipedia but lies past the 1000 word retrieval window and no prompt change can address that, which v5 demonstrated clearly. Adding query length constraints and a stopping heuristic to address the remaining failures caused hotpotqa_bridge to regress from 100% to 84.6% and squad_false_premise from 75% to 62.5%. The constraints disrupted the multi-hop chains that v3 had already solved. When further prompt changes regress solved categories without fixing the target failures, I decided I had reached the prompt ceiling and the right fix here is a system change to add a get_section tool for targeted deep retrieval. This would require a prompt and new tool and another set of iterations to carefully leverage this ability to request additional information.

The most valuable lesson from the project was that prompt engineering is fundamentally an evaluation problem. Once failures were categorized and measurable, prompt changes became significantly easier. The hardest part was not writing prompts, it was building a framework that could reliably tell me what to change next.


## Future Work

The largest remaining limitation is retrieval depth. The current system retrieves only the first portion of a Wikipedia article. Several remaining failures occur because the relevant information exists in Wikipedia but lies beyond the retrieval window.

Given additional time, I would prioritize progressive retrieval instead of retrieving a fixed article summary, the agent could request additional sections or deeper context when it determines that the answer is likely present but inaccessible. This would directly address many of the remaining Out-of-Reach failures.

Additional future work would include:
- Ambiguity-focused datasets such as AmbigQA
- Larger-scale pairwise evaluation
- Retrieval strategy comparisons
- Continuous evaluation runs to collect long term trends