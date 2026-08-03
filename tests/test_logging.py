"""
Tests for structured logging.

These verify the JSON event format, the secret-redaction guarantees, and that a
full orchestration run emits the key lifecycle events -- all offline via
FakeAIClient.
"""

import json
import logging

from src.app_logging import (
    log_event,
    get_logger,
    safe_error_message,
    REDACTED,
)


def parsed_events(caplog):
    """Parse every captured log line as JSON and return the event dicts."""
    events = []
    for record in caplog.records:
        try:
            events.append(json.loads(record.getMessage()))
        except (json.JSONDecodeError, ValueError):
            pass
    return events


# ---------------------------------------------------------------------------
# Event format
# ---------------------------------------------------------------------------
def test_log_event_emits_json_with_event_and_fields(caplog):
    logger = get_logger("vibematch.test")
    with caplog.at_level(logging.INFO, logger="vibematch.test"):
        payload = log_event(logger, "recommendation_completed",
                            parser_confidence=0.82, candidate_count=5)

    assert payload["event"] == "recommendation_completed"
    events = parsed_events(caplog)
    assert {"event": "recommendation_completed", "parser_confidence": 0.82,
            "candidate_count": 5} == events[-1]


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------
def test_sensitive_field_names_are_redacted():
    logger = get_logger("vibematch.test")
    payload = log_event(logger, "debug", api_key="sk-supersecret", password="hunter2")
    assert payload["api_key"] == REDACTED
    assert payload["password"] == REDACTED


def test_key_shaped_tokens_are_scrubbed_from_values():
    logger = get_logger("vibematch.test")
    payload = log_event(logger, "error", message="failed using key sk-ABC123XYZ now")
    assert "sk-ABC123XYZ" not in payload["message"]
    assert REDACTED in payload["message"]


def test_safe_error_message_scrubs_secrets():
    msg = safe_error_message(ValueError("bad token sk-DEADBEEF99 supplied"))
    assert "sk-DEADBEEF99" not in msg
    assert "ValueError" in msg


# ---------------------------------------------------------------------------
# End-to-end: a successful run emits the lifecycle events
# ---------------------------------------------------------------------------
def test_successful_run_logs_completion_event(caplog):
    import json as _json
    from src.ai_client import FakeAIClient
    from src.orchestrator import VibeMatchOrchestrator

    parse_reply = _json.dumps(
        {"genre": "pop", "mood": "happy", "energy": 0.9, "confidence": 0.85, "uncertain_fields": []}
    )
    explain_reply = _json.dumps(
        {"summary": "Upbeat pop.",
         "song_explanations": [{"title": "Sunrise City", "explanation": "Exact pop, happy match."}]}
    )
    orch = VibeMatchOrchestrator(FakeAIClient(responses=[parse_reply, explain_reply]))

    with caplog.at_level(logging.INFO, logger="vibematch.orchestrator"):
        orch.recommend_and_explain("high energy happy pop")

    names = [e["event"] for e in parsed_events(caplog)]
    for expected in (
        "request_received", "guardrail_input", "parsing_succeeded",
        "songs_loaded", "songs_retrieved", "explanation_generated",
        "verification_result", "recommendation_completed",
    ):
        assert expected in names

    completed = [e for e in parsed_events(caplog) if e["event"] == "recommendation_completed"][-1]
    assert completed["verification_passed"] is True
    assert completed["fallback_used"] is False
    assert completed["repair_attempted"] is False


# ---------------------------------------------------------------------------
# End-to-end: a fallback run logs the fallback
# ---------------------------------------------------------------------------
def test_fallback_run_logs_fallback_used(caplog):
    import json as _json
    from src.ai_client import FakeAIClient
    from src.orchestrator import VibeMatchOrchestrator
    from src.verifier import Verifier

    parse_reply = _json.dumps(
        {"genre": "pop", "mood": "happy", "energy": 0.9, "confidence": 0.85, "uncertain_fields": []}
    )

    class _BadExplainer:
        def generate(self, context, feedback=None):
            return {"summary": "s",
                    "song_explanations": [{"title": "Invented Song", "artist": "Ghost",
                                           "explanation": "made up"}]}

    orch = VibeMatchOrchestrator(
        FakeAIClient(parse_reply),
        explanation_generator=_BadExplainer(),
        verifier=Verifier(),
    )

    with caplog.at_level(logging.INFO, logger="vibematch.orchestrator"):
        ctx = orch.recommend_and_explain("high energy happy pop")

    assert ctx.explanation_method == "fallback"
    names = [e["event"] for e in parsed_events(caplog)]
    assert "repair_attempted" in names
    assert "fallback_used" in names

    completed = [e for e in parsed_events(caplog) if e["event"] == "recommendation_completed"][-1]
    assert completed["fallback_used"] is True
    assert completed["repair_attempted"] is True
    assert completed["verification_passed"] is False
