"""
AI client abstraction for VibeMatch AI.

This module defines a single, narrow interface -- `AIClient.generate()` -- plus
two implementations:

* `AnthropicAIClient` -- the production client. It talks to Anthropic's Claude
  models and reads its API key and model name from environment variables, so no
  secret is ever hardcoded.
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


# ---------------------------------------------------------------------------
# Custom exceptions -- callers catch these instead of provider-specific errors,
# so the rest of the app never has to import the Anthropic SDK to handle failures.
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


# The name of the environment variable holding the API key. Kept as a constant
# so the production client and any docs/tests refer to the same string.
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
MODEL_ENV_VAR = "VIBEMATCH_MODEL"
MAX_TOKENS_ENV_VAR = "VIBEMATCH_MAX_TOKENS"

# Default model when VIBEMATCH_MODEL is unset. Opus is the most capable Claude
# model and a safe default; override it via the env var for cheaper/faster runs.
DEFAULT_MODEL = "claude-opus-5"
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


class AnthropicAIClient:
    """
    Production `AIClient` backed by Anthropic's Claude models.

    The API key and model name come from environment variables -- never from
    source code. Construction fails fast with `MissingAPIKeyError` if no key is
    configured, so a misconfigured deployment is caught immediately rather than
    on the first request.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Build the client from explicit values, falling back to environment
        variables. Nothing here is hardcoded: `api_key` defaults to
        `ANTHROPIC_API_KEY`, `model` to `VIBEMATCH_MODEL` (or DEFAULT_MODEL).
        """
        api_key = api_key or os.environ.get(API_KEY_ENV_VAR)
        if not api_key:
            raise MissingAPIKeyError(
                f"No API key found. Set the {API_KEY_ENV_VAR} environment "
                f"variable (see .env.example) before creating an AnthropicAIClient."
            )

        self._model = model or os.environ.get(MODEL_ENV_VAR) or DEFAULT_MODEL
        self._max_tokens = max_tokens or int(
            os.environ.get(MAX_TOKENS_ENV_VAR, DEFAULT_MAX_TOKENS)
        )

        # Import the SDK lazily so that this module -- and the FakeAIClient path
        # used by tests -- can be imported without the `anthropic` package
        # installed and without any network access.
        try:
            import anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise AIClientError(
                "The 'anthropic' package is required for AnthropicAIClient. "
                "Install it with: pip install -r requirements.txt"
            ) from exc

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send one request to Claude and return its text reply.

        Transient/service failures become `TemporaryAIServiceError`; empty or
        refused responses become `InvalidAIResponseError`.
        """
        anthropic = self._anthropic
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
            raise TemporaryAIServiceError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            # 5xx / overloaded are transient; other statuses are not retryable.
            if exc.status_code >= 500:
                raise TemporaryAIServiceError(str(exc)) from exc
            raise InvalidAIResponseError(str(exc)) from exc

        # A safety refusal comes back as a normal 200 -- treat it as unusable.
        if getattr(response, "stop_reason", None) == "refusal":
            raise InvalidAIResponseError("The AI model refused the request.")

        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        if not text.strip():
            raise InvalidAIResponseError("The AI model returned an empty response.")

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
