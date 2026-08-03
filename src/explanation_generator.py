"""
Grounded AI explanation generator for VibeMatch AI.

This is the "G" (generation) in RAG, and it is deliberately kept on a short
leash. It receives ONLY the evidence retrieved by the orchestrator -- the user's
request, the parsed preferences, and the exact top songs with their attributes,
deterministic scores, and scoring reasons -- and asks the AI to write a short,
honest explanation of *those* songs.

Guarantees enforced here (not just requested in the prompt):

* The AI writes prose only. It cannot add, remove, or reorder songs.
* `song_explanations` is built by iterating the RETRIEVED songs, so a song the
  AI didn't retrieve can never appear in the output, and every retrieved song
  gets an explanation (an AI one, or a deterministic fallback).
* `confidence` and `warnings` come from the retrieval context, not the AI, so
  the model cannot overstate certainty.
* If the AI is unavailable or returns junk, we fall back to the deterministic
  scoring reasons instead of crashing.
"""

import json
from typing import Optional

from src.ai_client import AIClient, AIClientError


# Song attributes we expose to the AI as evidence (the real catalog columns).
_ATTRIBUTE_KEYS = (
    "genre", "mood", "energy", "tempo_bpm", "valence", "danceability",
    "acousticness", "instrumentalness", "popularity", "release_decade",
    "mood_tag", "explicit", "artist_type",
)

# Shown when retrieval found nothing to explain.
NO_MATCH_SUMMARY = (
    "The catalog didn't contain any songs that matched your request closely "
    "enough to recommend. Try adjusting or adding a preference."
)


SYSTEM_PROMPT = """\
You explain music recommendations that were ALREADY chosen by a separate scoring
system. You do not choose or rank songs.

You will receive JSON with the user's request, their parsed preferences, and a
list of songs -- each with its attributes, a numeric score, and the concrete
reasons it scored that way.

Follow these rules exactly:
- Use ONLY the songs supplied in the JSON. Never mention or recommend a song
  that is not in the list.
- Never invent an artist, a song, or a song attribute. Only use the values given.
- For each supplied song, explain briefly why it fits the request, citing the
  given attributes and reasons.
- Mention meaningful mismatches or trade-offs (for example, the right genre but a
  different mood, or a related-but-not-exact match).
- If none of the songs is an exact match for what was asked, say so honestly.
- Do NOT claim you listened to the music. You are reasoning from data only.
- Do NOT claim more certainty than the supplied confidence score justifies.
- Keep the whole response concise.

Return ONLY a JSON object (no markdown, no code fences) with exactly:
  {
    "summary": "<2-3 sentence overview>",
    "song_explanations": [
      {"title": "<exact title from the list>", "explanation": "<one or two sentences>"}
    ]
  }
"""


class ExplanationGenerator:
    """Turns a retrieval context into a grounded, structured explanation."""

    def __init__(self, ai_client: AIClient):
        self._ai = ai_client

    def generate(self, context, feedback=None) -> dict:
        """
        Build the structured explanation for a `RecommendationContext`-like object.

        Accepts anything exposing `original_request`, `parsed_preferences`,
        `recommendations`, `confidence`, and `warnings` (duck-typed on purpose, so
        this module never imports the orchestrator).

        `feedback` (optional) is correction guidance from the verifier, included in
        the evidence so a repair attempt can fix the flagged problems.
        """
        warnings = list(getattr(context, "warnings", []) or [])
        confidence = getattr(context, "confidence", 0.0)
        recommendations = list(getattr(context, "recommendations", []) or [])

        # Nothing retrieved -> be honest, and don't waste an AI call.
        if not recommendations:
            return {
                "summary": NO_MATCH_SUMMARY,
                "song_explanations": [],
                "confidence": confidence,
                "warnings": warnings,
            }

        evidence = self._build_evidence(context, recommendations)
        if feedback:
            evidence["correction_feedback"] = feedback

        ai_summary: Optional[str] = None
        ai_explanations: dict = {}
        try:
            raw = self._ai.generate(SYSTEM_PROMPT, json.dumps(evidence, indent=2))
            data = self._parse_response(raw)
            ai_summary = data.get("summary")
            for item in data.get("song_explanations", []) or []:
                if isinstance(item, dict) and item.get("title"):
                    ai_explanations[item["title"]] = item.get("explanation")
        except (AIClientError, _ExplanationParseError):
            # Graceful degradation: keep serving the user with deterministic text.
            warnings.append(
                "AI explanation was unavailable; showing the scoring reasons instead."
            )

        # Build explanations by iterating the RETRIEVED songs only. This is the
        # structural guarantee that no off-list song can appear.
        song_explanations = []
        for rec in recommendations:
            title = rec.get("title")
            song_explanations.append(
                {
                    "title": title,
                    "artist": rec.get("artist"),
                    "explanation": ai_explanations.get(title) or _fallback_explanation(rec),
                }
            )

        summary = ai_summary or _fallback_summary(recommendations)

        return {
            "summary": summary,
            "song_explanations": song_explanations,
            "confidence": confidence,
            "warnings": warnings,
        }

    # -- internals ----------------------------------------------------------

    def _build_evidence(self, context, recommendations) -> dict:
        """Assemble the exact JSON evidence packet sent to the AI."""
        songs = []
        for rec in recommendations:
            song = rec.get("song", {}) or {}
            songs.append(
                {
                    "title": rec.get("title"),
                    "artist": rec.get("artist"),
                    "score": round(float(rec.get("score", 0.0)), 2),
                    "reasons": rec.get("reasons"),
                    "attributes": {key: song.get(key) for key in _ATTRIBUTE_KEYS},
                }
            )
        return {
            "original_request": getattr(context, "original_request", ""),
            "parsed_preferences": getattr(context, "parsed_preferences", {}),
            "confidence": getattr(context, "confidence", 0.0),
            "warnings": list(getattr(context, "warnings", []) or []),
            "songs": songs,
        }

    @staticmethod
    def _parse_response(raw: str) -> dict:
        text = _strip_code_fences(raw)
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise _ExplanationParseError(str(exc)) from exc
        if not isinstance(data, dict):
            raise _ExplanationParseError("Expected a JSON object.")
        return data


class _ExplanationParseError(Exception):
    """Internal: the AI reply wasn't usable JSON (handled via fallback)."""


def _fallback_explanation(rec: dict) -> str:
    """Deterministic explanation built from the recommender's own reasons."""
    reasons = rec.get("reasons") or "no strong matching features"
    return f"Selected by the scoring system because: {reasons}."


def _fallback_summary(recommendations) -> str:
    return (
        f"Here are the top {len(recommendations)} songs the scoring system "
        f"matched to your request, with the reasons each was chosen."
    )


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding ```json ... ``` block if the model added one."""
    if not isinstance(text, str):
        return ""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        if "\n" in stripped:
            first_line, rest = stripped.split("\n", 1)
            if first_line.strip().lower() in ("json", ""):
                stripped = rest
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()
