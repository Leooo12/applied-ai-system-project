"""
Tests for the retrieval orchestrator.

Every test uses a FakeAIClient (no network) so the parse step is deterministic.
Retrieval runs against the real data/songs.csv, so rankings are the genuine
recommender output -- proving the AI never controls ordering.
"""

import json

import pytest

from src.ai_client import FakeAIClient
from src.orchestrator import (
    VibeMatchOrchestrator,
    RecommendationContext,
    CatalogNotFoundError,
)


# A confident parse of a "high-energy happy pop" request.
POP_REPLY = json.dumps(
    {
        "genre": "pop",
        "mood": "happy",
        "energy": 0.9,
        "confidence": 0.85,
        "uncertain_fields": [],
    }
)


def make_orchestrator(reply=POP_REPLY, **kwargs):
    return VibeMatchOrchestrator(FakeAIClient(reply), **kwargs)


# ---------------------------------------------------------------------------
# A clear request retrieves appropriate songs
# ---------------------------------------------------------------------------
def test_clear_request_retrieves_appropriate_songs():
    ctx = make_orchestrator().recommend("high energy happy pop for a party")

    assert isinstance(ctx, RecommendationContext)
    assert ctx.allowed is True
    assert len(ctx.recommendations) == 5
    # The deterministic recommender puts the exact pop/happy match first.
    top = ctx.recommendations[0]["song"]
    assert top["title"] == "Sunrise City"
    assert top["genre"] == "pop"
    assert top["mood"] == "happy"


# ---------------------------------------------------------------------------
# Parsed preferences are actually passed to the recommender (and None-dropped)
# ---------------------------------------------------------------------------
def test_parsed_preferences_are_passed_to_recommender():
    recorded = {}

    def spy_recommend(prefs, songs, k=5):
        recorded["prefs"] = prefs
        recorded["k"] = k
        recorded["num_songs"] = len(songs)
        return [({"title": "X", "artist": "Y"}, 9.9, "Genre match (+2.0)")]

    ctx = make_orchestrator(recommend_fn=spy_recommend).recommend("happy pop")

    # Only the three specified fields were passed -- None fields were dropped.
    assert recorded["prefs"] == {"genre": "pop", "mood": "happy", "energy": 0.9}
    assert ctx.parsed_preferences == recorded["prefs"]
    assert recorded["k"] == 5
    assert recorded["num_songs"] == 36  # real catalog was loaded and passed in


# ---------------------------------------------------------------------------
# Empty input stops before retrieval
# ---------------------------------------------------------------------------
def test_empty_input_stops_before_retrieval():
    calls = []

    def spy_recommend(prefs, songs, k=5):
        calls.append(1)
        return []

    fake = FakeAIClient(POP_REPLY)
    orch = VibeMatchOrchestrator(fake, recommend_fn=spy_recommend)

    ctx = orch.recommend("")

    assert ctx.allowed is False
    assert ctx.recommendations == []
    assert ctx.errors
    assert calls == []           # retrieval never ran
    assert fake.calls == []      # the AI was never called either


# ---------------------------------------------------------------------------
# A low-confidence request includes a warning
# ---------------------------------------------------------------------------
def test_low_confidence_request_includes_warning():
    reply = json.dumps(
        {"mood": "chill", "energy": 0.3, "confidence": 0.2, "uncertain_fields": ["genre"]}
    )
    ctx = make_orchestrator(reply=reply).recommend("uh, something chill maybe")

    assert ctx.needs_clarification is True
    assert any("confidence" in w.lower() for w in ctx.warnings)
    # It still retrieves -- low confidence warns, it does not block.
    assert ctx.recommendations


# ---------------------------------------------------------------------------
# A missing CSV file returns a controlled error
# ---------------------------------------------------------------------------
def test_missing_csv_raises_controlled_error():
    orch = make_orchestrator(csv_path="data/does_not_exist.csv")

    with pytest.raises(CatalogNotFoundError):
        orch.recommend("high energy happy pop")


