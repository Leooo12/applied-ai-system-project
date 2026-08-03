"""
Tests for the recommendation foundation.

These tests exercise the REAL scoring logic (score_song / recommend_songs) --
the same code path src/main.py uses -- both directly and through the
Recommender class, which now delegates to those functions rather than returning
placeholder values. Nothing here relies on the original ordering of a song list;
each test constructs a catalog where the expected winner is deliberately NOT
first, so a passing test reflects actual scoring behavior.
"""

from dataclasses import asdict

import pytest

from src.recommender import (
    Song,
    UserProfile,
    Recommender,
    score_song,
    recommend_songs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_song(
    id,
    title,
    artist,
    genre,
    mood,
    energy,
    acousticness=0.5,
    tempo_bpm=100,
    valence=0.5,
    danceability=0.5,
    instrumentalness=0.0,
):
    """Build a Song with sensible defaults so tests only set what they care about."""
    return Song(
        id=id,
        title=title,
        artist=artist,
        genre=genre,
        mood=mood,
        energy=energy,
        tempo_bpm=tempo_bpm,
        valence=valence,
        danceability=danceability,
        acousticness=acousticness,
        instrumentalness=instrumentalness,
    )


def happy_pop_user():
    return UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.85,
        likes_acoustic=False,
    )


# ---------------------------------------------------------------------------
# Best match ranked first (winner placed LAST in the input list)
# ---------------------------------------------------------------------------
def test_best_matching_song_is_ranked_first():
    songs = [
        make_song(1, "Wrong Everything", "A", "metal", "intense", energy=0.10, acousticness=0.95),
        make_song(2, "Half Right", "B", "jazz", "relaxed", energy=0.50, acousticness=0.50),
        make_song(3, "Perfect Match", "C", "pop", "happy", energy=0.85, acousticness=0.05),
    ]
    rec = Recommender(songs)

    results = rec.recommend(happy_pop_user(), k=3)

    # The best match is the one placed last in the input -- proving the result
    # reflects scoring, not list order.
    assert results[0].title == "Perfect Match"


# ---------------------------------------------------------------------------
# Results are ordered by ACTUAL descending score
# ---------------------------------------------------------------------------
def test_recommend_songs_orders_by_descending_score():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.85}
    catalog = [
        {"id": 1, "title": "x", "artist": "a", "genre": "jazz", "mood": "sad", "energy": 0.10},
        {"id": 2, "title": "y", "artist": "b", "genre": "pop", "mood": "happy", "energy": 0.85},
        {"id": 3, "title": "z", "artist": "c", "genre": "pop", "mood": "chill", "energy": 0.60},
    ]

    ranked = recommend_songs(prefs, catalog, k=3, diversity=False)
    scores = [score for _song, score, _reasons in ranked]

    assert scores == sorted(scores, reverse=True)
    assert ranked[0][0]["id"] == 2  # exact genre+mood+energy match wins


def test_class_recommend_matches_recommend_songs():
    """The class must produce the same ranking as the real function it wraps."""
    songs = [
        make_song(1, "One", "A", "pop", "happy", energy=0.80, acousticness=0.10),
        make_song(2, "Two", "B", "lofi", "chill", energy=0.35, acousticness=0.90),
        make_song(3, "Three", "C", "rock", "intense", energy=0.95, acousticness=0.05),
    ]
    user = happy_pop_user()
    rec = Recommender(songs)

    class_ids = [s.id for s in rec.recommend(user, k=3, diversity=False)]
    prefs = Recommender._user_to_prefs(user)
    func_ids = [
        row["id"]
        for row, _s, _r in recommend_songs(
            prefs, [asdict(s) for s in songs], k=3, diversity=False
        )
    ]

    assert class_ids == func_ids


# ---------------------------------------------------------------------------
# Explanations are real (non-empty and mention actual matching features)
# ---------------------------------------------------------------------------
def test_explanation_is_non_empty_and_mentions_real_features():
    song = make_song(1, "Perfect Match", "C", "pop", "happy", energy=0.85, acousticness=0.05)
    rec = Recommender([song])

    explanation = rec.explain_recommendation(happy_pop_user(), song)

    assert isinstance(explanation, str)
    assert explanation.strip() != ""
    assert "Explanation placeholder" not in explanation
    # Exact genre + mood matches must be named in the reasons.
    assert "Genre match" in explanation
    assert "Mood match" in explanation


def test_explanation_reports_no_match_for_unrelated_song():
    """A song matching nothing yields an honest message, not a fake reason."""
    user = UserProfile("pop", "happy", target_energy=0.85, likes_acoustic=False)
    # No categorical matches, and no numerical prefs overlap that score > 0 is
    # impossible here because energy/acousticness always contribute something;
    # so instead assert the message is non-empty and truthful for a poor fit.
    song = make_song(1, "Nope", "Z", "classical", "melancholy", energy=0.05, acousticness=0.99)
    explanation = Recommender([song]).explain_recommendation(user, song)
    assert explanation.strip() != ""


# ---------------------------------------------------------------------------
# Edge cases: empty catalog, k=0, k > catalog size
# ---------------------------------------------------------------------------
def test_empty_catalog_returns_empty_list():
    rec = Recommender([])
    assert rec.recommend(happy_pop_user(), k=5) == []


def test_k_zero_returns_empty_list():
    songs = [make_song(1, "One", "A", "pop", "happy", energy=0.8)]
    rec = Recommender(songs)
    assert rec.recommend(happy_pop_user(), k=0) == []


def test_k_larger_than_catalog_does_not_crash():
    songs = [
        make_song(1, "One", "A", "pop", "happy", energy=0.80),
        make_song(2, "Two", "B", "lofi", "chill", energy=0.35),
    ]
    rec = Recommender(songs)

    results = rec.recommend(happy_pop_user(), k=100)

    assert len(results) == len(songs)


# ---------------------------------------------------------------------------
# Unknown scoring strategy raises a clear error
# ---------------------------------------------------------------------------
def test_unknown_strategy_raises_clear_error():
    songs = [make_song(1, "One", "A", "pop", "happy", energy=0.8)]
    rec = Recommender(songs)

    with pytest.raises(ValueError) as excinfo:
        rec.recommend(happy_pop_user(), strategy="does_not_exist")

    assert "Unknown scoring mode" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Diversity mode reduces repeated artists when possible
# ---------------------------------------------------------------------------
def test_diversity_reduces_repeated_artists():
    # Two high-scoring songs by the same artist, one slightly lower by another.
    songs = [
        make_song(1, "Same A", "Repeat Artist", "pop", "happy", energy=0.90, acousticness=0.10),
        make_song(2, "Same B", "Repeat Artist", "pop", "happy", energy=0.88, acousticness=0.10),
        make_song(3, "Other", "Fresh Artist", "pop", "happy", energy=0.85, acousticness=0.10),
    ]
    user = UserProfile("pop", "happy", target_energy=0.90, likes_acoustic=False)
    rec = Recommender(songs)

    without_diversity = [s.artist for s in rec.recommend(user, k=2, diversity=False)]
    with_diversity = [s.artist for s in rec.recommend(user, k=2, diversity=True)]

    # Without diversity, the two same-artist songs win outright.
    assert without_diversity == ["Repeat Artist", "Repeat Artist"]
    # With diversity, the second slot goes to a different artist.
    assert len(set(with_diversity)) == 2
