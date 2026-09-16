"""Embedding client abstraction for midnight-recall.

Provides a pluggable interface: real implementation calls an API,
fake implementation returns deterministic pseudo-vectors for testing.
"""
import hashlib
import json
import os
import sys
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


def _mean_pool_l2(token_emb: list, masks: list) -> list[list[float]]:
    """Mean-pool non-padded token embeddings, then L2-normalize each sentence.

    Pure function (no model needed) so it is unit-testable offline.
    `token_emb` is nested [sentence][token][dim]; `masks` is [sentence][token]
    of 0/1. Padded tokens (mask 0) are excluded from the mean.
    """
    out: list[list[float]] = []
    for sent_emb, m in zip(token_emb, masks):
        dim = len(sent_emb[0]) if sent_emb else 0
        acc = [0.0] * dim
        n = 0
        for emb, flag in zip(sent_emb, m):
            if not flag:
                continue
            for i in range(dim):
                acc[i] += emb[i]
            n += 1
        vec = [a / n for a in acc] if n else [0.0] * dim
        norm = sum(x * x for x in vec) ** 0.5
        if norm:
            vec = [x / norm for x in vec]
        out.append(vec)
    return out


class LocalOnnxEmbeddingClient(EmbeddingClient):
    """Real local embedding via ONNX Runtime — no cloud, no API key.

    Loads a tokenizer (tokenizers lib) + ONNX model from `model_dir`.
    Expected layout inside model_dir:
        model.onnx      ONNX-exported embedding model (BAAI/bge-m3)
        tokenizer.json  XLM-RoBERTa / bge-m3 tokenizer
        config.json     optional; may carry "hidden_size" (= dimension)

    `embed` runs forward pass, mean-pools non-padded tokens and L2-normalizes.
    """

    def __init__(self, dimension: int = 1024, model_dir: str = "",
                 max_length: int = 8192):
        super().__init__(dimension=dimension, model="bge-m3-local")
        if not model_dir or not os.path.isdir(model_dir):
            raise ValueError(
                f"Local ONNX embedding requested but model_dir not found: "
                f"{model_dir!r}. Set MIDNIGHT_MODEL_DIR (or pass model_dir) "
                f"to a directory containing model.onnx + tokenizer.json."
            )
        onnx_path = os.path.join(model_dir, 'model.onnx')
        tok_path = os.path.join(model_dir, 'tokenizer.json')
        if not os.path.exists(onnx_path):
            raise ValueError(f"model.onnx missing in {model_dir!r}")
        if not os.path.exists(tok_path):
            raise ValueError(f"tokenizer.json missing in {model_dir!r}")

        import onnxruntime  # local import keeps pure unit tests dependency-light
        import numpy as np
        from tokenizers import Tokenizer
        self._np = np
        self._sess = onnxruntime.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
        inputs = {i.name for i in self._sess.get_inputs()}
        # auto-detect input names: tokens + mask are the two common ones
        self._tok_name = next((n for n in inputs if 'token' in n or n == 'input_ids'), None)
        self._mask_name = next((n for n in inputs if 'mask' in n or n == 'attention_mask'), None)
        if self._tok_name is None or self._mask_name is None:
            names = sorted(inputs)
            if len(names) >= 2:
                self._tok_name, self._mask_name = names[0], names[1]
            else:
                raise ValueError(f"unexpected ONNX graph inputs: {names}")
        self._tok = Tokenizer.from_file(tok_path)
        self._pad_id = self._tok.token_to_id('[PAD]') or 1
        self.max_length = max(1, int(max_length or 8192))

    def embed(self, texts: list[str]) -> list[list[float]]:
        np = self._np
        toks = self._tok.encode_batch([str(t) for t in texts])
        input_ids = [t.ids[: self.max_length] for t in toks]
        maxlen = max(len(x) for x in input_ids) if input_ids else 0
        batch = np.array(
            [ids + [self._pad_id] * (maxlen - len(ids)) for ids in input_ids],
            dtype=np.int64,
        )
        masks = np.array(
            [[1] * len(ids) + [0] * (maxlen - len(ids)) for ids in input_ids],
            dtype=np.int64,
        )
        if maxlen == 0:
            return [[0.0] * self.dimension for _ in texts]
        out = self._sess.run(None, {self._tok_name: batch, self._mask_name: masks})
        # [batch, seq, hidden] -> mean_pool + L2 normalize
        hidden = out[0].tolist()
        return _mean_pool_l2(hidden, masks.tolist())


def _model_complete(model_dir: str) -> bool:
    """A usable local model needs the graph, the weights and the tokenizer."""
    if not model_dir or not os.path.isdir(model_dir):
        return False
    for name in ('model.onnx', 'model.onnx_data', 'tokenizer.json'):
        p = os.path.join(model_dir, name)
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            return False
    return True


