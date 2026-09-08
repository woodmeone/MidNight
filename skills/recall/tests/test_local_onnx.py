"""Tests for local ONNX embedding backend (V2 vectorization).

Covers the two pieces that don't require a real downloaded model:
  1. `_mean_pool_l2`: mean-pooling + L2-normalization correctness.
  2. `load_embedding_client` routing: backend selection must stay
     backward-compatible (no config -> FakeEmbeddingClient; api_key ->
     SiliconFlowEmbeddingClient), while an explicit local/onnx backend
     without a model directory must fail loudly instead of silently
     degrading to fake vectors.
"""
import os
import pytest

from scripts.embedding import (
    load_embedding_client,
    FakeEmbeddingClient,
    SiliconFlowEmbeddingClient,
    LocalOnnxEmbeddingClient,
    _mean_pool_l2,
)
import scripts.embedding as emb


def _fake_tokenizer(tmp_path):
    """Build a minimal tokenizer.json that can encode text into ints.

    LocalOnnx truncation/padding logic is what matters here — a real XLM-R
    file isn't required (and avoids loading the 2GB onnx weights), so we use
    a tiny hand-rolled tokenizer that assigns token ids by char hash.
    """
    import json
    pieces = {
        "version": "1.0",
        "normalizer": None,
        "pre_tokenizer": {"type": "Whitespace"},  # space-split so 'a a a...' yields many tokens
        "model": {
            "type": "WordLevel",
            "unk_token": "[UNK]",
            "vocab": {
                "[PAD]": 1, "[UNK]": 0, "[CLS]": 2, "[SEP]": 3,
                "a": 4, "b": 5, "c": 6,
            },
        },
        "post_processor": None,
        "decoder": None,
    }
    p = tmp_path / "tokenizer.json"
    p.write_text(json.dumps(pieces), encoding="utf-8")
    return str(p)


class TestMeanPoolL2:
    def test_pools_only_non_pad_tokens(self):
        # 2 tokens are padded; only 2 non-padded tokens contribute.
        token_emb = [
            [[1.0, 0.0], [3.0, 0.0], [0.0, 0.0], [0.0, 0.0]],  # 2 real + 2 pad
        ]
        mask = [[1, 1, 0, 0]]
        vecs = _mean_pool_l2(token_emb, mask)
        # after L2 normalize of [2,0], direction is [1,0], norm 1
        assert len(vecs) == 1
        x, y = vecs[0]
        assert x == pytest.approx(1.0)
        assert y == pytest.approx(0.0, abs=1e-6)

    def test_l2_normalized(self):
        token_emb = [[[3.0, 4.0]]]
        mask = [[1]]
        (vec,) = _mean_pool_l2(token_emb, mask)
        norm = (vec[0] ** 2 + vec[1] ** 2) ** 0.5
        assert norm == pytest.approx(1.0)

    def test_all_pad_returns_zeros(self):
        token_emb = [[[0.0, 0.0], [0.0, 0.0]]]
        mask = [[0, 0]]
        (vec,) = _mean_pool_l2(token_emb, mask)
        assert vec == [0.0, 0.0]


class TestRouting:
    def test_default_still_fake(self):
        assert isinstance(load_embedding_client({}), FakeEmbeddingClient)
        assert isinstance(load_embedding_client(None), FakeEmbeddingClient)

    def test_api_key_still_siliconflow(self):
        client = load_embedding_client({'api_key': 'sk-test', 'api_url': 'https://test.api'})
        assert isinstance(client, SiliconFlowEmbeddingClient)

    def test_local_backend_without_model_dir_fails_loud(self, monkeypatch, tmp_path):
        # An empty dir means "no model installed" -> must raise, not silently fake.
        monkeypatch.setenv('MIDNIGHT_MODEL_DIR', str(tmp_path))
        with pytest.raises(ValueError):
            load_embedding_client({'backend': 'local'})


