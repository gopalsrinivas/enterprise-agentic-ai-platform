"""Embedding provider boundary; tests default to deterministic local vectors."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from openai import AsyncOpenAI


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbeddingProvider:
    model = "deterministic-fake-v1"

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in text.casefold().split():
                digest = hashlib.sha256(token.encode()).digest()
                vector[int.from_bytes(digest[:4], "big") % self.dimensions] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str, dimensions: int = 1536) -> None:
        self.model = model
        self.dimensions = dimensions
        self._client = AsyncOpenAI(api_key=api_key)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            input=texts, model=self.model, dimensions=self.dimensions
        )
        return [item.embedding for item in response.data]
