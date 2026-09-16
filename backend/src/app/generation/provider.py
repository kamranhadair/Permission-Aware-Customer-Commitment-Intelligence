"""One generation provider, no registry/router — mirrors
app/retrieval/embeddings.py's shape exactly: a small Protocol, one
deterministic fake used by the whole test suite, and one real
implementation that lazy-imports its SDK inside its own method so
importing this module never pulls in the `google-genai` package when the
optional `generation` extra isn't installed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Protocol

from app.generation.errors import GenerationFailure
from app.generation.prompt import SYSTEM_PROMPT, build_user_message
from app.generation.types import GeneratedAnswer, GenerationContext
from app.generation.validation import RawGeneratedAnswer, parse_provider_payload

MODEL_NAME = "gemini-2.5-flash"


class AnswerGenerator(Protocol):
    model_name: str

    def generate(self, query: str, context: GenerationContext) -> GeneratedAnswer: ...


class FakeAnswerGenerator:
    """Deterministic test double — a scriptable spy, not a text-similarity
    simulator (same philosophy as FakeEmbeddingProvider being
    deterministic-but-meaningless rather than semantically real).

    Configure with a fixed `GeneratedAnswer`, a callable that inspects
    (query, context) and returns one, or `raise_failure=True` to simulate a
    provider/network error. Records the last call so tests can assert on
    exactly what context reached "the model".
    """

    model_name = "fake"

    def __init__(
        self,
        respond_with: GeneratedAnswer | Callable[[str, GenerationContext], GeneratedAnswer] | None = None,
        raise_failure: bool = False,
    ) -> None:
        self._respond_with = respond_with
        self._raise_failure = raise_failure
        self.last_query: str | None = None
        self.last_context: GenerationContext | None = None

    def generate(self, query: str, context: GenerationContext) -> GeneratedAnswer:
        self.last_query = query
        self.last_context = context
        if self._raise_failure:
            raise GenerationFailure("simulated provider failure")
        if callable(self._respond_with):
            return self._respond_with(query, context)
        if self._respond_with is not None:
            return self._respond_with
        return GeneratedAnswer(status="insufficient_evidence", claims=[])


class GeminiAnswerGenerator:
    """Lazy singleton, loaded on first use — same pattern as
    BgeEmbeddingProvider._get_model. Uses Gemini's native structured-output
    mode (response_mime_type="application/json" + response_schema) rather
    than a simulated tool call — the SDK accepts our RawGeneratedAnswer
    Pydantic model directly as the schema, so the wire schema and the
    validation schema can never drift apart. Structured output lowers
    malformed-output risk, it does not remove the need to run the result
    through parse_provider_payload before trusting it."""

    model_name = MODEL_NAME

    _client = None

    def _get_client(self):
        if GeminiAnswerGenerator._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise ImportError(
                    "The real answer generator requires the 'generation' extra: "
                    "pip install -e '.[dev,generation]'"
                ) from exc
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise GenerationFailure("GEMINI_API_KEY is not set")
            GeminiAnswerGenerator._client = genai.Client(api_key=api_key)
        return GeminiAnswerGenerator._client

    def generate(self, query: str, context: GenerationContext) -> GeneratedAnswer:
        from google.genai import types

        client = self._get_client()
        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=build_user_message(query, context),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=RawGeneratedAnswer,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — any provider/network failure is a GenerationFailure
            raise GenerationFailure(f"provider request failed: {exc}") from exc

        if not response.text:
            raise GenerationFailure("provider response contained no text")
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise GenerationFailure(f"provider response was not valid JSON: {exc}") from exc

        return parse_provider_payload(payload)
