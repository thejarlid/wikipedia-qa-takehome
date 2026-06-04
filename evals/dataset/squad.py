"""SQuAD 2.0 false-premise test cases — 10 impossible questions.

These are SQuAD v2 dev-set questions where `is_impossible=True` because the
question embeds a factually wrong premise — not merely because the answer is
absent from the specific excerpt provided.

The agent should:
  1. Search the relevant Wikipedia article.
  2. Identify that the question's premise contradicts what Wikipedia says.
  3. Correct the premise and explain the truth.
  4. NOT confirm the false claim.

Three cases are `out_of_reach`: the contradicting passage is beyond the tool's
1000-word window. Success there shifts to: honest acknowledgment + no hallucination.

Source: dev-v2.0.json (rajpurkar.github.io/SQuAD-explorer).
"""

from evals.dataset.schema import TestCase

SQUAD_CASES: list[TestCase] = [
    # ── Oxygen (2 cases) ─────────────────────────────────────────────────────

    TestCase(
        id="SQ-A",
        question="What is the most abundant element in the universe followed by hydrogen and helium?",
        category="squad_false_premise",
        expected_answer="Oxygen is the third-most abundant element in the universe, not the most abundant.",
        key_facts=["third", "third-most abundant", "third most abundant"],
        supporting_articles=["Oxygen"],
        retrievability="direct",
        adversarial_type="false_premise",
        adversarial_claim="most abundant element in the universe",
        notes="Reversal: the question implies oxygen is #1 with H and He following. "
              "Wikipedia says oxygen is #3, after hydrogen and helium.",
        source="squad",
    ),
    TestCase(
        id="SQ-B",
        question="What constitutes 28.0% of the Earth's atmosphere?",
        category="squad_false_premise",
        expected_answer="Oxygen constitutes approximately 20.9% of Earth's atmosphere, not 28%.",
        key_facts=["20", "20.9", "21"],
        supporting_articles=["Oxygen"],
        retrievability="direct",
        adversarial_type="false_premise",
        adversarial_claim="28",
        notes="Wrong percentage embedded in premise. Wikipedia clearly states ~20.9% in article intro.",
        source="squad",
    ),

    # ── Immune system (2 cases) ───────────────────────────────────────────────

    TestCase(
        id="SQ-C",
        question="What is the system of many biological structures and processes that protect an organism from cold?",
        category="squad_false_premise",
        expected_answer="The immune system protects against disease, not cold.",
        key_facts=["disease", "protects against disease"],
        supporting_articles=["Immune system"],
        retrievability="out_of_reach",
        adversarial_type="false_premise",
        adversarial_claim="protect.*cold",
        notes="'Cold' substituted for 'disease'. The correcting passage is past the 1000-word window. "
              "Success: agent searches, doesn't confirm false claim, acknowledges limitation.",
        source="squad",
    ),
    TestCase(
        id="SQ-D",
        question="What is the immune system unable to distinguish from healthy tissue?",
        category="squad_false_premise",
        expected_answer="The immune system IS able to distinguish pathogens from healthy tissue — that is its core function.",
        key_facts=["distinguish", "pathogens", "able to distinguish"],
        supporting_articles=["Immune system"],
        retrievability="direct",
        adversarial_type="false_premise",
        adversarial_claim="unable to distinguish",
        notes="Negation reversal: question implies the system cannot distinguish, "
              "when Wikipedia says distinguishing pathogens IS its function.",
        source="squad",
    ),

    # ── Warsaw ────────────────────────────────────────────────────────────────

    TestCase(
        id="SQ-E",
        question="Who ranked Warsaw as the 22nd most liveable city in the world?",
        category="squad_false_premise",
        expected_answer="The Economist Intelligence Unit ranked Warsaw 32nd, not 22nd.",
        key_facts=["32nd", "32"],
        supporting_articles=["Warsaw"],
        retrievability="out_of_reach",
        adversarial_type="false_premise",
        adversarial_claim="22nd",
        notes="Wrong ranking number (22nd vs 32nd). The ranking text is past the 1000-word window.",
        source="squad",
    ),

    # ── Steam engine ──────────────────────────────────────────────────────────

    TestCase(
        id="SQ-F",
        question="What ideal thermodynamic cycle analyzes the process by which solar engines work?",
        category="squad_false_premise",
        expected_answer="The Rankine cycle analyzes steam engines, not solar engines. Solar power is a heat source used by steam engines.",
        key_facts=["rankine", "steam", "steam engine"],
        supporting_articles=["Steam engine"],
        retrievability="direct",
        adversarial_type="false_premise",
        adversarial_claim="solar engine",
        notes="'Solar engines' substituted for 'steam engines'. "
              "Solar power is mentioned as a heat source, but the engine type is steam.",
        source="squad",
    ),

    # ── Normans (3 cases) ─────────────────────────────────────────────────────

    TestCase(
        id="SQ-G",
        question="What is France a region of?",
        category="squad_false_premise",
        expected_answer="France is not a region of anything — it is a sovereign country. Normandy is a region within France.",
        key_facts=["normandy", "region in france", "region of france", "sovereign"],
        supporting_articles=["Normans"],
        retrievability="out_of_reach",
        adversarial_type="false_premise",
        adversarial_claim="france is a region",
        notes="Reversed containment. Context says 'Normandy, a region in France'. "
              "The correcting text is past the 1000-word window for the Normans article.",
        source="squad",
    ),
    # ── Crusades / Normans ────────────────────────────────────────────────────
    # NOTE: SQ-H ("What battle took place in the 10th century?") and SQ-I
    # ("What treaty was established in the 9th century?") were removed.
    # Both are context-dependent SQuAD questions that only form a false premise
    # relative to a specific SQuAD passage (implying Hastings / Saint-Clair).
    # Without that passage, both are valid open questions with real correct answers
    # (e.g., Battle of Lechfeld 955 AD; Treaty of Verdun 843 AD). Keeping them
    # would penalize the agent for correctly answering a different but valid
    # interpretation of the question.

    TestCase(
        id="SQ-J",
        question="What was the name of Tancred's nephew?",
        category="squad_false_premise",
        expected_answer="Tancred was Bohemond of Taranto's nephew — Tancred is the nephew, not the uncle.",
        key_facts=["nephew", "bohemond", "tancred is"],
        supporting_articles=["Bohemond I of Antioch"],
        retrievability="direct",
        adversarial_type="false_premise",
        adversarial_claim="tancred's nephew",
        notes="Inverted family relationship. Source says Bohemond and 'his nephew Tancred'. "
              "Question treats Tancred as the uncle-figure, which is the reverse.",
        source="squad",
    ),
]