def _skill_model_dir() -> str:
    """Model dir shipped beside the skill package (skills/recall/models/bge-m3)."""
    return os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'models', 'bge-m3'))


def _user_model_dir() -> str:
    """Per-user global drop target: ~/.midnight/models/bge-m3."""
    return os.path.join(os.path.expanduser('~'), '.midnight', 'models', 'bge-m3')


def _model_candidates() -> list[str]:
    """Ordered search list: skill-local first, then per-user global."""
    return [_skill_model_dir(), _user_model_dir()]


def _auto_download_enabled() -> bool:
    val = os.environ.get('MIDNIGHT_EMBEDDING_AUTO_DOWNLOAD', '1').strip().lower()
    return val not in ('0', 'false', 'no', 'off')


def _get_downloader():
    """Return the download_bge_m3 module (single instance on both sys.path layouts).

    Both `download_bge_m3` and `scripts.download_bge_m3` can resolve to the same
    file, but as two distinct module objects. Reading from sys.modules first
    keeps a single instance here (and lets tests patch it deterministically).
    """
    if 'download_bge_m3' in sys.modules:
        return sys.modules['download_bge_m3']
    if 'scripts.download_bge_m3' in sys.modules:
        return sys.modules['scripts.download_bge_m3']
    try:
        import download_bge_m3 as m
    except ImportError:
        import scripts.download_bge_m3 as m
    return m


def _resolve_local_model_dir(config: Optional[dict]) -> str:
    """3-tier local model resolution:
      1. explicit model_dir env/config (highest priority, required to exist)
      2. skill-local models dir
      3. per-user ~/.midnight/models/bge-m3
      else auto-download into the per-user dir (unless auto-download disabled).
    """
    explicit = config.get('model_dir') if config else None
    explicit = explicit or os.environ.get('MIDNIGHT_MODEL_DIR', '')
    if explicit:
        if not _model_complete(explicit):
            raise ValueError(
                f"MIDNIGHT_MODEL_DIR points at {explicit!r} but it's missing "
                f"model.onnx, model.onnx_data or tokenizer.json. Re-run "
                f"python skills/recall/scripts/download_bge_m3.py --output-dir {explicit!r}")
        return explicit
    for cand in _model_candidates():
        if _model_complete(cand):
            return cand
    if _auto_download_enabled():
        target = _user_model_dir()
        print(f'[recall] local model not found; auto-downloading bge-m3 -> {target}', flush=True)
        _get_downloader().download_model(target)
        if not _model_complete(target):
            raise ValueError('auto-download finished but model files are incomplete')
        return target
    raise ValueError(
        'Local ONNX embedding requested but no model found. Install one via '
        'python skills/recall/scripts/download_bge_m3.py --output-dir '
        '~/.midnight/models/bge-m3 , or point MIDNIGHT_MODEL_DIR at an existing '
        'copy. (Set MIDNIGHT_EMBEDDING_AUTO_DOWNLOAD=0 to disable auto-download.)')


def load_embedding_client(config: Optional[dict] = None) -> EmbeddingClient:
    """Factory: load embedding client from config dict.

    Config format:
        {
            "backend": "onnx"|"api"|"fake" (optional; default from env MIDNIGHT_EMBEDDING),
            "api_url": "https://api.siliconflow.cn/v1",
            "api_key": "sk-...",
            "model": "BAAI/bge-m3",
            "model_dir": "~/.midnight/models/bge-m3",  # for backend=onnx
            "dimension": 1024
        }
    Selection (backward-compatible):
      - backend == local/onnx  -> LocalOnnxEmbeddingClient (raises if model missing)
      - api_key present        -> SiliconFlowEmbeddingClient
      - otherwise              -> FakeEmbeddingClient (testing/offline)
    If config is None, defaults to FakeEmbeddingClient.
    """
    config = config or {}
    backend = (config.get('backend') or os.environ.get('MIDNIGHT_EMBEDDING') or '').strip().lower()
    dimension = int(config.get('dimension', 1024) or 1024)

    if backend in ('local', 'onnx'):
        model_dir = _resolve_local_model_dir(config)
        return LocalOnnxEmbeddingClient(dimension=dimension, model_dir=model_dir)

    if config.get('api_key'):
        return SiliconFlowEmbeddingClient(
            dimension=dimension,
            api_url=config.get('api_url', ''),
            api_key=config.get('api_key', ''),
            model=config.get('model', 'BAAI/bge-m3')
        )
    return FakeEmbeddingClient(dimension=dimension)