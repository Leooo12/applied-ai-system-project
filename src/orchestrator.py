"""
Retrieval orchestrator for VibeMatch AI.

This is the "R" in RAG (Retrieval-Augmented Generation) -- it turns a
natural-language request into a set of REAL songs retrieved from the catalog,
ready to be handed to the AI later for explanation.

The pipeline, in order:

    request text
      -> guardrail on the raw text        (stop early if unsafe/off-topic/empty)
      -> parse into structured prefs       (AI understands language)
      -> guardrail on the parsed prefs     (ranges, conflicts, coverage)
      -> drop None fields                  (keep only what the user specified)
      -> load songs from data/songs.csv
      -> recommend_songs(prefs, songs)     (deterministic ranking -- NOT the AI)
      -> RecommendationContext

Two design rules make this genuine retrieval augmentation:

* The language model NEVER ranks songs. It only extracts preferences; ordering
  and scores come entirely from `src/recommender.py`.
* The songs returned here are the exact rows a later step will explain, so the
  eventual AI answer is grounded in retrieved data, not invented alongside it.
"""

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from src.ai_client import AIClient
from src.guardrails import Guardrails
from src.preference_parser import ParsedPreferences, PreferenceParser
from src.recommender import load_songs, recommend_songs


DEFAULT_CSV_PATH = "data/songs.csv"
DEFAULT_TOP_K = 5

# The song-attribute fields the recommender can actually score on. `activity`,
# `confidence`, etc. from ParsedPreferences are intentionally excluded -- they
# are not song attributes.
SCORING_FIELDS = (
    "genre", "mood", "energy", "tempo_bpm", "valence", "danceability",
    "acousticness", "instrumentalness", "popularity", "release_decade",
    "mood_tag", "explicit", "artist_type",
)


class OrchestratorError(Exception):
    """Base class for controlled orchestrator failures."""


class CatalogNotFoundError(OrchestratorError):
    """Raised when the song catalog CSV is missing or unreadable."""


@dataclass
class RecommendationContext:
    """
    The structured output of one retrieval run.

    `recommendations` is a list of dicts, each `{"title", "artist", "score",
    "reasons", "song"}` -- carrying the full retrieved song row plus the
    deterministic score and reasons from the recommender. `allowed` is False when
    a guardrail stopped the request before (or instead of) retrieval.
    """

    original_request: str
    parsed_preferences: dict
    recommendations: List[dict]
    confidence: float
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    needs_clarification: bool = False
    allowed: bool = True


def _default_load(csv_path: str) -> List[dict]:
    """
    Load the catalog, raising a controlled error if the file is missing.

    `recommender.load_songs` deliberately returns [] for a missing file; here we
    want a *distinct, catchable* failure so a bad path doesn't look like an empty
    catalog.
    """
    if not os.path.exists(csv_path):
        raise CatalogNotFoundError(f"Song catalog not found at: {csv_path}")
    return load_songs(csv_path)


class VibeMatchOrchestrator:
    """
    Coordinates guardrails, parsing, and retrieval into one call: `recommend()`.

    Dependencies (AI client, guardrails, parser, load/recommend functions) are
    injectable so tests can run offline and deterministically with fakes/spies.
    """

    def __init__(
        self,
        ai_client: AIClient,
        guardrails: Optional[Guardrails] = None,
        parser: Optional[PreferenceParser] = None,
        recommend_fn: Callable = recommend_songs,
        load_fn: Callable[[str], List[dict]] = _default_load,
        csv_path: str = DEFAULT_CSV_PATH,
        top_k: int = DEFAULT_TOP_K,
    ):
        self._guardrails = guardrails or Guardrails()
        self._parser = parser or PreferenceParser(ai_client)
        self._recommend_fn = recommend_fn
        self._load_fn = load_fn
        self._csv_path = csv_path
        self._top_k = top_k

    def recommend(self, request: str) -> RecommendationContext:
        """Run the full guardrail -> parse -> retrieve pipeline for one request."""
        # 1. Guard the raw text. If it's blocked, stop BEFORE parsing/retrieval.
        input_check = self._guardrails.check_input(request)
        if not input_check.allowed:
            return RecommendationContext(
                original_request=request or "",
                parsed_preferences={},
                recommendations=[],
                confidence=0.0,
                warnings=list(input_check.warnings),
                errors=list(input_check.errors),
                needs_clarification=input_check.needs_clarification,
                allowed=False,
            )

        warnings: List[str] = list(input_check.warnings)

        # 2. Parse natural language into structured preferences (AI step).
        parsed = self._parser.parse(request)

        # 3. Guard the parsed preferences (ranges, conflicts, coverage).
        pref_check = self._guardrails.check_preferences(parsed)
        warnings.extend(pref_check.warnings)
        needs_clarification = pref_check.needs_clarification or parsed.needs_clarification
        if needs_clarification:
            warnings.append(
                "Low confidence in understanding your request; results may be approximate."
            )

        # An out-of-range value is a hard stop (should be rare -- the parser clamps).
        if not pref_check.allowed:
            return RecommendationContext(
                original_request=request,
                parsed_preferences={},
                recommendations=[],
                confidence=parsed.confidence,
                warnings=warnings,
                errors=list(pref_check.errors),
                needs_clarification=needs_clarification,
                allowed=False,
            )

        # 4. Keep only the fields the user actually specified.
        prefs = _preferences_to_dict(parsed)

        # 5. Load the catalog (controlled error if the file is missing).
        songs = self._load_fn(self._csv_path)

        # 6. Retrieve + rank -- deterministically, via the recommender. The AI
        #    has no say in ordering or scores.
        ranked = self._recommend_fn(prefs, songs, k=self._top_k)
        recommendations = [
            {
                "title": song.get("title"),
                "artist": song.get("artist"),
                "score": score,
                "reasons": reasons,
                "song": song,
            }
            for song, score, reasons in ranked
        ]

        return RecommendationContext(
            original_request=request,
            parsed_preferences=prefs,
            recommendations=recommendations,
            confidence=parsed.confidence,
            warnings=warnings,
            errors=[],
            needs_clarification=needs_clarification,
            allowed=True,
        )


def _preferences_to_dict(prefs: ParsedPreferences) -> dict:
    """Build the recommender's prefs dict, dropping any field left as None."""
    return {
        name: getattr(prefs, name)
        for name in SCORING_FIELDS
        if getattr(prefs, name) is not None
    }
