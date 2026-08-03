"""
Reliability evaluation harness for VibeMatch AI.

Runs a fixed set of deterministic test cases (evaluation/test_cases.json)
through the SAME orchestrator used by `src/main.py` -- no shortcuts, no
duplicated pipeline logic. Every case is driven by a `FakeAIClient`, so the
whole evaluation runs offline, at zero API cost, and produces the same result
every time it's run.

For each case it records: the guardrail result, the parser result, the
retrieval result, the verification result, whether a repair was attempted,
whether the deterministic fallback was used, and pass/fail -- derived by
comparing the actual outcome against the case's `expect` block, never
hardcoded.

Run with:  python -m src.evaluator
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from src.ai_client import AIClientError, FakeAIClient, TemporaryAIServiceError
from src.orchestrator import VibeMatchOrchestrator
from src.preference_parser import PreferenceParseError

CASES_PATH = "evaluation/test_cases.json"
RESULTS_JSON_PATH = "evaluation/evaluation_results.json"
RESULTS_MD_PATH = "evaluation/evaluation_results.md"


@dataclass
class CaseResult:
    """Everything recorded for one reliability test case."""

    test_id: str
    name: str
    input: str
    expected_behavior: str
    actual_behavior: str
    guardrail_result: str
    parser_result: str
    retrieval_result: str
    verification_result: str
    repair_attempted: bool
    fallback_used: bool
    passed: bool
    notes: str = ""


class _EventCollector(logging.Handler):
    """Captures every structured (JSON) log line emitted during one case run."""

    def __init__(self):
        super().__init__()
        self.events: List[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.events.append(json.loads(record.getMessage()))
        except (TypeError, ValueError):
            pass

    def find(self, event_name: str) -> Optional[dict]:
        for event in self.events:
            if event.get("event") == event_name:
                return event
        return None


def _load_cases(path: str = CASES_PATH) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["cases"]


class _InventedSongExplainer:
    """
    Stands in for `ExplanationGenerator` to simulate a generation layer that
    (unlike the real one) fails to filter its output to the retrieved songs --
    so the test genuinely exercises the VERIFIER's independent defense, rather
    than the generator's own built-in filtering.
    """

    def generate(self, context, feedback=None) -> dict:
        return {
            "summary": "These should be a great fit.",
            "song_explanations": [
                {"title": "Totally Made Up Song", "artist": "Nobody", "explanation": "Fabricated."}
            ],
            "confidence": context.confidence,
            "warnings": list(context.warnings),
        }


def _build_ai_client(case: dict) -> FakeAIClient:
    """
    Build the FakeAIClient for one case from its `ai` / `ai_raw` spec.

    Cases with both a parse and an explain reply queue both, in call order
    (parser calls the AI first, the explanation generator second/third).
    """
    ai_spec = case.get("ai", {})
    ai_raw = case.get("ai_raw", {})

    if ai_raw.get("parse") is not None:
        # Malformed / non-JSON reply, used verbatim.
        return FakeAIClient(ai_raw["parse"])

    parse_reply = json.dumps(ai_spec.get("parse", {"confidence": 0.0, "uncertain_fields": []}))

    if "explain" in ai_spec:
        explain_reply = json.dumps(ai_spec["explain"])
        return FakeAIClient(responses=[parse_reply, explain_reply])

    return FakeAIClient(parse_reply)


def _resolve_input(case: dict) -> str:
    """Build the request text, expanding the 'input_repeat' shorthand if present."""
    if "input_repeat" in case:
        spec = case["input_repeat"]
        return spec["text"] * spec["times"]
    return case.get("input", "")


def run_case(case: dict) -> CaseResult:
    """Run one test case through the real orchestrator and grade the outcome."""
    request = _resolve_input(case)
    ai_client = _build_ai_client(case)

    # Simulate "AI service unavailable / missing credentials" by making the
    # very first call to the model raise -- nothing downstream can proceed,
    # exactly like a missing API key would behave in production.
    if case.get("inject") == "service_error":
        ai_client.raise_on_next(TemporaryAIServiceError("AI service unavailable (simulated)."))

    # For the "invented song" case, swap in a stub generation layer that does
    # NOT filter to retrieved titles, so the VERIFIER's own defense is what's
    # actually under test here (not the generator's built-in filtering).
    explanation_generator = _InventedSongExplainer() if case.get("inject") == "invented" else None
    orchestrator = VibeMatchOrchestrator(ai_client, explanation_generator=explanation_generator)

    collector = _EventCollector()
    collector.setLevel(logging.DEBUG)
    orch_logger = logging.getLogger("vibematch.orchestrator")
    orch_logger.setLevel(logging.DEBUG)
    orch_logger.addHandler(collector)

    context = None
    error: Optional[Exception] = None
    try:
        context = orchestrator.recommend_and_explain(request)
    except Exception as exc:  # noqa: BLE001 -- we want to grade ANY raised error
        error = exc
    finally:
        orch_logger.removeHandler(collector)

    return _grade(case, request, context, error, collector)


def _grade(case, request, context, error, collector: _EventCollector) -> CaseResult:
    """Compare the actual outcome to the case's `expect` block and record it."""
    expect = case.get("expect", {})
    notes = []

    # -- Describe each stage from the captured structured log events ---------
    guardrail_input = collector.find("guardrail_input")
    guardrail_prefs = collector.find("guardrail_preferences")
    parsing_ok = collector.find("parsing_succeeded")
    parsing_failed = collector.find("parsing_failed")
    retrieved = collector.find("songs_retrieved")
    verification_events = [e for e in collector.events if e.get("event") == "verification_result"]
    repair = collector.find("repair_attempted")
    fallback = collector.find("fallback_used")

    if guardrail_input is not None:
        guardrail_result = (
            "allowed" if guardrail_input["allowed"] else "blocked (input guardrail)"
        )
    else:
        guardrail_result = "not reached"

    if error is not None and isinstance(error, PreferenceParseError):
        parser_result = f"error: {type(error).__name__}"
    elif error is not None and parsing_ok is None:
        parser_result = f"error: {type(error).__name__}"
    elif parsing_ok is not None:
        parser_result = f"confidence={parsing_ok['parser_confidence']}"
    elif parsing_failed is not None:
        parser_result = "error: invalid JSON"
    else:
        parser_result = "not reached"

    if retrieved is not None:
        retrieval_result = f"{retrieved['candidate_count']} songs retrieved"
    elif guardrail_input is not None and not guardrail_input["allowed"]:
        retrieval_result = "skipped (blocked before retrieval)"
    else:
        retrieval_result = "not reached"

    if verification_events:
        verification_result = "; ".join(
            f"attempt {e['attempt']}: {'passed' if e['passed'] else 'failed'}"
            for e in verification_events
        )
    else:
        verification_result = "not reached"

    repair_attempted = repair is not None
    fallback_used = fallback is not None

    # -- Actual behavior summary ----------------------------------------------
    if error is not None:
        actual_behavior = f"Raised {type(error).__name__}: {error}"
    elif context is None:
        actual_behavior = "No result produced."
    elif not context.allowed:
        actual_behavior = f"Blocked: {'; '.join(context.errors) or 'no reason given'}"
    else:
        actual_behavior = (
            f"Retrieved {len(context.recommendations)} song(s); "
            f"explanation method={context.explanation_method}; "
            f"confidence={context.confidence:.2f}"
        )

    # -- Pass/fail: compare against the case's `expect` block -----------------
    passed = True

    if "error" in expect:
        expected_type = expect["error"]
        if error is None:
            passed = False
            notes.append(f"Expected a {expected_type} to be raised, but none was.")
        else:
            actual_bases = {t.__name__ for t in type(error).__mro__}
            if expected_type not in actual_bases:
                passed = False
                notes.append(f"Expected {expected_type}, got {type(error).__name__}.")
    elif "blocked" in expect:
        if error is not None:
            passed = False
            notes.append(f"Expected a clean block, but got {type(error).__name__}: {error}")
        elif context is None or context.allowed:
            passed = False
            notes.append("Expected the request to be blocked, but it was allowed.")
    else:
        if error is not None:
            passed = False
            notes.append(f"Expected success, but raised {type(error).__name__}: {error}")
        elif context is None:
            passed = False
            notes.append("No context returned.")
        else:
            if expect.get("allowed") and not context.allowed:
                passed = False
                notes.append("Expected the request to be allowed, but it was blocked.")
            if "method" in expect and context.explanation_method != expect["method"]:
                passed = False
                notes.append(
                    f"Expected explanation method {expect['method']!r}, "
                    f"got {context.explanation_method!r}."
                )
            if "min_recommendations" in expect and len(context.recommendations) < expect["min_recommendations"]:
                passed = False
                notes.append("Fewer recommendations than expected.")
            if expect.get("needs_clarification") and not context.needs_clarification:
                passed = False
                notes.append("Expected needs_clarification=True.")
            if "warning_contains" in expect:
                term = expect["warning_contains"].lower()
                haystack = " ".join(context.warnings).lower()
                if term not in haystack:
                    passed = False
                    notes.append(f"Expected a warning mentioning {term!r}.")

    if not notes:
        notes.append("Matched expected behavior.")

    return CaseResult(
        test_id=case["id"],
        name=case["name"],
        input=request if len(request) <= 120 else f"{request[:117]}...",
        expected_behavior=case["expected_behavior"],
        actual_behavior=actual_behavior,
        guardrail_result=guardrail_result,
        parser_result=parser_result,
        retrieval_result=retrieval_result,
        verification_result=verification_result,
        repair_attempted=repair_attempted,
        fallback_used=fallback_used,
        passed=passed,
        notes=" ".join(notes),
    )