# ---------------------------------------------------------------------------
# The fake AI client makes the run reproducible
# ---------------------------------------------------------------------------
def test_runs_are_reproducible_with_fake_client():
    orch = make_orchestrator()

    first = [r["song"]["title"] for r in orch.recommend("happy pop").recommendations]
    second = [r["song"]["title"] for r in orch.recommend("happy pop").recommendations]

    assert first == second


# ---------------------------------------------------------------------------
# Output contains scores and deterministic reasons
# ---------------------------------------------------------------------------
def test_output_contains_scores_and_deterministic_reasons():
    ctx = make_orchestrator().recommend("high energy happy pop")

    top = ctx.recommendations[0]
    assert isinstance(top["score"], float)
    assert top["score"] > 0
    # Reasons come straight from the recommender's per-feature breakdown.
    assert "match" in top["reasons"].lower()
    assert "Genre match" in top["reasons"] or "Mood match" in top["reasons"]


# ---------------------------------------------------------------------------
# Agentic workflow: generate -> verify -> repair(once) -> fallback
# ---------------------------------------------------------------------------
from src.verifier import Verifier


class _StubExplainer:
    """Explanation generator that returns queued dicts, recording feedback."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.feedback_calls = []  # feedback passed on each call (None on first)

    def generate(self, context, feedback=None):
        self.feedback_calls.append(feedback)
        index = min(len(self.feedback_calls) - 1, len(self._outputs) - 1)
        return self._outputs[index]


def _expl(title, artist, explanation="A pop, happy track."):
    return {
        "summary": "Here are your picks.",
        "song_explanations": [{"title": title, "artist": artist, "explanation": explanation}],
    }


def _orch_with_explainer(stub):
    # Parser gets a confident pop reply; retrieval uses the real catalog.
    return VibeMatchOrchestrator(
        FakeAIClient(POP_REPLY),
        explanation_generator=stub,
        verifier=Verifier(),
    )


def test_valid_explanation_is_used_without_repair():
    stub = _StubExplainer([_expl("Sunrise City", "Neon Echo")])
    ctx = _orch_with_explainer(stub).recommend_and_explain("high energy happy pop")

    assert ctx.explanation_method == "generated"
    assert len(stub.feedback_calls) == 1          # generated once, never repaired
    assert ctx.explanation["song_explanations"][0]["title"] == "Sunrise City"


def test_invalid_explanation_is_repaired_once():
    stub = _StubExplainer([
        _expl("Totally Made Up Song", "Ghost"),   # invalid -> triggers repair
        _expl("Sunrise City", "Neon Echo"),       # repaired -> valid
    ])
    ctx = _orch_with_explainer(stub).recommend_and_explain("high energy happy pop")

    assert ctx.explanation_method == "repaired"
    assert len(stub.feedback_calls) == 2          # exactly one repair attempt
    assert stub.feedback_calls[1] is not None     # repair received feedback
    assert ctx.explanation["song_explanations"][0]["title"] == "Sunrise City"


def test_failed_repair_falls_back_to_deterministic():
    stub = _StubExplainer([
        _expl("Totally Made Up Song", "Ghost"),   # invalid
        _expl("Still Not Real", "Ghost"),         # still invalid after repair
    ])
    ctx = _orch_with_explainer(stub).recommend_and_explain("high energy happy pop")

    assert ctx.explanation_method == "fallback"
    assert len(stub.feedback_calls) == 2          # no more than one repair attempt
    # Fallback is built from the REAL retrieved songs + their scoring reasons.
    titles = [e["title"] for e in ctx.explanation["song_explanations"]]
    assert "Sunrise City" in titles
    assert "Totally Made Up Song" not in titles
    assert any("Genre match" in e["explanation"] for e in ctx.explanation["song_explanations"])
    assert any("could not be verified" in w for w in ctx.explanation["warnings"])
