"""
Integration tests for the interactive main-application mode.

`run_interactive` accepts injectable `ai_client`, `input_fn`, and `output_fn`, so
these tests drive a full conversation with a FakeAIClient and scripted input --
no network, no real keyboard, no API key.
"""

import json

from src.ai_client import FakeAIClient
from src.main import run_interactive


def scripted_input(lines):
    """An input_fn that returns each queued line in turn."""
    it = iter(lines)
    return lambda prompt="": next(it)


def collector():
    """An output_fn that records everything printed."""
    out = []
    return out, out.append


PARSE_REPLY = json.dumps(
    {"genre": "pop", "mood": "happy", "energy": 0.9, "confidence": 0.85, "uncertain_fields": []}
)
EXPLAIN_REPLY = json.dumps(
    {"summary": "Upbeat pop that matches your request.",
     "song_explanations": [{"title": "Sunrise City", "explanation": "Exact pop, happy match."}]}
)


def test_interactive_happy_path_displays_full_result():
    fake = FakeAIClient(responses=[PARSE_REPLY, EXPLAIN_REPLY])
    lines, out = collector()

    run_interactive(
        ai_client=fake,
        input_fn=scripted_input(["high energy happy pop", "balanced", "quit"]),
        output_fn=out,
    )

    text = "\n".join(lines)
    assert "Interpreted preferences" in text
    assert "Sunrise City" in text          # a real retrieved song
    assert "score" in text                 # scores shown
    assert "reasons:" in text              # deterministic reasons shown
    assert "Confidence: 0.85" in text      # confidence shown
    assert "Explanation source" in text    # repair/fallback status shown
    assert "Goodbye!" in text


def test_interactive_quit_immediately():
    fake = FakeAIClient(PARSE_REPLY)
    lines, out = collector()

    run_interactive(ai_client=fake, input_fn=scripted_input(["quit"]), output_fn=out)

    assert any("Goodbye!" in line for line in lines)
    assert fake.calls == []  # never reached the AI


def test_interactive_missing_api_key_shows_setup_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lines, out = collector()

    # ai_client=None forces construction of the real client, which fails cleanly.
    run_interactive(ai_client=None, input_fn=scripted_input(["quit"]), output_fn=out)

    text = "\n".join(lines)
    assert "ANTHROPIC_API_KEY" in text
    assert ".env" in text


def test_interactive_blocked_request_shows_friendly_message():
    fake = FakeAIClient(PARSE_REPLY)
    lines, out = collector()

    run_interactive(
        ai_client=fake,
        input_fn=scripted_input(["delete project files", "balanced", "quit"]),
        output_fn=out,
    )

    text = "\n".join(lines)
    assert "couldn't process that request" in text.lower()
    assert fake.calls == []  # guardrail blocked before any AI call


def test_interactive_unknown_strategy_falls_back_to_balanced():
    fake = FakeAIClient(responses=[PARSE_REPLY, EXPLAIN_REPLY])
    lines, out = collector()

    run_interactive(
        ai_client=fake,
        input_fn=scripted_input(["happy pop", "not_a_strategy", "quit"]),
        output_fn=out,
    )

    text = "\n".join(lines)
    assert "using 'balanced'" in text
    assert "Sunrise City" in text