def run_all(cases_path: str = CASES_PATH) -> List[CaseResult]:
    """Run every case and return the list of results, in file order."""
    return [run_case(case) for case in _load_cases(cases_path)]


def _write_json(results: List[CaseResult], path: str, passed: int, total: int) -> None:
    payload = {
        "summary": f"{passed} of {total} reliability cases passed.",
        "passed": passed,
        "total": total,
        "results": [asdict(r) for r in results],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _write_markdown(results: List[CaseResult], path: str, passed: int, total: int) -> None:
    lines = [
        "# VibeMatch AI -- Reliability Evaluation Results",
        "",
        f"**{passed} of {total} reliability cases passed.**",
        "",
        "Generated by `python -m src.evaluator`. Every case runs through the same "
        "`VibeMatchOrchestrator` used by `src/main.py`, driven by a deterministic "
        "`FakeAIClient` -- no network access or API cost.",
        "",
        "| ID | Name | Pass/Fail | Guardrail | Parser | Retrieval | Verification | Repair | Fallback |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(
            f"| {r.test_id} | {r.name} | {status} | {r.guardrail_result} | "
            f"{r.parser_result} | {r.retrieval_result} | {r.verification_result} | "
            f"{'yes' if r.repair_attempted else 'no'} | {'yes' if r.fallback_used else 'no'} |"
        )

    lines.append("")
    lines.append("## Case Details")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.extend([
            "",
            f"### {r.test_id} -- {r.name} [{status}]",
            f"- **Input:** {r.input!r}",
            f"- **Expected behavior:** {r.expected_behavior}",
            f"- **Actual behavior:** {r.actual_behavior}",
            f"- **Notes:** {r.notes}",
        ])

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    results = run_all()
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    _write_json(results, RESULTS_JSON_PATH, passed, total)
    _write_markdown(results, RESULTS_MD_PATH, passed, total)

    print(f"{passed} of {total} reliability cases passed.")
    if passed < total:
        print("\nFailed cases:")
        for r in results:
            if not r.passed:
                print(f"  - {r.test_id} ({r.name}): {r.notes}")


if __name__ == "__main__":
    main()
