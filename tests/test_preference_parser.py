"""
Tests for the natural-language preference parser.

Every test drives the parser with a FakeAIClient holding a canned JSON reply, so
nothing here makes a real API call or needs a network. Each test controls exactly
what the "AI" returns and then checks how the parser validates it.
"""

import json

import pytest

from src.ai_client import FakeAIClient
from src.preference_parser import (
    PreferenceParser,
    ParsedPreferences,
    PreferenceParseError,
)


def make_parser(ai_reply: str, **kwargs) -> PreferenceParser:
    """Build a parser whose fake AI always returns `ai_reply`."""
    return PreferenceParser(FakeAIClient(ai_reply), **kwargs)


# A complete, well-formed reply for the sample request in the task.
CLEAR_REPLY = json.dumps(
    {
        "genre": None,
        "mood": "focused",
        "energy": 0.3,
        "tempo_bpm": 90,
        "valence": None,
        "danceability": None,
        "acousticness": 0.8,
        "instrumentalness": 0.9,
        "popularity": None,
        "release_decade": None,
        "mood_tag": "relaxing",
        "explicit": "no",
        "artist_type": None,
        "activity": "coding",
        "confidence": 0.85,
        "uncertain_fields": [],
    }
)


# ---------------------------------------------------------------------------
# A clear, detailed request
# ---------------------------------------------------------------------------
def test_clear_request_is_parsed_into_structured_fields():
    parser = make_parser(CLEAR_REPLY)

    prefs = parser.parse("Calm instrumental music for late-night coding, low energy, no explicit lyrics.")

    assert isinstance(prefs, ParsedPreferences)
    assert prefs.mood == "focused"
    assert prefs.energy == 0.3
    assert prefs.instrumentalness == 0.9
    assert prefs.explicit == "no"
    assert prefs.activity == "coding"
    assert prefs.confidence == 0.85
    assert prefs.needs_clarification is False


# ---------------------------------------------------------------------------
# A vague request -> low confidence, flagged for clarification
# ---------------------------------------------------------------------------
def test_vague_request_flags_needs_clarification():
    reply = json.dumps(
        {
            "mood": None,
            "energy": None,
            "confidence": 0.2,
            "uncertain_fields": ["genre", "mood", "energy"],
        }
    )
    prefs = make_parser(reply).parse("Play me something.")

    assert prefs.needs_clarification is True
    assert prefs.confidence == 0.2
    assert "mood" in prefs.uncertain_fields


# ---------------------------------------------------------------------------
# A request with no genre -> parser must NOT invent one
# ---------------------------------------------------------------------------
def test_no_genre_stays_none():
    reply = json.dumps(
        {"genre": None, "mood": "happy", "energy": 0.7,
         "confidence": 0.8, "uncertain_fields": []}
    )
    prefs = make_parser(reply).parse("Something upbeat and happy.")

    assert prefs.genre is None
    assert prefs.mood == "happy"


# ---------------------------------------------------------------------------
# Invalid JSON -> controlled error
# ---------------------------------------------------------------------------
def test_invalid_json_raises_controlled_error():
    parser = make_parser("Sorry, I can't do that as JSON { not valid ")

    with pytest.raises(PreferenceParseError):
        parser.parse("anything")


def test_non_object_json_raises_controlled_error():
    parser = make_parser(json.dumps([1, 2, 3]))  # valid JSON, but not an object

    with pytest.raises(PreferenceParseError):
        parser.parse("anything")


# ---------------------------------------------------------------------------
# Out-of-range numerical values -> clamped into valid ranges
# ---------------------------------------------------------------------------
def test_out_of_range_values_are_clamped():
    reply = json.dumps(
        {
            "energy": 5.0,          # > 1.0
            "valence": -3.0,        # < 0.0
            "tempo_bpm": 9999,      # far above the supported range
            "popularity": 500,      # > 100
            "confidence": 2.0,      # > 1.0
            "uncertain_fields": [],
        }
    )
    prefs = make_parser(reply).parse("loud fast music")

    assert prefs.energy == 1.0
    assert prefs.valence == 0.0
    assert prefs.tempo_bpm == 220.0   # TEMPO_MAX
    assert prefs.popularity == 100
    assert prefs.confidence == 1.0


# ---------------------------------------------------------------------------
# Missing optional fields -> default to None
# ---------------------------------------------------------------------------
def test_missing_optional_fields_default_to_none():
    reply = json.dumps({"mood": "chill", "confidence": 0.7, "uncertain_fields": []})
    prefs = make_parser(reply).parse("chill music")

    assert prefs.mood == "chill"
    assert prefs.genre is None
    assert prefs.energy is None
    assert prefs.tempo_bpm is None
    assert prefs.popularity is None
    assert prefs.explicit is None


# ---------------------------------------------------------------------------
# Low confidence -> needs_clarification True
# ---------------------------------------------------------------------------
def test_low_confidence_sets_needs_clarification():
    reply = json.dumps({"mood": "sad", "confidence": 0.3, "uncertain_fields": []})
    prefs = make_parser(reply).parse("idk, something")

    assert prefs.needs_clarification is True


def test_high_confidence_does_not_flag_clarification():
    reply = json.dumps({"mood": "sad", "confidence": 0.9, "uncertain_fields": []})
    prefs = make_parser(reply).parse("melancholy piano")

    assert prefs.needs_clarification is False


# ---------------------------------------------------------------------------
# Empty input -> handled safely, no AI call
# ---------------------------------------------------------------------------
def test_empty_input_needs_clarification_and_skips_ai():
    fake = FakeAIClient(CLEAR_REPLY)
    parser = PreferenceParser(fake)

    prefs = parser.parse("   ")

    assert prefs.needs_clarification is True
    assert prefs.confidence == 0.0
    # The AI was never called for empty input.
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Explicit normalization + code-fence tolerance (belt-and-suspenders)
# ---------------------------------------------------------------------------
def test_explicit_is_normalized_and_code_fences_are_stripped():
    reply = "```json\n" + json.dumps(
        {"explicit": True, "confidence": 0.8, "uncertain_fields": []}
    ) + "\n```"
    prefs = make_parser(reply).parse("clean music only")

    assert prefs.explicit == "yes"
