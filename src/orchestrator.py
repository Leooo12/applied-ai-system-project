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

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from src.ai_client import AIClient
from src.app_logging import get_logger, log_event, safe_error_message
from src.explanation_generator import ExplanationGenerator
from src.guardrails import Guardrails
from src.preference_parser import ParsedPreferences, PreferenceParser, PreferenceParseError
from src.recommender import load_songs, recommend_songs
from src.verifier import Verifier, VerificationResult

logger = get_logger("vibematch.orchestrator")

DEFAULT_STRATEGY = "balanced"


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
    # Populated by `recommend_and_explain` with the grounded AI explanation
    # ({"summary", "song_explanations", "confidence", "warnings"}); None until then.
    explanation: Optional[dict] = None
    # How the final explanation was produced: "generated", "repaired", or
    # "fallback" (deterministic). None until `recommend_and_explain` runs.
    explanation_method: Optional[str] = None


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
        explanation_generator: Optional[ExplanationGenerator] = None,
        verifier: Optional[Verifier] = None,
        recommend_fn: Callable = recommend_songs,
        load_fn: Callable[[str], List[dict]] = _default_load,
        csv_path: str = DEFAULT_CSV_PATH,
        top_k: int = DEFAULT_TOP_K,
        strategy: str = DEFAULT_STRATEGY,
    ):
        self._guardrails = guardrails or Guardrails()
        self._parser = parser or PreferenceParser(ai_client)
        self._explainer = explanation_generator or ExplanationGenerator(ai_client)
        self._verifier = verifier or Verifier()
        self._recommend_fn = recommend_fn
        self._load_fn = load_fn
        self._csv_path = csv_path
        self._top_k = top_k
        # Label only -- the recommender uses its balanced default; recorded so
        # logs report which ranking philosophy produced the results.
        self._strategy = strategy

    def recommend(self, request: str) -> RecommendationContext:
        """Run the full guardrail -> parse -> retrieve pipeline for one request."""
        # Log the request by LENGTH only -- never the raw text (avoids storing
        # unnecessary personal information).
        log_event(logger, "request_received", request_length=len(request or ""))

        # 1. Guard the raw text. If it's blocked, stop BEFORE parsing/retrieval.
        input_check = self._guardrails.check_input(request)
        log_event(
            logger, "guardrail_input",
            allowed=input_check.allowed,
            error_count=len(input_check.errors),
            warning_count=len(input_check.warnings),
        )
        if not input_check.allowed:
            log_event(logger, "recommendation_blocked", stage="input_guardrail")
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
        try:
            parsed = self._parser.parse(request)
        except PreferenceParseError as exc:
            log_event(logger, "parsing_failed", level=logging.ERROR,
                      reason=safe_error_message(exc))
            raise
        log_event(logger, "parsing_succeeded", parser_confidence=parsed.confidence)

        # 3. Guard the parsed preferences (ranges, conflicts, coverage).
        pref_check = self._guardrails.check_preferences(parsed)
        log_event(
            logger, "guardrail_preferences",
            allowed=pref_check.allowed,
            error_count=len(pref_check.errors),
            warning_count=len(pref_check.warnings),
        )
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
        log_event(logger, "songs_loaded", song_count=len(songs))

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
        log_event(
            logger, "songs_retrieved",
            candidate_count=len(recommendations),
            strategy=self._strategy,
        )

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

    def recommend_and_explain(self, request: str) -> RecommendationContext:
        """
        Full agentic pipeline: retrieve -> generate -> verify -> (repair once) ->
        verify -> (deterministic fallback).

            generate explanation
                -> verify
                -> if valid: use it ("generated")
                -> else: ONE AI repair, then verify
                    -> if valid: use it ("repaired")
                    -> else: deterministic fallback ("fallback", no AI call)

        A generated/repaired answer is NEVER used unless it passed verification.
        There is exactly one repair attempt -- no retry loop.
        """
        try:
            context = self.recommend(request)
            if not context.allowed:
                log_event(logger, "recommendation_completed",
                          allowed=False, fallback_used=False, repair_attempted=False)
                return context

            repair_attempted = False

            # Generate, then verify.
            explanation = self._explainer.generate(context)
            log_event(logger, "explanation_generated",
                      candidate_count=len(context.recommendations))
            verdict = self._verifier.verify(
                explanation, context.recommendations, context.confidence
            )
            log_event(logger, "verification_result",
                      passed=verdict.passed, error_count=len(verdict.errors), attempt=1)

            if verdict.passed:
                context.explanation = explanation
                context.explanation_method = "generated"
            else:
                # One -- and only one -- repair attempt.
                repair_attempted = True
                log_event(logger, "repair_attempted", issue_count=len(verdict.errors))
                repaired = self._explainer.generate(
                    context, feedback=_repair_feedback(verdict)
                )
                repaired_verdict = self._verifier.verify(
                    repaired, context.recommendations, context.confidence
                )
                log_event(logger, "verification_result",
                          passed=repaired_verdict.passed,
                          error_count=len(repaired_verdict.errors), attempt=2)

                if repaired_verdict.passed:
                    context.explanation = repaired
                    context.explanation_method = "repaired"
                else:
                    # Still invalid -> deterministic fallback, no AI involved.
                    log_event(logger, "fallback_used", level=logging.WARNING,
                              reason="repair_failed_verification")
                    context.explanation = self._deterministic_fallback(context)
                    context.explanation_method = "fallback"

            log_event(
                logger, "recommendation_completed",
                parser_confidence=context.confidence,
                candidate_count=len(context.recommendations),
                strategy=self._strategy,
                verification_passed=(context.explanation_method != "fallback"),
                repair_attempted=repair_attempted,
                fallback_used=(context.explanation_method == "fallback"),
            )
            return context
        except Exception as exc:
            # Never leak secrets through an exception; log a clean message.
            log_event(logger, "unexpected_error", level=logging.ERROR,
                      error=safe_error_message(exc))
            raise

    @staticmethod
    def _deterministic_fallback(context: "RecommendationContext") -> dict:
        """
        Build an explanation purely from the recommender's scores and reasons --
        no AI call. This is the guaranteed-valid answer of last resort.
        """
        song_explanations = [
            {
                "title": rec.get("title"),
                "artist": rec.get("artist"),
                "explanation": (
                    f"Selected by the scoring system because: "
                    f"{rec.get('reasons') or 'no strong matching features'}."
                ),
            }
            for rec in context.recommendations
        ]
        warnings = list(context.warnings) + [
            "The AI explanation could not be verified, so these deterministic "
            "scoring reasons are shown instead."
        ]
        summary = (
            f"Showing the top {len(context.recommendations)} songs the scoring "
            f"system matched to your request, with the reason each was chosen."
        )
        return {
            "summary": summary,
            "song_explanations": song_explanations,
            "confidence": context.confidence,
            "warnings": warnings,
        }


def _preferences_to_dict(prefs: ParsedPreferences) -> dict:
    """Build the recommender's prefs dict, dropping any field left as None."""
    return {
        name: getattr(prefs, name)
        for name in SCORING_FIELDS
        if getattr(prefs, name) is not None
    }


def _repair_feedback(verdict: VerificationResult) -> str:
    """Turn verification failures into concrete correction guidance for the AI."""
    parts = ["Your previous answer failed grounding checks."]
    if verdict.unsupported_titles:
        parts.append(
            "Do not mention songs outside the provided list; remove: "
            + ", ".join(str(t) for t in verdict.unsupported_titles)
            + "."
        )
    if verdict.unsupported_claims:
        parts.append("Fix these unsupported claims: " + " ".join(verdict.unsupported_claims))
    for error in verdict.errors:
        parts.append(error)
    parts.append(
        "Use ONLY the supplied songs, artists, and attributes, and give every "
        "song a reason."
    )
    return " ".join(parts)
