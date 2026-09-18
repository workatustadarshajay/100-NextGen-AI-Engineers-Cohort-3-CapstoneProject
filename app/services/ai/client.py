from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import get_ai_settings


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class MissingGeminiKeyError(RuntimeError):
    """Raised when GEMINI_API_KEY is not configured."""


class GeminiResponseError(RuntimeError):
    """Raised when the model returns output that does not match the requested schema."""


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    settings = get_ai_settings()
    if not settings.api_key:
        raise MissingGeminiKeyError(
            "GEMINI_API_KEY is not set. Add it to your environment or .env file "
            "before running the clinical workflow."
        )
    return genai.Client(api_key=settings.api_key)


def generate_structured(
    schema: type[SchemaT],
    prompt: str,
    system_instruction: str,
    *,
    client: genai.Client | None = None,
) -> SchemaT:
    """Call Gemini and parse the reply into the given Pydantic schema."""
    settings = get_ai_settings()
    active_client = client or get_client()
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

    output_text = interaction.output_text
    if not output_text:
        raise GeminiResponseError(f"{schema.__name__}: the model returned an empty response.")
    try:
        return schema.model_validate_json(output_text)
    except ValidationError as error:
        raise GeminiResponseError(f"{schema.__name__}: {error}") from error


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
    result = active_client.models.embed_content(
        model=settings.embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return [list(embedding.values) for embedding in result.embeddings]
