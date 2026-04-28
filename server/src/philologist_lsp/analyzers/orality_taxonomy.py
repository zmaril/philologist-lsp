"""Hand-curated oral/literate categorization + descriptions for the 71
havelock-orality marker subtypes.

Categorization is based on Walter Ong's "Orality and Literacy" (1982) and
Eric Havelock's framework. The havelock model includes its own category
classifier; we use this static mapping instead because it's free, fast,
and consistent with the linguistic theory.
"""

from __future__ import annotations

ORAL = "oral"
LITERATE = "literate"


# Each marker → (category, short description, optional examples)
MARKER_TAXONOMY: dict[str, tuple[str, str, list[str]]] = {
    # ── Oral markers ───────────────────────────────────────────────────
    "vocative": (
        ORAL,
        "Direct address to the audience or interlocutor.",
        ["Friends, Romans, countrymen…", "Listen, brothers."],
    ),
    "second_person": (
        ORAL,
        "Direct reference to the listener using 'you'.",
        ["You all know what happened.", "If you ask me…"],
    ),
    "inclusive_we": (
        ORAL,
        "Speaker–audience solidarity through 'we'/'us'.",
        ["We must do better.", "Our task is clear."],
    ),
    "named_individual": (
        ORAL,
        "Reference to a specific person by name.",
        ["John told me yesterday.", "Mary disagrees."],
    ),
    "specific_place": (
        ORAL,
        "Concrete, named locale rather than abstract space.",
        ["here in Boston", "down on the farm"],
    ),
    "temporal_anchor": (
        ORAL,
        "Anchoring time to the moment of speaking.",
        ["this day", "right now", "tonight"],
    ),
    "imperative": (
        ORAL,
        "Direct command or instruction.",
        ["Listen carefully.", "Stop that."],
    ),
    "rhetorical_question": (
        ORAL,
        "Question posed for effect rather than information.",
        ["Who could deny it?", "Is this not justice?"],
    ),
    "phatic_check": (
        ORAL,
        "Audience-attention probe.",
        ["right?", "you know?", "see what I mean?"],
    ),
    "phatic_filler": (
        ORAL,
        "Hesitation or floor-holding device.",
        ["uh", "well…", "I mean,"],
    ),
    "discourse_formula": (
        ORAL,
        "Stock conversational opening or closing.",
        ["As I was saying,", "And so it goes."],
    ),
    "religious_formula": (
        ORAL,
        "Ritualized invocation rooted in oral worship.",
        ["In the name of…", "May God bless…"],
    ),
    "proverb": (
        ORAL,
        "Inherited wisdom in compressed form.",
        ["A stitch in time saves nine.", "Pride goeth before a fall."],
    ),
    "refrain": (
        ORAL,
        "Repeated phrase across stretches of discourse.",
        ["I have a dream… (repeated)"],
    ),
    "anaphora": (
        ORAL,
        "Repetition of a word or phrase at the start of successive clauses.",
        ["We shall fight on the beaches, we shall fight on the landing grounds…"],
    ),
    "epistrophe": (
        ORAL,
        "Repetition of a word at the end of successive clauses.",
        ["…government of the people, by the people, for the people."],
    ),
    "parallelism": (
        ORAL,
        "Mirror structure between adjacent phrases.",
        ["Easy come, easy go."],
    ),
    "tricolon": (
        ORAL,
        "Three-part rhetorical construction.",
        ["Veni, vidi, vici."],
    ),
    "antithesis": (
        ORAL,
        "Sharp opposition between paired ideas.",
        [
            "Ask not what your country can do for you, but what you can do for your country."
        ],
    ),
    "asyndeton": (
        ORAL,
        "Conjunctions omitted between coordinated clauses.",
        ["I came, I saw, I conquered."],
    ),
    "polysyndeton": (
        ORAL,
        "Conjunctions piled up between clauses.",
        ["and the rain and the wind and the cold"],
    ),
    "intensifier_doubling": (
        ORAL,
        "Reduplication for emphasis.",
        ["very very tired", "right now right now"],
    ),
    "lexical_repetition": (
        ORAL,
        "Same word repeated for prosodic or memory effect.",
        ["work, work, work"],
    ),
    "alliteration": (
        ORAL,
        "Repetition of initial consonant sounds.",
        ["fearful and forlorn"],
    ),
    "assonance": (
        ORAL,
        "Repetition of vowel sounds.",
        ["the rain in Spain"],
    ),
    "rhyme": (
        ORAL,
        "Matching end-sounds for memorability.",
        ["if the glove don't fit…"],
    ),
    "rhythm": (
        ORAL,
        "Regular metric beat in prose.",
        ["four score and seven years ago"],
    ),
    "audience_response": (
        ORAL,
        "Cue for or call-back to listener reaction.",
        ["Can I get an amen?"],
    ),
    "embodied_action": (
        ORAL,
        "Reference to gesture, posture, or bodily presence.",
        ["as you can see here", "I stand before you"],
    ),
    "sensory_detail": (
        ORAL,
        "Concrete sense impression: sight, sound, taste, touch.",
        ["the cold iron in my hand"],
    ),
    "everyday_example": (
        ORAL,
        "Domestic, household-scale illustration.",
        ["like when you bake a cake…"],
    ),
    "us_them": (
        ORAL,
        "In-group / out-group framing.",
        ["our people vs. their leaders"],
    ),
    "conflict_frame": (
        ORAL,
        "Story scaffolded around an opposition or struggle.",
        ["David against Goliath"],
    ),
    "epithet": (
        ORAL,
        "Formulaic descriptor attached to a noun (Homeric style).",
        ["wine-dark sea", "swift-footed Achilles"],
    ),
    "dramatic_pause": (
        ORAL,
        "Conspicuous suspension of speech.",
        ["And then… silence."],
    ),
    "aside": (
        ORAL,
        "Off-topic remark addressed semi-privately.",
        ["— though between you and me —"],
    ),
    "self_correction": (
        ORAL,
        "Speaker revising mid-utterance.",
        ["I went there— or rather, we went there."],
    ),
    "simple_conjunction": (
        ORAL,
        "Plain coordinator (and, but, so) joining ideas.",
        ["He came and he saw."],
    ),
    "additive_formal": (
        ORAL,
        "Loose 'and-then' chaining typical of oral narration.",
        ["So she went and then she saw and then…"],
    ),
    "causal_chain": (
        ORAL,
        "Sequence of cause-and-effect told as a story.",
        ["He fell because he tripped because the floor was wet."],
    ),
    "conceptual_metaphor": (
        ORAL,
        "Concrete analogy carrying abstract meaning.",
        ["time is money"],
    ),
    # ── Literate markers ───────────────────────────────────────────────
    "abstract_noun": (
        LITERATE,
        "Noun naming a concept, quality, or relation.",
        ["justice", "feasibility", "legitimacy"],
    ),
    "nominalization": (
        LITERATE,
        "Verbs and adjectives turned into nouns.",
        ["the implementation of", "demonstration of"],
    ),
    "agent_demoted": (
        LITERATE,
        "Doer of an action moved out of subject position.",
        ["mistakes were made (by us)"],
    ),
    "agentless_passive": (
        LITERATE,
        "Passive voice with the agent omitted entirely.",
        ["it was decided", "errors were made"],
    ),
    "objectifying_stance": (
        LITERATE,
        "Distancing observer language; 'one' instead of 'you'.",
        ["one might argue", "it has been observed"],
    ),
    "third_person_reference": (
        LITERATE,
        "Reference to entities outside the speech situation.",
        ["the committee", "the author"],
    ),
    "institutional_subject": (
        LITERATE,
        "Organization or office acting as the grammatical subject.",
        ["the court ruled", "the firm announced"],
    ),
    "categorical_statement": (
        LITERATE,
        "Strong universal claim without hedging.",
        ["all X are Y", "no exception is permitted"],
    ),
    "qualified_assertion": (
        LITERATE,
        "Claims with built-in limitations and scope restrictions.",
        ["in most cases…", "under certain conditions…"],
    ),
    "epistemic_hedge": (
        LITERATE,
        "Marker of uncertainty or guarded commitment.",
        ["it appears that", "may suggest"],
    ),
    "conditional": (
        LITERATE,
        "If-then framing; hypothetical reasoning.",
        ["should X be true…", "if Y, then Z"],
    ),
    "concessive": (
        LITERATE,
        "Acknowledging a counter-point before continuing.",
        ["although X, Y"],
    ),
    "concessive_connector": (
        LITERATE,
        "Logical connector signaling concession.",
        ["nevertheless", "even so", "however"],
    ),
    "contrastive": (
        LITERATE,
        "Explicit logical contrast between propositions.",
        ["whereas", "in contrast"],
    ),
    "causal_explicit": (
        LITERATE,
        "Marked logical causation rather than narrative chain.",
        ["because of which", "this entails that"],
    ),
    "definitional_move": (
        LITERATE,
        "Stipulating what a term means within the discourse.",
        ["By X we mean…", "X is defined as…"],
    ),
    "methodological_framing": (
        LITERATE,
        "Description of how the analysis was conducted.",
        ["we collected data via…", "the methodology employed"],
    ),
    "metadiscourse": (
        LITERATE,
        "Talk about the talk itself.",
        ["as discussed above", "in this section we will"],
    ),
    "citation": (
        LITERATE,
        "Pointing to an outside text or source.",
        ["(Smith 1998)", "as Foucault argues"],
    ),
    "footnote_reference": (
        LITERATE,
        "Auxiliary annotation pointing outside the main flow.",
        ["[1]", "see footnote 4"],
    ),
    "cross_reference": (
        LITERATE,
        "Pointer to another part of the same text.",
        ["see Section 3", "as noted earlier"],
    ),
    "evidential": (
        LITERATE,
        "Marker showing the source or basis of a claim.",
        ["according to the data", "the evidence shows"],
    ),
    "probability": (
        LITERATE,
        "Quantified or qualified likelihood expressions.",
        ["50% likely", "very probably"],
    ),
    "nested_clauses": (
        LITERATE,
        "Multi-level subordinate clauses inside one sentence.",
        ["the man who came when she said that…"],
    ),
    "relative_chain": (
        LITERATE,
        "Stacked relative clauses extending a noun phrase.",
        ["the report that the committee that the senate appointed produced"],
    ),
    "list_structure": (
        LITERATE,
        "Bulleted or enumerated item series.",
        ["1) … 2) … 3) …"],
    ),
    "enumeration": (
        LITERATE,
        "Inline counted listing.",
        ["first… second… third…"],
    ),
    "temporal_embedding": (
        LITERATE,
        "Time framed abstractly rather than anchored to now.",
        ["during the third quarter of the fiscal year"],
    ),
    "technical_term": (
        LITERATE,
        "Domain-specific specialist vocabulary.",
        ["heteroskedasticity", "phlogiston"],
    ),
    "technical_abbreviation": (
        LITERATE,
        "Specialist acronym or shorthand.",
        ["GDP", "ROI", "RNA"],
    ),
}


def category_for(marker: str) -> str:
    entry = MARKER_TAXONOMY.get(marker)
    return entry[0] if entry else LITERATE  # default to literate for unknowns


def description_for(marker: str) -> str:
    entry = MARKER_TAXONOMY.get(marker)
    return entry[1] if entry else "(no description available)"


def examples_for(marker: str) -> list[str]:
    entry = MARKER_TAXONOMY.get(marker)
    return entry[2] if entry else []


def display_name(marker: str) -> str:
    """Convert snake_case → 'Snake Case' for UI."""
    return marker.replace("_", " ").upper()