# ---------------------------------------------------------------------------
# Adversarial edge-case tests for LocalOnnxEmbeddingClient.embed, using a
# hand-rolled tokenizer + a fake onnxruntime session so they run offline/fast
# (no 2GB model download needed).
# ---------------------------------------------------------------------------

class _FakeSess:
    last_seq_len = None
    hidden = 1024

    def __init__(self, path=None):
        self.path = path

    def get_inputs(self):
        return [_Simple('input_ids'), _Simple('attention_mask')]

    def run(self, outputs, feed):
        import numpy as np
        ids = feed['input_ids']
        mask = feed['attention_mask']
        _FakeSess.last_seq_len = int(ids.shape[1])
        out = np.zeros((ids.shape[0], ids.shape[1], _FakeSess.hidden), np.float32)
        out[..., 0] = mask.astype(np.float32)  # signal only on non-pad tokens
        return [out]


class _Simple:
    def __init__(self, name):
        self.name = name


class _FakeOnnxRuntime:
    @staticmethod
    def InferenceSession(*args, **kwargs):
        return _FakeSess()


class TestLocalOnnxAdversarial:
    @staticmethod
    def _make(tmp_path, monkeypatch, dim=1024, max_length=8192):
        import sys
        from pathlib import Path
        model_dir = tmp_path
        (model_dir / 'model.onnx').write_bytes(b'dummy-graph')
        (model_dir / 'tokenizer.json').write_bytes(
            Path(_fake_tokenizer(tmp_path)).read_bytes())
        monkeypatch.setitem(sys.modules, 'onnxruntime', _FakeOnnxRuntime())
        _FakeSess.last_seq_len = None
        return LocalOnnxEmbeddingClient(
            dimension=dim, model_dir=str(model_dir), max_length=max_length)

    def test_truncates_to_max_length(self, tmp_path, monkeypatch):
        c = self._make(tmp_path, monkeypatch, max_length=4)
        c.embed(['a a a a a a a a a a'])      # 10 tokens -> clamped to 4
        assert _FakeSess.last_seq_len == 4

    def test_no_truncation_within_limit(self, tmp_path, monkeypatch):
        c = self._make(tmp_path, monkeypatch, max_length=8192)
        c.embed(['a a'])
        assert _FakeSess.last_seq_len == 2

    def test_empty_list_returns_empty(self, tmp_path, monkeypatch):
        c = self._make(tmp_path, monkeypatch)
        assert c.embed([]) == []

    def test_empty_string_returns_zero_vector(self, tmp_path, monkeypatch):
        c = self._make(tmp_path, monkeypatch)
        vecs = c.embed([''])
        assert len(vecs) == 1 and len(vecs[0]) == 1024
        assert all(v == 0.0 for v in vecs[0])

    def test_mixed_lengths_pad_to_longest(self, tmp_path, monkeypatch):
        c = self._make(tmp_path, monkeypatch)
        vecs = c.embed(['a', 'a a a'])
        assert len(vecs) == 2 and all(len(v) == 1024 for v in vecs)
        assert _FakeSess.last_seq_len == 3

    def test_idempotent_deterministic(self, tmp_path, monkeypatch):
        c = self._make(tmp_path, monkeypatch)
        v1 = c.embed(['a b c'])
        v2 = c.embed(['a b c'])
        assert v1 == v2

    def test_padding_does_not_bleed_signal(self, tmp_path, monkeypatch):
        # A short row ('a') padded to a longer neighbour ('a a a') must NOT average
        # the pad (mask=0) columns into its mean. If pad columns were wrongly
        # counted, the short row's mean would drop to ~1/3. Masking keeps it at 1.0.
        c = self._make(tmp_path, monkeypatch)
        vecs = c.embed(['a', 'a a a'])
        short, long_ = vecs
        assert len(short) == 1024 and len(long_) == 1024
        assert abs(short[0] - 1.0) < 1e-6   # pads excluded from the mean
        assert abs(long_[0] - 1.0) < 1e-6   # all real tokens -> still 1.0