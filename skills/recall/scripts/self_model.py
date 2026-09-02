"""Self anchor — the agent's identity file (self.md) for midnight-recall.

V2: an agent is an independent individual with a stable identity anchor that
survives session/model switches. self.md separates the 定海锚 (immutable:
name / anchor_tags / self-description) from the 可动层 (mutable:
persona_style / capabilities / position ...) so the identity stays grounded
while still being able to evolve.

CLI:
    python self_model.py --init [--agent X]   # 无 self.md 时自动生成（幂等）
    python self_model.py --show [--agent X]   # 打印当前 self 内容
"""
import json
import os
import re
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from scripts.config 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用
from scripts.config import get_self_path, get_agent_dir  # noqa: E402

# 定海锚字段：mutable_only=True 时不可被 update_self 修改
IMMUTABLE_KEYS = frozenset({'name', 'anchor_tags', 'description'})

DEFAULT_TEMPLATE = {
    'name': 'midnight-agent',
    'anchor_tags': ['midnight'],
    'mutable': {
        'persona_style': '冷静、高效、务实的助手',
        'capabilities': ['记忆', '联想', '执行'],
    },
    'description': '我是 Midnight Skills 的记忆智能体。这是我的身份锚：'
                   '底层身份（自称、身份锚标签、自描述）为定海锚，只读保护；'
                   '偏好/风格/能力边界/立场为可动层，可随经历演化。',
}

_FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', re.DOTALL)


def _parse_list(value: str) -> list[str]:
    """Parse a tag list: 'a, b' or '[a, b]'."""
    value = value.strip()
    if value.startswith('[') and value.endswith(']'):
        value = value[1:-1]
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


def _parse_self(content: str) -> dict:
    """Parse self.md content into {name, anchor_tags, mutable, description}."""
    result = {
        'name': None,
        'anchor_tags': [],
        'mutable': {},
        'description': content.strip(),
    }
    m = _FRONTMATTER_PATTERN.match(content)
    if not m:
        return result
    fm_text, body = m.group(1), m.group(2)
    result['description'] = body.strip()
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, _, value = line.partition(':')
        key = key.strip().lower()
        value = value.strip()
        if key == 'name':
            result['name'] = value
        elif key == 'anchor_tags':
            result['anchor_tags'] = _parse_list(value)
        elif key == 'mutable':
            if value.startswith('{'):
                try:
                    result['mutable'] = json.loads(value)
                except json.JSONDecodeError:
                    result['mutable'] = {}
            else:
                result['mutable'] = {}
    return result


def _serialize_self(data: dict) -> str:
    """Serialize a self dict back to self.md text."""
    name = data.get('name') or DEFAULT_TEMPLATE['name']
    anchor_tags = data.get('anchor_tags') or []
    mutable = data.get('mutable') or {}
    desc = (data.get('description') or '').strip()
    lines = [
        '---',
        f"name: {name}",
        'anchor_tags: [' + ', '.join(anchor_tags) + ']',
        'mutable: ' + json.dumps(mutable, ensure_ascii=False),
        '---',
    ]
    text = '\n'.join(lines)
    return text + ('\n' + desc if desc else '')


def ensure_self(agent: str = None, defaults: dict | None = None) -> dict:
    """Create self.md on first run (idempotent). Returns parsed self dict."""
    path = get_self_path(agent)
    if os.path.exists(path):
        return read_self(agent)
    data = defaults if defaults is not None else DEFAULT_TEMPLATE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_serialize_self(data))
    return dict(data)


def read_self(agent: str = None) -> dict:
    """Read and parse self.md. Returns {} if missing."""
    path = get_self_path(agent)
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return _parse_self(f.read())


def update_self(agent: str = None, patch: dict | None = None,
                mutable_only: bool = True) -> dict:
    """Merge patch into the mutable layer of self.md.

    With mutable_only=True (default), immutable keys (name / anchor_tags /
    description) are rejected and left untouched. Returns
    {'updated': bool, 'rejected': [keys]}.
    """
    patch = patch or {}
    if not os.path.exists(get_self_path(agent)):
        ensure_self(agent)
    data = read_self(agent)
    mutable = dict(data.get('mutable') or {})
    rejected = []
    applied = []
    for key, value in patch.items():
        if mutable_only and key in IMMUTABLE_KEYS:
            rejected.append(key)
            continue
        mutable[key] = value
        applied.append(key)
    data['mutable'] = mutable
    with open(get_self_path(agent), 'w', encoding='utf-8') as f:
        f.write(_serialize_self(data))
    return {'updated': bool(applied), 'rejected': rejected}


def main(argv=None) -> int:
    """CLI: python self_model.py --init [--agent X] | --show [--agent X]"""
    argv = argv if argv is not None else sys.argv[1:]
    agent = os.environ.get('MIDNIGHT_AGENT')
    action = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--init':
            action = 'init'
        elif arg == '--show':
            action = 'show'
        elif arg == '--agent' and i + 1 < len(argv):
            agent = argv[i + 1]
            i += 1
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 2
        i += 1

    if action == 'init':
        data = ensure_self(agent)
        print(json.dumps({'status': 'ok', 'path': get_self_path(agent),
                          'name': data.get('name')}, ensure_ascii=False))
        return 0
    if action == 'show':
        data = read_self(agent)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print("Usage: self_model.py --init [--agent X] | --show [--agent X]", file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
