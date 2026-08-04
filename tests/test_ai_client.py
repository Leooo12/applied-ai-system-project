"""Tests for the provider-agnostic AI client abstraction."""

import sys
import types
import pytest

from src.ai_client import (
    AIClient,
    FakeAIClient,
    GeminiAIClient,
    MissingAPIKeyError,
    InvalidAIResponseError,
    TemporaryAIServiceError,
    GEMINI_API_KEY_ENV_VAR,
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


def _install_fake_genai(monkeypatch, response=None, error=None):
    class FakeModels:
        def generate_content(self, **kwargs):
            if error:
                raise error
            return response

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = lambda api_key: types.SimpleNamespace(
        models=FakeModels(), api_key=api_key
    )
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)


def test_gemini_client_requires_an_api_key(monkeypatch):
    monkeypatch.delenv(GEMINI_API_KEY_ENV_VAR, raising=False)

    with pytest.raises(MissingAPIKeyError):
        GeminiAIClient()


def test_gemini_client_satisfies_protocol_and_returns_sdk_text(monkeypatch):
    _install_fake_genai(monkeypatch, response=types.SimpleNamespace(text="OK"))

    client = GeminiAIClient(api_key="test-key", model="test-model")

    assert isinstance(client, AIClient)
    assert client.generate("system", "user") == "OK"


def test_gemini_client_rejects_empty_sdk_text(monkeypatch):
    _install_fake_genai(monkeypatch, response=types.SimpleNamespace(text=""))

    client = GeminiAIClient(api_key="test-key", model="test-model")

    with pytest.raises(InvalidAIResponseError):
        client.generate("system", "user")


def test_gemini_client_maps_timeout_to_temporary_error(monkeypatch):
    _install_fake_genai(monkeypatch, error=TimeoutError("timed out"))

    client = GeminiAIClient(api_key="test-key", model="test-model")

    with pytest.raises(TemporaryAIServiceError):
        client.generate("system", "user")


def test_custom_exceptions_share_a_common_base():
    from src.ai_client import AIClientError

    for error_type in (
        MissingAPIKeyError,
        InvalidAIResponseError,
        TemporaryAIServiceError,
    ):
        assert issubclass(error_type, AIClientError)
