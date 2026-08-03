"""
Tests for the grounded AI explanation generator.

Every test drives the generator with a FakeAIClient, so the "AI" prose is fully
controlled and no network is used. The evidence is built from
`RecommendationContext` objects constructed directly.
"""

import json

import pytest

from src.ai_client import FakeAIClient, TemporaryAIServiceError
from src.explanation_generator import ExplanationGenerator, NO_MATCH_SUMMARY
from src.orchestrator import RecommendationContext, VibeMatchOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_rec(title, artist, genre, mood, score, reasons, **attrs):
    song = {"title": title, "artist": artist, "genre": genre, "mood": mood}
    song.update(attrs)
    return {"title": title, "artist": artist, "score": score, "reasons": reasons, "song": song}


def make_context(recommendations, confidence=0.85, warnings=None, request="happy pop"):
    return RecommendationContext(
        original_request=request,
        parsed_preferences={"genre": "pop", "mood": "happy", "energy": 0.9},
        recommendations=recommendations,
        confidence=confidence,
        warnings=warnings or [],
    )


SUNRISE = make_rec(
    "Sunrise City", "Neon Echo", "pop", "happy", 11.07,
    "Mood match (+2.0), Genre match (+2.0), Energy similarity (+1.84)",
    energy=0.82,
)


def ai_reply(summary, explanations):
    return json.dumps({"summary": summary, "song_explanations": explanations})


# ---------------------------------------------------------------------------
# A valid grounded response
# ---------------------------------------------------------------------------
def test_valid_grounded_response():
    reply = ai_reply(
        "These upbeat pop picks fit your happy, high-energy request.",
        [{"title": "Sunrise City", "explanation": "Exact pop + happy match with high energy."}],
    )
    result = ExplanationGenerator(FakeAIClient(reply)).generate(make_context([SUNRISE]))

    assert result["summary"].startswith("These upbeat pop picks")
    assert result["confidence"] == 0.85
    assert len(result["song_explanations"]) == 1
    entry = result["song_explanations"][0]
    assert entry["title"] == "Sunrise City"
    assert entry["artist"] == "Neon Echo"          # artist filled from retrieved data
    assert "pop" in entry["explanation"].lower()


def test_generator_ignores_songs_the_ai_invents():
    # The AI hallucinates an off-list song; it must NOT appear in the output.
    reply = ai_reply(
        "Summary.",
        [
            {"title": "Sunrise City", "explanation": "Real one."},
            {"title": "Totally Made Up Song", "explanation": "Invented."},
        ],
    )
    result = ExplanationGenerator(FakeAIClient(reply)).generate(make_context([SUNRISE]))

    titles = [e["title"] for e in result["song_explanations"]]
    assert titles == ["Sunrise City"]  # only the retrieved song survives


# ---------------------------------------------------------------------------
# No exact genre match
# ---------------------------------------------------------------------------
def test_no_exact_genre_match_is_reported():
    indie = make_rec(
        "Rooftop Lights", "Indigo Parade", "indie pop", "happy", 9.76,
        "Mood match (+2.0), Genre related (+1.0)",
    )
    reply = ai_reply(
        "No exact pop match was found, so here is a closely related indie-pop track.",
        [{"title": "Rooftop Lights", "explanation": "Indie pop is a related genre, and the mood matches."}],
    )
    result = ExplanationGenerator(FakeAIClient(reply)).generate(make_context([indie]))

    assert "no exact" in result["summary"].lower()
    assert result["song_explanations"][0]["title"] == "Rooftop Lights"


# ---------------------------------------------------------------------------
# Low-confidence response carries the low confidence through
# ---------------------------------------------------------------------------
def test_low_confidence_is_passed_through():
    ctx = make_context(
        [SUNRISE],
        confidence=0.3,
        warnings=["Low confidence in understanding your request; results may be approximate."],
    )
    result = ExplanationGenerator(FakeAIClient(ai_reply("Best guess.", []))).generate(ctx)

    assert result["confidence"] == 0.3
    assert any("confidence" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# Conflicting preferences: warnings are preserved
# ---------------------------------------------------------------------------
def test_conflicting_preferences_warning_is_preserved():
    ctx = make_context(
        [SUNRISE],
        warnings=["The request contains conflicting mood and energy preferences (high energy paired with a calm mood)."],
    )
    result = ExplanationGenerator(FakeAIClient(ai_reply("Note the conflict.", []))).generate(ctx)

    assert any("conflicting" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# Empty retrieved list -> honest no-match, no AI call
# ---------------------------------------------------------------------------
def test_empty_retrieved_list_returns_no_match_without_calling_ai():
    fake = FakeAIClient(ai_reply("should not be used", []))
    result = ExplanationGenerator(fake).generate(make_context([]))

    assert result["summary"] == NO_MATCH_SUMMARY
    assert result["song_explanations"] == []
    assert fake.calls == []  # AI was never called


# ---------------------------------------------------------------------------
# AI service error -> graceful deterministic fallback
# ---------------------------------------------------------------------------
def test_ai_service_error_falls_back_to_deterministic_reasons():
    fake = FakeAIClient(ai_reply("unused", []))
    fake.raise_on_next(TemporaryAIServiceError("service down"))

    result = ExplanationGenerator(fake).generate(make_context([SUNRISE]))

    # Still returns something useful, flagged with a warning.
    assert any("unavailable" in w.lower() for w in result["warnings"])
    assert len(result["song_explanations"]) == 1
    # The fallback explanation is built from the deterministic scoring reasons.
    assert "Genre match" in result["song_explanations"][0]["explanation"]


# ---------------------------------------------------------------------------
# Orchestrator integration: recommend_and_explain attaches the explanation
# ---------------------------------------------------------------------------
def test_orchestrator_attaches_grounded_explanation():
    parse_reply = json.dumps(
        {"genre": "pop", "mood": "happy", "energy": 0.9, "confidence": 0.85, "uncertain_fields": []}
    )
    explain_reply = ai_reply(
        "Upbeat pop that matches your request.",
        [{"title": "Sunrise City", "explanation": "Exact match."}],
    )
    # The parser and the explainer each get their own fake reply, in call order.
    orch = VibeMatchOrchestrator(FakeAIClient(responses=[parse_reply, explain_reply]))

    ctx = orch.recommend_and_explain("high energy happy pop")

    assert ctx.allowed is True
    assert ctx.explanation is not None
    assert ctx.explanation["summary"]
    assert ctx.explanation["song_explanations"][0]["title"] == "Sunrise City"


def test_orchestrator_skips_explanation_for_blocked_input():
    orch = VibeMatchOrchestrator(FakeAIClient("{}"))
    ctx = orch.recommend_and_explain("")  # empty -> blocked

    assert ctx.allowed is False
    assert ctx.explanation is None
