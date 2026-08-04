"""
AI client abstraction for VibeMatch AI.

This module defines a single, narrow interface -- `AIClient.generate()` -- plus
two implementations:

* `GeminiAIClient` -- the production client. It talks to Google's Gemini API
  and reads its API key and model name from environment variables, so no secret
  is ever hardcoded.
* `FakeAIClient` -- a deterministic stand-in for tests. It returns predefined
  responses and never touches the network, so the rest of the system can be
  tested offline and reproducibly.

Deliberately, there is NO recommendation, parsing, validation, or prompt logic
here. This layer only answers one question: "given a system prompt and a user
prompt, give me the model's text back (or raise a clear error)." Everything that
interprets that text lives in higher layers.
"""

import os
from typing import Optional, Protocol, runtime_checkable

from src.app_logging import safe_error_message


# ---------------------------------------------------------------------------
# Custom exceptions -- callers catch these instead of provider-specific errors,
# so the rest of the app never has to import the Gemini SDK to handle failures.
# ---------------------------------------------------------------------------
class AIClientError(Exception):
    """Base class for every error raised by this module."""


class MissingAPIKeyError(AIClientError):
    """Raised when the production client is created without an API key set."""


class InvalidAIResponseError(AIClientError):
    """
    Raised when the model returned something unusable -- an empty body, no text
    content, or a safety refusal. The caller cannot recover by retrying the same
    request unchanged.
    """


class TemporaryAIServiceError(AIClientError):
    """
    Raised for transient failures (rate limits, timeouts, connection errors,
    5xx / overloaded responses). These are worth retrying with backoff.
    """


GEMINI_API_KEY_ENV_VAR = "GEMINI_API_KEY"
GEMINI_MODEL_ENV_VAR = "GEMINI_MODEL"
MAX_TOKENS_ENV_VAR = "VIBEMATCH_MAX_TOKENS"

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_TOKENS = 1024


@runtime_checkable
class AIClient(Protocol):
    """
    The one method every AI client must provide.

    `generate` takes a system prompt (instructions/role) and a user prompt (the
    actual request) and returns the model's reply as a plain string. It raises
    one of the AIClientError subclasses above on failure.
    """

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        ...


class GeminiAIClient:
    """Production `AIClient` backed by Google's Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        api_key = api_key or os.environ.get(GEMINI_API_KEY_ENV_VAR)
        if not api_key:
            raise MissingAPIKeyError(
                f"No API key found. Set the {GEMINI_API_KEY_ENV_VAR} environment "
                "variable (see .env.example) before interactive mode."
            )

        self._model = model or os.environ.get(GEMINI_MODEL_ENV_VAR) or DEFAULT_GEMINI_MODEL
        self._max_tokens = max_tokens or int(
            os.environ.get(MAX_TOKENS_ENV_VAR, DEFAULT_MAX_TOKENS)
        )

        # Import lazily so FakeAIClient and the offline test suite need no SDK.
        try:
            from google import genai
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise AIClientError(
                "The 'google-genai' package is required for GeminiAIClient. "
                "Install it with: pip install -r requirements.txt"
            ) from exc

        self._client = genai.Client(api_key=api_key)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Send one request to Gemini and return its text reply."""
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config={
                    "system_instruction": system_prompt,
                    "max_output_tokens": self._max_tokens,
                },
            )
        except (TimeoutError, ConnectionError, OSError) as exc:
            raise TemporaryAIServiceError(safe_error_message(exc)) from exc
        except Exception as exc:
            code = getattr(exc, "code", getattr(exc, "status_code", None))
            if code == 429 or (isinstance(code, int) and code >= 500):
                raise TemporaryAIServiceError(safe_error_message(exc)) from exc
            raise InvalidAIResponseError(safe_error_message(exc)) from exc

        text = getattr(response, "text", "") or ""
        if not text.strip():
            raise InvalidAIResponseError("The Gemini model returned no text.")
        return text


class FakeAIClient:
    """
    Deterministic `AIClient` for tests -- no network, no API key, no SDK.

    Give it either a single fixed reply or a list of replies to return in order.
    You can also queue an exception to be raised, so tests can exercise the
    error-handling paths (invalid response, temporary failure) without hitting a
    real service.

    Examples
    --------
    >>> FakeAIClient("hello").generate("sys", "user")
    'hello'
    >>> client = FakeAIClient(responses=["first", "second"])
    >>> client.generate("s", "u"), client.generate("s", "u")
    ('first', 'second')
    """

    def __init__(self, response: Optional[str] = None, responses=None):
        if responses is not None:
            self._responses = list(responses)
        elif response is not None:
            self._responses = [response]
        else:
            self._responses = ["FAKE RESPONSE"]

        # Records every (system_prompt, user_prompt) pair so tests can assert on
        # what the higher layers actually sent.
        self.calls = []
        self._next_index = 0
        self._raise = None

    def raise_on_next(self, error: Exception) -> None:
        """Queue an exception for the next `generate` call (for error-path tests)."""
        self._raise = error

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the next canned response, or raise a queued exception."""
        self.calls.append((system_prompt, user_prompt))

        if self._raise is not None:
            error, self._raise = self._raise, None
            raise error

        # Repeat the last response once the queue is exhausted, so a client
        # built with a single response can be called any number of times.
        index = min(self._next_index, len(self._responses) - 1)
        self._next_index += 1
        return self._responses[index]
