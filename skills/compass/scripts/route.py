"""Route — semantic model routing for midnight-compass (语义路由).

Inspired by VCP's SemanticModelRouter, original implementation.
Given a query, route it to the most appropriate model/preset based on
semantic similarity against route descriptions.

Config: json file ~/.midnight/compass/config.json
"""
import json
import os
import sys
import sqlite3
import struct
from typing import Optional

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from embedding 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.midnight/compass/config.json")
DEFAULT_DB_PATH = os.path.expanduser("~/.midnight/compass/compass.db")

DEFAULT_CONFIG = {
    "enabled": True,
    "default_model": "deepseek-v4-flash",
    "default_preset": "default",
    "match_threshold": 0.18,
    "context_weights": [0.7, 0.3],
    "presets": {
        "default": {
            "default_model": "deepseek-v4-flash",
            "fallback_models": ["deepseek-v4-pro"],
            "match_threshold": 0.18,
            "routes": [
                {"name": "daily_chat", "model": "deepseek-v4-flash",
                 "description": "日常聊天、闲聊、寒暄、生活琐事、轻松对话、随意问答"},
                {"name": "research_and_coding", "model": "deepseek-v4-pro",
                 "description": "信息调研、代码编写、脚本开发、调试程序、API集成、数据处理"},
                {"name": "deep_reasoning", "model": "deepseek-v4-pro",
                 "description": "复杂推理、深度逻辑分析、形式逻辑、哲学思辨、跨学科推理"},
                {"name": "creative_writing", "model": "deepseek-v4-flash",
                 "description": "创意写作、文案创作、故事编写、诗歌、文案润色"},
                {"name": "memory_operation", "model": "deepseek-v4-flash",
                 "description": "记忆操作、日记写入、标签管理、回忆检索、知识整理"},
            ]
        }
    }
}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Load routing config, create default if not exists. Always returns a fresh dict."""
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def embed_query(query: str, embedding_client) -> list[float]:
    """Embed a query string."""
    return embedding_client.embed([query])[0]


def route(query: str, embedding_client, config_path: str = DEFAULT_CONFIG_PATH,
          preset_name: str = None) -> dict:
    """Route a query to the best model.

    Returns {model, route_name, score, fallback_models, all_routes}
    """
    config = load_config(config_path)
    if not config.get('enabled', True):
        return {'model': config.get('default_model', 'deepseek-v4-flash'),
                'route_name': 'default_disabled', 'score': 1.0,
                'fallback_models': config.get('presets', {}).get('default', {}).get('fallback_models', [])}

    preset_name = preset_name or config.get('default_preset', 'default')
    preset = config.get('presets', {}).get(preset_name, config['presets']['default'])

    query_vec = embed_query(query, embedding_client)
    threshold = preset.get('match_threshold', config.get('match_threshold', 0.18))

    # Score each route
    scored = []
    for route_def in preset.get('routes', []):
        route_vec = embed_query(route_def['description'], embedding_client)
        score = _cosine_similarity(query_vec, route_vec)
        scored.append({
            'name': route_def['name'],
            'model': route_def['model'],
            'description': route_def['description'],
            'score': score,
        })

    # Sort by score desc, filter by threshold
    scored.sort(key=lambda x: x['score'], reverse=True)
    matched = [r for r in scored if r['score'] >= threshold]

    if matched:
        best = matched[0]
        return {
            'model': best['model'],
            'route_name': best['name'],
            'score': round(best['score'], 4),
            'fallback_models': preset.get('fallback_models', []),
            'all_routes': scored,
        }

    # No match above threshold, use default
    return {
        'model': preset.get('default_model', 'deepseek-v4-flash'),
        'route_name': 'default',
        'score': 0.0,
        'fallback_models': preset.get('fallback_models', []),
        'all_routes': scored,
    }


def main(argv=None) -> int:
    """CLI: python route.py --query "..." [--preset NAME] [--config PATH]"""
    argv = argv if argv is not None else sys.argv[1:]

    query = ''
    preset_name = None
    config_path = DEFAULT_CONFIG_PATH

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--query' and i + 1 < len(argv):
            query = argv[i + 1]
            i += 2
        elif arg == '--preset' and i + 1 < len(argv):
            preset_name = argv[i + 1]
            i += 2
        elif arg == '--config' and i + 1 < len(argv):
            config_path = argv[i + 1]
            i += 2
        else:
            print(f"Unknown: {arg}", file=sys.stderr)
            return 2

    if not query:
        print("Usage: route.py --query '...' [--preset NAME] [--config PATH]", file=sys.stderr)
        return 1

    from embedding import FakeEmbeddingClient
    client = FakeEmbeddingClient(dimension=16)
    result = route(query, client, config_path=config_path, preset_name=preset_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())