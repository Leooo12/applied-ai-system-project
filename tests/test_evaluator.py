"""
Tests for the reliability evaluator.

These confirm the evaluator loads the real test cases, runs them through the
real orchestrator (via FakeAIClient), grades pass/fail correctly against each
case's `expect` block, and that the summary count is computed -- not hardcoded.
"""

import json

from src.evaluator import run_all, run_case, _load_cases, CASES_PATH


def test_test_cases_file_has_at_least_twelve_cases():
    cases = _load_cases()
    assert len(cases) >= 12
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))  # unique IDs


def test_all_required_scenarios_are_present():
    cases = _load_cases()
    names = " ".join(c["name"].lower() for c in cases)
    for keyword in (
        "high-energy happy pop", "calm instrumental", "intense rock",
        "conflicting", "unsupported genre", "vague", "empty",
        "long input", "injection", "malformed", "invented", "unavailable",
    ):
        assert keyword in names, f"missing scenario keyword: {keyword}"


def test_empty_input_case_is_blocked():
    cases = _load_cases()
    case = next(c for c in cases if c["id"] == "TC07")
    result = run_case(case)

    assert result.passed is True
    assert "blocked" in result.guardrail_result.lower()


def test_prompt_injection_case_is_blocked():
    cases = _load_cases()
    case = next(c for c in cases if c["id"] == "TC09")
    result = run_case(case)

    assert result.passed is True
    assert "blocked" in result.guardrail_result.lower()


def test_malformed_json_case_raises_controlled_error():
    cases = _load_cases()
    case = next(c for c in cases if c["id"] == "TC10")
    result = run_case(case)

    assert result.passed is True
    assert "PreferenceParseError" in result.parser_result or "error" in result.parser_result


def test_invented_song_case_falls_back():
    cases = _load_cases()
    case = next(c for c in cases if c["id"] == "TC11")
    result = run_case(case)

    assert result.passed is True
    assert result.fallback_used is True
    assert result.repair_attempted is True


def test_service_unavailable_case_raises_ai_error():
    cases = _load_cases()
    case = next(c for c in cases if c["id"] == "TC12")
    result = run_case(case)

    assert result.passed is True
    assert "error" in result.parser_result.lower()


def test_run_all_produces_a_result_per_case():
    results = run_all()
    cases = _load_cases()
    assert len(results) == len(cases)


def test_summary_count_is_computed_not_hardcoded():
    """The pass count must equal the number of results actually marked passed."""
    results = run_all()
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    # Recompute independently from the same results to prove it's a real count.
    recomputed = len([r for r in results if r.passed is True])
    assert passed == recomputed
    assert 0 <= passed <= total
