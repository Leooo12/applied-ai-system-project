"""
Input guardrails and validation for VibeMatch AI.

Guardrails sit on the *edges* of the system and decide whether a request is safe
and sensible to process. There are two checkpoints:

1. `check_input(text)` runs on the RAW user text, before the AI ever sees it.
   It blocks empty/whitespace/oversized input, off-topic requests, and
   prompt-injection attempts ("ignore all previous instructions", "reveal your
   API key", "delete project files").

2. `check_preferences(prefs)` runs on the PARSED `ParsedPreferences`, after the
   parser has produced structured data. It re-checks numeric ranges, flags
   requests with no usable preference, and *warns* about conflicts (e.g. high
   energy paired with a calm mood) without ever changing them.

Both return a `GuardrailResult`. The rule of thumb:
  * `errors`   -> stop processing (`allowed=False`).
  * `warnings` -> keep going, but tell the user something looked off.

Guardrails never mutate preferences and never touch the recommendation algorithm.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from src.preference_parser import ParsedPreferences


# ---------------------------------------------------------------------------
# Tunable limits and vocabulary
# ---------------------------------------------------------------------------
MAX_INPUT_LENGTH = 1000  # characters; anything longer is rejected

# Genres/moods the catalog actually contains. Used to *warn* (not block) when a
# request asks for something unsupported.
KNOWN_GENRES = {
    "pop", "indie pop", "lofi", "ambient", "rock", "metal", "hip-hop",
    "r&b", "funk", "jazz", "folk", "classical", "electronic", "synthwave",
}
KNOWN_MOODS = {
    "happy", "relaxed", "chill", "moody", "intense", "confident", "focused",
    "romantic", "melancholy", "energetic", "sad",
}

# Moods that imply calm vs. high-energy, used to detect conflicts with `energy`.
CALM_MOODS = {
    "calm", "relaxed", "chill", "mellow", "sleepy", "focused",
    "peaceful", "soothing", "melancholy", "sad",
}
ENERGETIC_MOODS = {"energetic", "intense", "aggressive", "upbeat", "hype"}

# Phrases that signal an attempt to hijack the assistant or extract secrets.
# Matched as lowercase substrings -- a real music request won't contain these.
INJECTION_PATTERNS = (
    "ignore all previous", "ignore previous instruction", "ignore the above",
    "disregard previous", "disregard all previous", "forget previous instruction",
    "reveal your", "reveal the api", "api key", "system prompt",
    "environment variable", "print your instructions", "show your instructions",
    "delete project files", "delete all files", "rm -rf", "drop table",
    "secret key", "access token", "your password",
)

# Words that indicate the request is actually about music/listening. If none of
# these appear, we treat the request as off-topic.
MUSIC_KEYWORDS = (
    "music", "song", "songs", "track", "tracks", "tune", "tunes", "playlist",
    "listen", "artist", "band", "album", "genre", "mood", "vibe", "vibes",
    "beat", "beats", "melody", "rhythm", "play", "recommend", "recommendation",
    "suggestion", "instrumental", "acoustic", "lyrics", "tempo", "bpm",
    # activities people pick music for
    "coding", "study", "studying", "work", "workout", "gym", "run", "running",
    "sleep", "relax", "party", "focus", "drive", "driving", "chill", "dance",
    "dancing", "energy", "upbeat", "calm", "danceable",
)
# Genre and mood words also count as music-related.
MUSIC_KEYWORDS = MUSIC_KEYWORDS + tuple(KNOWN_GENRES) + tuple(KNOWN_MOODS)

# The 0-1 audio-feature fields, validated identically.
_UNIT_FIELDS = (
    "energy", "valence", "danceability", "acousticness", "instrumentalness",
)


@dataclass
class GuardrailResult:
    """
    The verdict from a guardrail check.

    `allowed` is False whenever there are any `errors`. `warnings` describe issues
    that don't stop processing. `needs_clarification` asks the caller to gather
    more detail from the user before trusting the result.
    """

    allowed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    needs_clarification: bool = False


def _result(errors, warnings, needs_clarification=False) -> GuardrailResult:
    """Build a result, deriving `allowed` from whether any errors were found."""
    return GuardrailResult(
        allowed=not errors,
        errors=errors,
        warnings=warnings,
        needs_clarification=needs_clarification,
    )


class Guardrails:
    """
    Runs the input and preference checks. Limits are configurable so tests (and
    future callers) can tighten or relax them without editing constants.
    """

    def __init__(self, max_input_length: int = MAX_INPUT_LENGTH):
        self._max_input_length = max_input_length

    # -- raw text, before parsing ------------------------------------------
    def check_input(self, text: Optional[str]) -> GuardrailResult:
        """Validate the raw request string before it reaches the AI."""
        # Empty or whitespace-only: nothing to work with.
        if text is None or not text.strip():
            return _result(
                errors=["Please describe the kind of music you'd like to hear."],
                warnings=[],
                needs_clarification=True,
            )

        errors: List[str] = []
        warnings: List[str] = []
        lowered = text.lower()

        if len(text) > self._max_input_length:
            errors.append(
                f"Your request is too long (limit {self._max_input_length} "
                f"characters). Please shorten it."
            )

        # Prompt injection / secret extraction takes precedence over the
        # off-topic check (an injection string is also off-topic).
        if any(pattern in lowered for pattern in INJECTION_PATTERNS):
            errors.append(
                "This request looks like an attempt to change my instructions or "
                "access private data, which I can't do. I only recommend music."
            )
        elif not _looks_music_related(lowered):
            errors.append(
                "I can only help with music recommendations. Try describing a "
                "mood, genre, activity, or the kind of sound you want."
            )

        return _result(errors, warnings)

    # -- structured preferences, after parsing -----------------------------
    def check_preferences(self, prefs: ParsedPreferences) -> GuardrailResult:
        """Validate parsed preferences: ranges, coverage, and conflicts."""
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Numeric ranges (defense in depth -- the parser already clamps, but
        #    preferences could arrive from elsewhere).
        for name in _UNIT_FIELDS:
            value = getattr(prefs, name)
            if value is not None and not (0.0 <= value <= 1.0):
                errors.append(f"'{name}' value {value} is outside the 0.0-1.0 range.")
        if prefs.tempo_bpm is not None and not (40.0 <= prefs.tempo_bpm <= 220.0):
            errors.append(f"tempo_bpm {prefs.tempo_bpm} is outside the 40-220 range.")
        if prefs.popularity is not None and not (0 <= prefs.popularity <= 100):
            errors.append(f"popularity {prefs.popularity} is outside the 0-100 range.")

        # 2. Coverage: is there anything to match on at all?
        no_preferences = _no_usable_preferences(prefs)
        needs_clarification = prefs.needs_clarification or no_preferences
        if no_preferences:
            warnings.append(
                "Your request didn't include enough detail to match songs well. "
                "Try adding a mood, genre, or activity."
            )

        # 3. Unsupported (but still processable) genre/mood -> warn.
        if prefs.genre and prefs.genre not in KNOWN_GENRES:
            warnings.append(
                f"'{prefs.genre}' isn't a genre in the catalog, so results may be weaker."
            )
        if prefs.mood and prefs.mood not in KNOWN_MOODS:
            warnings.append(
                f"'{prefs.mood}' isn't a mood in the catalog, so results may be weaker."
            )

        # 4. Conflicts -> warn only. We NEVER silently change the preferences.
        if prefs.energy is not None and prefs.mood in CALM_MOODS and prefs.energy >= 0.7:
            warnings.append(
                "The request contains conflicting mood and energy preferences "
                "(high energy paired with a calm mood)."
            )
        if prefs.energy is not None and prefs.mood in ENERGETIC_MOODS and prefs.energy <= 0.3:
            warnings.append(
                "The request contains conflicting mood and energy preferences "
                "(low energy paired with an energetic mood)."
            )

        return _result(errors, warnings, needs_clarification)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _looks_music_related(lowered_text: str) -> bool:
    """True if the text mentions anything about music, sound, or listening."""
    return any(keyword in lowered_text for keyword in MUSIC_KEYWORDS)


def _no_usable_preferences(prefs: ParsedPreferences) -> bool:
    """True when every actual music preference field is None."""
    fields = (
        "genre", "mood", "energy", "tempo_bpm", "valence", "danceability",
        "acousticness", "instrumentalness", "popularity", "release_decade",
        "mood_tag", "explicit", "artist_type", "activity",
    )
    return all(getattr(prefs, name) is None for name in fields)
