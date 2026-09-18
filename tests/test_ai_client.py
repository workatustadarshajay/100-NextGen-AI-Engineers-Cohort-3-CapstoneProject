from pydantic import BaseModel

from app.services.ai.client import GeminiQuotaError, generate_structured


class _Response(BaseModel):
    value: str


class _QuotaFailure(Exception):
    code = 429


class _Interactions:
    def create(self, **kwargs):
        raise _QuotaFailure("quota exceeded for generate_content_free_tier_requests")


class _FakeClient:
    interactions = _Interactions()


def test_generate_structured_classifies_quota_errors():
    try:
        generate_structured(
            _Response,
            "prompt",
            "system",
            client=_FakeClient(),
        )
    except GeminiQuotaError as error:
        assert "quota is exhausted" in str(error)
        assert "gemini-3.8-flash" in str(error)
    else:
        raise AssertionError("quota error was not classified")
