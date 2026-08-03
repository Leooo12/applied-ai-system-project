"""
Tests for the grounding verifier.

The verifier is pure logic -- no AI, no network. Each test builds a fake
explanation dict and the retrieved recommendations it should be checked against.
"""

from src.verifier import Verifier, VerificationResult


verifier = Verifier()


def make_rec(title, artist, genre, mood, reasons="Genre match (+2.0)", **attrs):
    song = {"title": title, "artist": artist, "genre": genre, "mood": mood}
    song.update(attrs)
    return {"title": title, "artist": artist, "score": 9.0, "reasons": reasons, "song": song}


SUNRISE = make_rec("Sunrise City", "Neon Echo", "pop", "happy")
RETRIEVED = [SUNRISE]


def explanation(song_explanations, summary="Here are your picks."):
    return {"summary": summary, "song_explanations": song_explanations}


# ---------------------------------------------------------------------------
# Valid response
# ---------------------------------------------------------------------------
def test_valid_response_passes():
    expl = explanation(
        [{"title": "Sunrise City", "artist": "Neon Echo",
          "explanation": "A pop track with a happy mood, matching your request."}]
    )
    result = verifier.verify(expl, RETRIEVED, confidence=0.85)

    assert isinstance(result, VerificationResult)
    assert result.passed is True
    assert result.errors == []


# ---------------------------------------------------------------------------
# Invented song title
# ---------------------------------------------------------------------------
def test_invented_title_fails():
    expl = explanation(
        [{"title": "Ghost Song", "artist": "Nobody", "explanation": "Made up."}]
    )
    result = verifier.verify(expl, RETRIEVED, confidence=0.85)

    assert result.passed is False
    assert "Ghost Song" in result.unsupported_titles


# ---------------------------------------------------------------------------
# Wrong artist
# ---------------------------------------------------------------------------
def test_wrong_artist_fails():
    expl = explanation(
        [{"title": "Sunrise City", "artist": "Wrong Artist",
          "explanation": "A pop, happy track."}]
    )
    result = verifier.verify(expl, RETRIEVED, confidence=0.85)

    assert result.passed is False
    assert result.unsupported_claims
    assert any("artist" in c.lower() for c in result.unsupported_claims)


# ---------------------------------------------------------------------------
# Wrong mood or genre
# ---------------------------------------------------------------------------
def test_wrong_genre_fails():
    expl = explanation(
        [{"title": "Sunrise City", "artist": "Neon Echo",
          "explanation": "This is a jazz recording for late nights."}]
    )
    result = verifier.verify(expl, RETRIEVED, confidence=0.85)

    assert result.passed is False
    assert any("genre" in c.lower() for c in result.unsupported_claims)


def test_wrong_mood_fails():
    expl = explanation(
        [{"title": "Sunrise City", "artist": "Neon Echo",
          "explanation": "A deeply sad ballad."}]
    )
    result = verifier.verify(expl, RETRIEVED, confidence=0.85)

    assert result.passed is False
    assert any("mood" in c.lower() for c in result.unsupported_claims)


# ---------------------------------------------------------------------------
# Missing reason
# ---------------------------------------------------------------------------
def test_missing_reason_fails():
    expl = explanation(
        [{"title": "Sunrise City", "artist": "Neon Echo", "explanation": "   "}]
    )
    result = verifier.verify(expl, RETRIEVED, confidence=0.85)

    assert result.passed is False
    assert any("missing reason" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Empty recommendation section when songs were retrieved
# ---------------------------------------------------------------------------
def test_empty_section_with_retrieved_songs_fails():
    result = verifier.verify(explanation([]), RETRIEVED, confidence=0.85)
    assert result.passed is False


def test_empty_section_with_no_retrieved_songs_is_ok():
    # A genuine no-match (nothing retrieved, nothing explained) is not a failure.
    result = verifier.verify(explanation([]), [], confidence=0.85)
    assert result.passed is True


# ---------------------------------------------------------------------------
# Overconfidence at low confidence -> warning (not a hard failure)
# ---------------------------------------------------------------------------
def test_overconfidence_at_low_confidence_warns():
    expl = explanation(
        [{"title": "Sunrise City", "artist": "Neon Echo",
          "explanation": "This is definitely the perfect match for you."}],
        summary="Absolutely certain about these.",
    )
    result = verifier.verify(expl, RETRIEVED, confidence=0.2)

    assert result.warnings
    assert any("certainty" in w.lower() for w in result.warnings)
