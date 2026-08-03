"""
Natural-language preference parser for VibeMatch AI.

This component is the bridge between how a person *talks* about music ("calm
instrumental music for late-night coding") and the structured numbers the
recommendation engine needs (`energy=0.3`, `instrumentalness=0.9`, ...).

The flow is deliberately simple and layered:

1. The AI model (via `src/ai_client.py`) does the *language understanding* -- it
   reads the free-text request and returns JSON describing the preferences.
2. This module does the *validation* -- it never trusts the AI blindly. Every
   number is coerced and clamped into a safe range, `explicit` is normalized to
   "yes"/"no", missing fields become `None`, invalid JSON becomes a clear error,
   and low-confidence output is flagged for clarification.

No recommendation or scoring happens here -- that stays in `src/recommender.py`.
This module only produces a validated `ParsedPreferences` object.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional

from src.ai_client import AIClient


# ---------------------------------------------------------------------------
# Supported ranges (the "reasonable" bounds we validate the AI's output against)
# ---------------------------------------------------------------------------
UNIT_MIN, UNIT_MAX = 0.0, 1.0        # energy, valence, danceability, etc.
TEMPO_MIN, TEMPO_MAX = 40.0, 220.0   # beats per minute
POPULARITY_MIN, POPULARITY_MAX = 0, 100

# Below this confidence, we ask the caller to get more detail from the user
# instead of trusting the parse.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# The numeric 0-1 "audio feature" fields, handled identically.
_UNIT_FIELDS = (
    "energy",
    "valence",
    "danceability",
    "acousticness",
    "instrumentalness",
)


class PreferenceParseError(Exception):
    """
    Raised when the AI's reply cannot be turned into structured preferences --
    most importantly, when it is not valid JSON. This is the "controlled error"
    callers can catch instead of a raw JSONDecodeError leaking out.
    """


@dataclass
class ParsedPreferences:
    """
    Structured music preferences extracted from a natural-language request.

    Every music field is optional (`None` means "the user didn't specify this").
    Only `confidence` and `uncertain_fields` are always present. `needs_clarification`
    is a derived flag: True when confidence fell below the threshold.
    """

    # --- Always present ---
    confidence: float
    uncertain_fields: List[str] = field(default_factory=list)

    # --- Optional music preferences (None = not specified) ---
    genre: Optional[str] = None
    mood: Optional[str] = None
    energy: Optional[float] = None
    tempo_bpm: Optional[float] = None
    valence: Optional[float] = None
    danceability: Optional[float] = None
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None
    popularity: Optional[int] = None
    release_decade: Optional[int] = None
    mood_tag: Optional[str] = None
    explicit: Optional[str] = None       # normalized to "yes" / "no"
    artist_type: Optional[str] = None
    activity: Optional[str] = None

    # --- Derived flag ---
    needs_clarification: bool = False


# The instructions we send the AI. It must return JSON ONLY -- no prose, no
# markdown -- and must NOT invent a genre the user never mentioned.
SYSTEM_PROMPT = """\
You convert a person's natural-language music request into structured JSON.

Return ONLY a single JSON object -- no explanation, no markdown, no code fences.

The JSON must have exactly these keys:
  genre, mood, energy, tempo_bpm, valence, danceability, acousticness,
  instrumentalness, popularity, release_decade, mood_tag, explicit,
  artist_type, activity, confidence, uncertain_fields

Rules:
- Use null for anything the request does not clearly specify. Do NOT guess a
  genre, artist type, or era the user did not mention. Only fill a field when the
  request gives real evidence for it.
- energy, valence, danceability, acousticness, instrumentalness: numbers from
  0.0 to 1.0.
- tempo_bpm: a realistic beats-per-minute number (roughly 40-220), or null.
- popularity: an integer from 0 to 100, or null.
- release_decade: a four-digit decade like 1990 or 2010, or null.
- explicit: "yes", "no", or null.
- activity: a short label for what the user is doing (e.g. "coding", "workout"),
  or null.
- confidence: a number from 0.0 to 1.0 for how sure you are overall.
- uncertain_fields: a JSON array of the field names you were unsure about
  (empty array if none).
