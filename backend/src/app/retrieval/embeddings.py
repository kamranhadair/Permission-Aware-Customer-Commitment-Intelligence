"""One embedding model for this prototype: BAAI/bge-small-en-v1.5, run
locally via sentence-transformers — no external API, no API key. Chosen
over the base variant for a much smaller download/inference footprint
(384-dim, ~130MB) while keeping the same BGE query-instruction convention.

Two implementations, no registry/router:
- FakeEmbeddingProvider: deterministic, hash-seeded, pure Python (no
  numpy/torch). Used by the entire security/functional test suite so it
  stays hermetic and fast.
- BgeEmbeddingProvider: lazy-imports sentence_transformers inside its own
  methods, never at module import time, so importing this module in tests
  never pulls in torch even when the `embeddings` extra isn't installed.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Protocol

EMBEDDING_DIMENSIONS = 384
MODEL_NAME = "BAAI/bge-small-en-v1.5"
# BGE's recommended asymmetric-encoding instruction prefix for queries
# (not applied to documents/passages).
_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbeddingProvider:
    """Deterministic and text-content-seeded, so the same input always
    produces the same vector — but otherwise semantically meaningless.
    Tests that need a specific distance relationship between vectors
    should construct/insert embeddings directly rather than relying on
    this provider's output to be "close" for similar text."""

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
        rng = random.Random(seed)
        vector = [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIMENSIONS)]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class BgeEmbeddingProvider:
    """Loads BAAI/bge-small-en-v1.5 once (module-level lazy singleton, not a
    registry/router) on first use."""

    _model = None

    def _get_model(self):
        if BgeEmbeddingProvider._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "The real embedding provider requires the 'embeddings' extra: "
                    "pip install -e '.[dev,embeddings]'"
                ) from exc
            BgeEmbeddingProvider._model = SentenceTransformer(MODEL_NAME)
        return BgeEmbeddingProvider._model

    def embed_query(self, text: str) -> list[float]:
        model = self._get_model()
        vector = model.encode(_QUERY_INSTRUCTION + text, normalize_embeddings=True)
        return vector.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()
