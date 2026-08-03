"""
Tests for the AI client abstraction.

Every test here uses FakeAIClient or checks construction guards -- nothing
touches the network or requires the `anthropic` package, so the suite stays
reproducible and offline.
"""

import pytest

from src.ai_client import (
    AIClient,
    FakeAIClient,
    AnthropicAIClient,
    MissingAPIKeyError,
    InvalidAIResponseError,
    TemporaryAIServiceError,
    API_KEY_ENV_VAR,
)


def test_fake_client_satisfies_the_protocol():
    assert isinstance(FakeAIClient("hi"), AIClient)


def test_fake_client_returns_fixed_response_and_records_calls():
    client = FakeAIClient("recommended songs")

    result = client.generate("system", "user request")

    assert result == "recommended songs"
    assert client.calls == [("system", "user request")]


def test_fake_client_returns_queued_responses_in_order():
    client = FakeAIClient(responses=["first", "second"])

    assert client.generate("s", "u") == "first"
    assert client.generate("s", "u") == "second"
    # Exhausted queue repeats the last response so callers never crash.
    assert client.generate("s", "u") == "second"


def test_fake_client_can_raise_a_queued_error():
    client = FakeAIClient("ok")
    client.raise_on_next(TemporaryAIServiceError("service down"))

    with pytest.raises(TemporaryAIServiceError):
        client.generate("s", "u")

    # The error fires only once; the next call succeeds normally.
    assert client.generate("s", "u") == "ok"


def test_anthropic_client_requires_an_api_key(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)

    with pytest.raises(MissingAPIKeyError):
        AnthropicAIClient()


def test_custom_exceptions_share_a_common_base():
    from src.ai_client import AIClientError

    for error_type in (
        MissingAPIKeyError,
        InvalidAIResponseError,
        TemporaryAIServiceError,
    ):
        assert issubclass(error_type, AIClientError)
