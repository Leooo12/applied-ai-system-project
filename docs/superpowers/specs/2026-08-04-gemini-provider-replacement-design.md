# Gemini Provider Replacement Design

## Goal

Replace the current Anthropic-only live AI client with a Gemini-only live AI
client so `python -m src.main --interactive` can use a locally supplied
`GEMINI_API_KEY`. Keep the existing deterministic recommendation, guardrail,
verification, repair, fallback, evaluator, and offline fake-client behavior.

## Scope

In scope:

- Replace `AnthropicAIClient` with `GeminiAIClient` behind the existing
  `AIClient.generate(system_prompt, user_prompt)` protocol.
- Read credentials from `GEMINI_API_KEY` and configuration from a Gemini model
  environment variable, without storing secrets in source, tests, logs, or
  committed files.
- Map Gemini SDK failures into the existing `AIClientError` hierarchy so the
  orchestrator and CLI retain controlled error handling.
- Update the dependency, environment template, README setup instructions, and
  tests to describe Gemini.
- Preserve `FakeAIClient` and all offline evaluator behavior.

Out of scope:

- A browser UI or HTML application.
- Keeping Anthropic as a selectable provider.
- Changing recommendation weights, catalog data, guardrails, verifier rules,
  repair limits, or fallback behavior.
- Making any live API request during the test suite.

## Data flow

```text
GEMINI_API_KEY + GEMINI_MODEL
              |
              v
      GeminiAIClient.generate()
              |
              v
preference parser -> deterministic recommender -> grounded explainer
                                      |                    |
                                      +-> verifier -> repair once -> fallback
```

The Gemini client receives the existing system and user prompts. The
recommender remains the sole authority for ranking. The explanation model
continues to receive only retrieved song evidence, and the verifier/fallback
contract is unchanged.

## Configuration and security

- `.env.example` documents `GEMINI_API_KEY` and the model variable only as
  placeholders; no real key is added.
- The client reads the key from the process environment. A `.env` file is not
  implicitly loaded unless the user loads it into the shell.
- Error messages and structured logs continue to use the existing secret-safe
  sanitization path.
- The CLI reports missing Gemini credentials with a setup message and does not
  print the key.

## Error handling

- Missing `GEMINI_API_KEY` -> `MissingAPIKeyError`.
- Connection, timeout, rate-limit, and transient service failures ->
  `TemporaryAIServiceError`.
- Empty, refused, malformed, or otherwise unusable model responses ->
  `InvalidAIResponseError` or the existing parser/explanation errors at their
  current boundaries.
- No retry loop is added to the provider; the existing orchestrator’s bounded
  explanation repair remains the only repair path.

## Testing plan

Before implementation, add failing tests for:

1. Gemini client construction requiring `GEMINI_API_KEY`.
2. Gemini client translating a mocked SDK text response into a string.
3. Gemini client translating representative SDK failures into the existing
   error classes.
4. Interactive mode displaying the Gemini setup message when the key is
   missing.
5. Existing fake-client, orchestrator, guardrail, verifier, and evaluator
   behavior remaining unchanged.

The tests must use mocked or fake provider responses and must never require a
real Gemini key or network access. After implementation, run the complete
offline suite and the reliability evaluator, then perform one opt-in manual
live smoke test only when the user has configured their own key.

## Acceptance criteria

- `python -m pytest -v` passes without a real key or network access.
- `python -m src.evaluator` still reports 12/12 reliability cases passed.
- `python -m src.main` still runs the deterministic recommender without a key.
- With `GEMINI_API_KEY` configured and the Gemini SDK installed,
  `python -m src.main --interactive` reaches the Gemini-backed parser and
  explanation flow.
- With no key configured, interactive mode exits with a clear Gemini setup
  message rather than a traceback.
- No `ANTHROPIC_API_KEY`, Anthropic dependency, or Anthropic-only setup text
  remains in the active project documentation or implementation.
