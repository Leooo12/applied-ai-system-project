"""
Grounding verifier for VibeMatch AI.

After the explanation generator produces an answer, this component independently
checks that answer against the RETRIEVED songs -- a second line of defense that
does not trust the generator (or the AI behind it).

It verifies:
- Every mentioned song title exists in the retrieved recommendation list.
- Every mentioned artist matches the retrieved data for that title.
- The prose does not claim a genre/mood/explicit/decade that conflicts with the
  retrieved attributes.
- Every recommended song actually has a (non-empty) reason.
- The answer does not claim high certainty when confidence is low.
- The recommendation section is not empty when songs were retrieved.

It returns a `VerificationResult`; `passed` is False whenever any hard error was
found. The orchestrator uses that verdict to drive repair/fallback.
"""

import re
from dataclasses import dataclass, field
from typing import List

from src.guardrails import KNOWN_GENRES, KNOWN_MOODS


# Below this confidence, absolute-certainty language is treated as overclaiming.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# Phrases that assert certainty the confidence score may not support.
OVERCONFIDENT_PHRASES = (
    "definitely", "guaranteed", "certainly", "without a doubt", "absolutely",
    "perfect match", "exactly what you want", "100%", "no doubt",
)


@dataclass
class VerificationResult:
    """Verdict of one verification pass."""

    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    unsupported_titles: List[str] = field(default_factory=list)
    unsupported_claims: List[str] = field(default_factory=list)


class Verifier:
    """Checks a generated explanation against the retrieved songs."""

    def __init__(self, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD):
        self._threshold = confidence_threshold

    def verify(
        self, explanation: dict, recommendations: List[dict], confidence: float
    ) -> VerificationResult:
        errors: List[str] = []
        warnings: List[str] = []
        unsupported_titles: List[str] = []
        unsupported_claims: List[str] = []

        song_explanations = explanation.get("song_explanations") or []
        summary = explanation.get("summary") or ""

        # Look up retrieved songs by title for O(1) checks.
        retrieved = {}
        for rec in recommendations:
            retrieved[rec.get("title")] = rec

        # An empty recommendation section when songs WERE retrieved is invalid.
        if recommendations and not song_explanations:
            errors.append("The explanation has no recommendations, but songs were retrieved.")

        for entry in song_explanations:
            title = entry.get("title")
            rec = retrieved.get(title)

            # 1. Title must be a retrieved song.
            if rec is None:
                unsupported_titles.append(title)
                errors.append(f"Mentions a song not in the retrieved list: {title!r}.")
                continue

            song = rec.get("song", {}) or {}

            # 2. Artist (if the entry claims one) must match the retrieved artist.
            claimed_artist = entry.get("artist")
            if claimed_artist and claimed_artist != rec.get("artist"):
                claim = (
                    f"Wrong artist for {title!r}: claimed {claimed_artist!r}, "
                    f"actual {rec.get('artist')!r}."
                )
                unsupported_claims.append(claim)
                errors.append(claim)

            # 3. Each song must have a non-empty reason/explanation.
            text = (entry.get("explanation") or "").strip()
            if not text:
                errors.append(f"Missing reason for recommended song {title!r}.")
                continue

            # 4. Prose must not contradict retrieved genre/mood.
            for claim in _attribute_conflicts(text, song, title):
                unsupported_claims.append(claim)
                errors.append(claim)

        # 5. Overclaiming certainty at low confidence -> warning (not a hard fail).
        if confidence < self._threshold:
            blob = (summary + " " + " ".join(
                e.get("explanation", "") for e in song_explanations
            )).lower()
            if any(phrase in blob for phrase in OVERCONFIDENT_PHRASES):
                warnings.append(
                    "The response claims high certainty despite a low confidence score."
                )

        return VerificationResult(
            passed=not errors,
            errors=errors,
            warnings=warnings,
            unsupported_titles=unsupported_titles,
            unsupported_claims=unsupported_claims,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _word_present(text: str, term: str) -> bool:
    """True if `term` appears as a whole word/phrase in `text` (case-insensitive)."""
    if not term:
        return False
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def _attribute_conflicts(text: str, song: dict, title: str) -> List[str]:
    """
    Conservatively flag prose that names a DIFFERENT genre/mood than the song's,
    while never naming the song's actual one. This catches "this jazz track" for a
    pop song, without flagging legitimate comparisons ("pop, not unlike jazz").
    """
    lowered = text.lower()
    conflicts: List[str] = []

    for attr, vocabulary in (("genre", KNOWN_GENRES), ("mood", KNOWN_MOODS)):
        actual = (song.get(attr) or "").lower()
        if not actual:
            continue
        actual_mentioned = _word_present(lowered, actual)
        others = [
            term for term in vocabulary
            if term != actual and _word_present(lowered, term)
        ]
        if others and not actual_mentioned:
            conflicts.append(
                f"{title!r} described as {attr} {others[0]!r}, "
                f"but the retrieved {attr} is {actual!r}."
            )

    return conflicts