"""


class PreferenceParser:
    """
    Turns a free-text request into a validated `ParsedPreferences`.

    It depends only on the `AIClient` interface, so tests can pass a
    `FakeAIClient` and run completely offline.
    """

    def __init__(
        self,
        ai_client: AIClient,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ):
        self._ai = ai_client
        self._threshold = confidence_threshold

    def parse(self, request: str) -> ParsedPreferences:
        """Parse `request` into structured, validated preferences."""
        # Empty input: there is nothing to understand, so don't even call the AI.
        # Return a low-confidence result that asks for clarification.
        if not request or not request.strip():
            return ParsedPreferences(
                confidence=0.0,
                uncertain_fields=["all"],
                needs_clarification=True,
            )

        raw = self._ai.generate(SYSTEM_PROMPT, request)
        data = self._load_json(raw)
        return self._build(data)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _load_json(raw: str) -> dict:
        """
        Turn the AI's text reply into a dict, tolerating markdown code fences.
        Anything that isn't a JSON object becomes a controlled PreferenceParseError.
        """
        text = _strip_code_fences(raw)
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise PreferenceParseError(
                f"AI did not return valid JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise PreferenceParseError(
                f"Expected a JSON object, got {type(data).__name__}."
            )
        return data

    def _build(self, data: dict) -> ParsedPreferences:
        """Validate and normalize every field from the parsed JSON dict."""
        confidence = _to_float(data.get("confidence"))
        confidence = _clamp(confidence, 0.0, 1.0) if confidence is not None else 0.0

        uncertain = data.get("uncertain_fields")
        uncertain_fields = (
            [str(f) for f in uncertain] if isinstance(uncertain, list) else []
        )

        prefs = ParsedPreferences(
            confidence=confidence,
            uncertain_fields=uncertain_fields,
            genre=_norm_str(data.get("genre")),
            mood=_norm_str(data.get("mood")),
            tempo_bpm=_clamp_or_none(data.get("tempo_bpm"), TEMPO_MIN, TEMPO_MAX),
            popularity=_clamp_int_or_none(
                data.get("popularity"), POPULARITY_MIN, POPULARITY_MAX
            ),
            release_decade=_to_int_or_none(data.get("release_decade")),
            mood_tag=_norm_str(data.get("mood_tag")),
            explicit=_norm_explicit(data.get("explicit")),
            artist_type=_norm_str(data.get("artist_type")),
            activity=_norm_str(data.get("activity")),
        )

        # The 0-1 audio features all validate the same way.
        for name in _UNIT_FIELDS:
            setattr(
                prefs,
                name,
                _clamp_or_none(data.get(name), UNIT_MIN, UNIT_MAX),
            )

        prefs.needs_clarification = confidence < self._threshold
        return prefs


# ---------------------------------------------------------------------------
# Small validation/normalization helpers -- kept as free functions so they are
# easy to read and test in isolation.
# ---------------------------------------------------------------------------
def _strip_code_fences(text: str) -> str:
    """Remove a surrounding ```json ... ``` block if the model added one."""
    if not isinstance(text, str):
        return ""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        # Drop an optional language tag like "json" on the first line.
        if "\n" in stripped:
            first_line, rest = stripped.split("\n", 1)
            if first_line.strip().lower() in ("json", ""):
                stripped = rest
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def _to_float(value) -> Optional[float]:
    """Best-effort float conversion; None if the value isn't numeric."""
    if isinstance(value, bool):  # guard: bools are ints in Python
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    """Keep `value` inside [low, high]."""
    return max(low, min(high, value))


def _clamp_or_none(value, low: float, high: float) -> Optional[float]:
    """Coerce to float and clamp, or None if not numeric."""
    number = _to_float(value)
    if number is None:
        return None
    return _clamp(number, low, high)


def _clamp_int_or_none(value, low: int, high: int) -> Optional[int]:
    """Coerce to int and clamp, or None if not numeric (used for popularity)."""
    number = _to_float(value)
    if number is None:
        return None
    return int(_clamp(round(number), low, high))


def _to_int_or_none(value) -> Optional[int]:
    """Coerce to int, or None (used for release_decade)."""
    number = _to_float(value)
    return int(number) if number is not None else None


def _norm_str(value) -> Optional[str]:
    """Trim and lowercase a string field; empty/blank becomes None."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def _norm_explicit(value) -> Optional[str]:
    """Normalize many truthy/falsy spellings to exactly 'yes' or 'no'."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    token = str(value).strip().lower()
    if token in ("yes", "y", "true", "1", "explicit"):
        return "yes"
    if token in ("no", "n", "false", "0", "clean"):
        return "no"
    return None
