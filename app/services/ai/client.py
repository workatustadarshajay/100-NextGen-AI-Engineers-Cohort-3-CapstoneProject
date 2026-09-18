import json
import logging
from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import types
from groq import Groq
from pydantic import BaseModel, ValidationError

from app.config import get_ai_settings
from app.observability import safe_error_message


SchemaT = TypeVar("SchemaT", bound=BaseModel)
AI_LOGGER = logging.getLogger("neuron.ai")


class MissingGeminiKeyError(RuntimeError):
    """Raised when GEMINI_API_KEY is not configured."""


class GeminiResponseError(RuntimeError):
    """Raised when the model returns output that does not match the requested schema."""


class GeminiQuotaError(RuntimeError):
    """Raised when the configured Gemini project has exhausted its quota."""


class MissingGroqKeyError(RuntimeError):
    """Raised when Groq fallback is requested without a configured API key."""


class GroqFallbackError(RuntimeError):
    """Raised when the Groq fallback cannot produce a valid response."""


def _is_quota_error(error: BaseException) -> bool:
    for attribute in ("status_code", "code", "http_status"):
        status_code = getattr(error, attribute, None)
        try:
            if int(status_code) == 429:
                return True
        except (TypeError, ValueError):
            pass
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("quota exceeded", "resource_exhausted", "too_many_requests")
    )


def _quota_error(operation: str, model: str) -> GeminiQuotaError:
    message = (
        f"Gemini quota is exhausted while {operation} with {model}. "
        "Configure GROQ_API_KEY for fallback, or wait for the project quota window "
        "to reset/enable billing."
    )
    return GeminiQuotaError(message)


def _parse_structured_output(
    schema: type[SchemaT], output_text: str | None, provider: str
) -> SchemaT:
    if not output_text:
        raise GeminiResponseError(f"{provider} {schema.__name__}: the model returned an empty response.")
    try:
        return schema.model_validate_json(output_text)
    except ValidationError as error:
        raise GeminiResponseError(f"{provider} {schema.__name__}: {error}") from error


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    settings = get_ai_settings()
    if not settings.api_key:
        raise MissingGeminiKeyError(
            "GEMINI_API_KEY is not set. Add it to your environment or .env file "
            "before running the clinical workflow."
        )
    return genai.Client(api_key=settings.api_key)


@lru_cache(maxsize=1)
def get_groq_client() -> Groq:
    settings = get_ai_settings()
    if not settings.groq_api_key:
        raise MissingGroqKeyError(
            "GROQ_API_KEY is not set, so the Groq fallback is unavailable."
        )
    return Groq(api_key=settings.groq_api_key, timeout=settings.request_timeout)


def _generate_with_gemini(
    schema: type[SchemaT],
    prompt: str,
    system_instruction: str,
    *,
    client: genai.Client | None = None,
) -> SchemaT:
    settings = get_ai_settings()
    active_client = client or get_client()
    try:
        interaction = active_client.interactions.create(
            model=settings.model,
            input=prompt,
            system_instruction=system_instruction,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema.model_json_schema(),
            },
            timeout=settings.request_timeout,
        )
    except Exception as error:
        if _is_quota_error(error):
            raise _quota_error("structured generation", settings.model) from error
        raise

    return _parse_structured_output(schema, interaction.output_text, "Gemini")


def _generate_with_groq(
    schema: type[SchemaT],
    prompt: str,
    system_instruction: str,
    *,
    client: Groq | None = None,
) -> SchemaT:
    settings = get_ai_settings()
    active_client = client or get_groq_client()
    schema_instruction = (
        f"{system_instruction}\n\nReturn only a JSON object matching this schema:\n"
        f"{json.dumps(schema.model_json_schema(), separators=(',', ':'))}"
    )
    try:
        response = active_client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": schema_instruction},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_completion_tokens=4096,
            timeout=settings.request_timeout,
        )
    except Exception as error:
        if _is_quota_error(error):
            raise GroqFallbackError(
                f"Groq fallback quota is exhausted for {settings.groq_model}."
            ) from error
        raise GroqFallbackError(
            "Groq fallback request failed: "
            f"{safe_error_message(error)}"
        ) from error

    try:
        output_text = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as error:
        raise GroqFallbackError("Groq fallback returned no usable response.") from error
    try:
        return _parse_structured_output(schema, output_text, "Groq")
    except GeminiResponseError as error:
        raise GroqFallbackError(str(error)) from error


def generate_structured(
    schema: type[SchemaT],
    prompt: str,
    system_instruction: str,
    *,
    client: genai.Client | None = None,
    fallback_client: Groq | None = None,
) -> SchemaT:
    """Call Gemini, falling back to Groq only when Gemini quota is exhausted."""
    try:
        return _generate_with_gemini(
            schema, prompt, system_instruction, client=client
        )
    except GeminiQuotaError as gemini_error:
        try:
            result = _generate_with_groq(
                schema,
                prompt,
                system_instruction,
                client=fallback_client,
            )
        except MissingGroqKeyError:
            raise gemini_error
        except GroqFallbackError:
            raise
        AI_LOGGER.warning(
            "gemini_quota_fallback",
            extra={"provider": "groq", "model": get_ai_settings().groq_model},
        )
        return result


def embed_texts(
    texts: list[str],
    task_type: str,
    *,
    client: genai.Client | None = None,
) -> list[list[float]]:
    """Embed one batch of texts for the guideline index or a retrieval query."""
    if not texts:
        return []
    settings = get_ai_settings()
    active_client = client or get_client()
    try:
        result = active_client.models.embed_content(
            model=settings.embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(task_type=task_type),
        )
    except Exception as error:
        if _is_quota_error(error):
            raise _quota_error("embedding generation", settings.embedding_model) from error
        raise
    return [list(embedding.values) for embedding in result.embeddings]
