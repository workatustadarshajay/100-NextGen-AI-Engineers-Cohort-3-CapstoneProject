from types import SimpleNamespace

from pydantic import BaseModel

import app.services.ai.client as client_module
from app.services.ai.client import (
    GeminiQuotaError,
    MissingGroqKeyError,
    generate_structured,
)


class _Response(BaseModel):
    value: str


class _QuotaFailure(Exception):
    code = 429


class _Interactions:
    def create(self, **kwargs):
        raise _QuotaFailure("quota exceeded for generate_content_free_tier_requests")


class _FakeClient:
    interactions = _Interactions()


class _GroqCompletions:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.output_text))]
        )


class _FakeGroqClient:
    def __init__(self, output_text):
        self.completions = _GroqCompletions(output_text)
        self.chat = SimpleNamespace(completions=self.completions)


def test_generate_structured_uses_groq_for_gemini_quota_errors():
    groq_client = _FakeGroqClient('{"value":"from groq"}')

    result = generate_structured(
        _Response,
        "prompt",
        "system",
        client=_FakeClient(),
        fallback_client=groq_client,
    )

    assert result.value == "from groq"
    request = groq_client.completions.calls[0]
    assert request["model"] == "llama-3.3-70b-versatile"
    assert request["response_format"] == {"type": "json_object"}
    assert request["temperature"] == 0


def test_generate_structured_classifies_quota_errors_without_groq_key(monkeypatch):
    def missing_groq_key():
        raise MissingGroqKeyError("missing test key")

    monkeypatch.setattr(client_module, "get_groq_client", missing_groq_key)

    try:
        generate_structured(
            _Response,
            "prompt",
            "system",
            client=_FakeClient(),
        )
    except GeminiQuotaError as error:
        assert "quota is exhausted" in str(error)
        assert "structured generation with" in str(error)
    else:
        raise AssertionError("quota error was not classified")
