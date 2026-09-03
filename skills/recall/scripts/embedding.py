"""Embedding client abstraction for midnight-recall.

Provides a pluggable interface: real implementation calls an API,
fake implementation returns deterministic pseudo-vectors for testing.
"""
import hashlib
import json
from typing import Optional


class EmbeddingClient:
    """Base embedding client. Subclass to support different backends."""

    def __init__(self, dimension: int = 1024, api_url: str = "", api_key: str = "", model: str = ""):
        self.dimension = dimension
        self.api_url = api_url
        self.api_key = api_key
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, return list of vectors."""
        raise NotImplementedError


class FakeEmbeddingClient(EmbeddingClient):
    """Deterministic pseudo-embedding for testing. Text → hash → vector."""

    def __init__(self, dimension: int = 1024):
        super().__init__(dimension=dimension)

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            h = hashlib.sha256(text.encode('utf-8')).digest()
            vec = [((h[i % 32] + i) % 256) / 255.0 for i in range(self.dimension)]
            results.append(vec)
        return results


class SemanticFakeEmbeddingClient(EmbeddingClient):
    """Deterministic, semantically-aware pseudo-embedding for testing.

    Vector = normalized bag of character bigrams. Two strings share a feature
    index iff they share characters, so a query that mentions a topic tag
    (e.g. "跑马拉松 紧张" vs tag "马拉松") gets a high cosine for that tag and
    ~0 for unrelated tags. This lets integration tests exercise the real
    query → seed sensing → pulse propagation path deterministically, without
    engine test hooks.
    """

    FEATURE_DIM = 256

    def __init__(self, dimension: int = 1024):
        super().__init__(dimension=dimension)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._bow(text) for text in texts]

    def _bow(self, text: str) -> list[float]:
        from collections import Counter
        chars = [c for c in text if not c.isspace()]
        features = []
        for i in range(len(chars)):
            features.append(chars[i])
            if i + 1 < len(chars):
                features.append(chars[i] + chars[i + 1])
        vec = [0.0] * self.FEATURE_DIM
        for feat, cnt in Counter(features).items():
            idx = int(hashlib.md5(feat.encode('utf-8')).hexdigest()[:8], 16) % self.FEATURE_DIM
            vec[idx] += cnt
        norm = sum(x * x for x in vec) ** 0.5
        if norm:
            vec = [x / norm for x in vec]
        return vec


class SiliconFlowEmbeddingClient(EmbeddingClient):
    """Real embedding client calling SiliconFlow's OpenAI-compatible API."""

    def __init__(self, dimension: int = 1024, api_url: str = "", api_key: str = "", model: str = "BAAI/bge-m3"):
        super().__init__(dimension=dimension, api_url=api_url, api_key=api_key, model=model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        import requests
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "input": texts
        }
        resp = requests.post(
            f"{self.api_url.rstrip('/')}/embeddings",
            headers=headers,
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        # Sort by index to preserve order
        sorted_data = sorted(data['data'], key=lambda x: x['index'])
        return [item['embedding'] for item in sorted_data]


def load_embedding_client(config: Optional[dict] = None) -> EmbeddingClient:
    """Factory: load embedding client from config dict.

    Config format:
        {
            "api_url": "https://api.siliconflow.cn/v1",
            "api_key": "sk-...",
            "model": "BAAI/bge-m3",
            "dimension": 1024
        }
    If config is None or empty, returns FakeEmbeddingClient (for testing/offline).
    """
    if not config or not config.get('api_key'):
        return FakeEmbeddingClient(dimension=config.get('dimension', 1024) if config else 1024)
    return SiliconFlowEmbeddingClient(
        dimension=config.get('dimension', 1024),
        api_url=config.get('api_url', ''),
        api_key=config.get('api_key', ''),
        model=config.get('model', 'BAAI/bge-m3')
    )