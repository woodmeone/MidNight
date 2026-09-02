"""Self-evolution engine — mirror/feedback-driven rewrite of the mutable layer.

V2 (§4.B.5): an agent grows by introspection. Based on new interactions,
research, or mirror feedback, the agent evaluates its self-image and rewrites
the *mutable* layer of self.md. The 定海锚 (name / anchor_tags / description)
is read-only — immutable keys are rejected and never overwritten.

Also houses the "规则不固化" disuse decay (§4.B.4): association weights
(tag_edges / tag_cooccurrence) that haven't been touched in a long time lose
weight, and stale-weak edges are forgotten — instead of freezing rules into a
rules.md file. No schema change: it reuses the existing `updated_at` columns.

CLI:
    python evolution.py --apply --feedback "..." --patch '{json}'
                        [--source user|mirror|research] [--agent X]
    # --set key=value 可重复；点号嵌套 (preferences.cmd=py)、JSON 数组值 ([...])。
    # PowerShell 会剥掉原生参数里的内嵌双引号，故 Windows 上请用 --set。
    python evolution.py --decay [--stale-days 90] [--factor 0.5] [--floor 0.05] [--agent X]
    python evolution.py --log [--agent X]
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from scripts.config 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用
from scripts.config import get_agent_dir, get_self_path, get_db_path  # noqa: E402
from scripts.self_model import read_self, update_self, ensure_self  # noqa: E402

EVOLUTION_LOG_NAME = 'evolution.log'

# 默认久不用衰减参数
DEFAULT_STALE_DAYS = 90
DEFAULT_DECAY_FACTOR = 0.5
DEFAULT_FLOOR = 0.05


def get_evolution_log_path(agent: str = None) -> str:
    """Evolution history file (JSONL) under the agent's data dir."""
    return os.path.join(get_agent_dir(agent), EVOLUTION_LOG_NAME)


def apply_evolution(agent: str = None, feedback: str = '',
                    patch: dict | None = None,
                    source: str = 'user') -> dict:
    """Evaluate & apply an evolution intent to self's mutable layer.

    - No self.md yet → auto-create it first (idempotent default).
    - patch keys in the 定海锚 (name / anchor_tags / description) are rejected
      (update_self(mutable_only=True) enforces this).
    - Every attempt — applied and rejected — is appended to evolution.log.
    Returns {'updated': bool, 'rejected': [keys]}.
    """
    if not os.path.exists(get_self_path(agent)):
        ensure_self(agent)
    result = update_self(agent, patch, mutable_only=True)
    rejected = result['rejected']
    applied_keys = [k for k in (patch or {}) if k not in rejected]
    entry = {
        'ts': datetime.now().isoformat(timespec='seconds'),
        'source': source,
        'feedback': feedback,
        'applied': applied_keys,
        'rejected': rejected,
        'patch': patch or {},
    }
    log_path = get_evolution_log_path(agent)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return {'updated': result['updated'], 'applied': applied_keys, 'rejected': rejected}


def read_evolution_log(agent: str = None) -> list[dict]:
    """Read evolution history, oldest first. Returns [] if none."""
    path = get_evolution_log_path(agent)
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def decay_stale_edges(db_path: str, stale_days: int = DEFAULT_STALE_DAYS,
                      factor: float = DEFAULT_DECAY_FACTOR,
                      floor: float = DEFAULT_FLOOR) -> dict:
    """Decay association weights untouched for `stale_days`.

    Applies to tag_edges and tag_cooccurrence alike (keeps recall consistent).
    Stale weights are multiplied by `factor`; those that then fall below
    `floor` are deleted (stale + weak = forgotten).
    Returns {'decayed': n, 'removed': n}.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        mod = f'-{stale_days} days'
        cur = conn.execute(
            """UPDATE tag_edges SET weight = weight * ?
               WHERE updated_at < datetime('now', ?) AND weight > ?""",
            (factor, mod, 0.0))
        decayed = cur.rowcount
        cur = conn.execute("DELETE FROM tag_edges WHERE weight < ?", (floor,))
        removed = cur.rowcount
        cur = conn.execute(
            """UPDATE tag_cooccurrence SET weight = weight * ?
               WHERE updated_at < datetime('now', ?) AND weight > ?""",
            (factor, mod, 0.0))
        decayed += cur.rowcount
        cur = conn.execute("DELETE FROM tag_cooccurrence WHERE weight < ?", (floor,))
        removed += cur.rowcount
        conn.commit()
        return {'decayed': decayed, 'removed': removed}
    finally:
        conn.close()


def _parse_set_value(raw_value: str) -> object:
    """Parse a --set value: JSON array, or PowerShell-safe bare list [a,b,c]."""
    s = raw_value.strip()
    if s.startswith('[') and s.endswith(']'):
        inner = s[1:-1]
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass
        # PowerShell-safe plain list: [记忆,联想,执行] → ['记忆','联想','执行']
        return [item.strip() for item in inner.split(',') if item.strip()]
    return raw_value


def _build_patch(set_args: list[tuple[str, str]],
                 patch_json: dict | None) -> dict:
    """Merge --patch JSON with repeatable --set key=value into a patch dict.

    --set supports dotted keys for nesting (preferences.cmd=py) and list values
    ([a,b,c] or JSON array). --set wins over --patch on key collision.
    """
    patch = dict(patch_json or {})
    for raw in set_args:
        key, _, raw_value = raw.partition('=')
        key = key.strip()
        if not key:
            continue
        value = _parse_set_value(raw_value)
        parts = key.split('.')
        if len(parts) == 1:
            patch[parts[0]] = value
        else:
            node = patch
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = value
    return patch


def main(argv=None) -> int:
    """CLI: evolution.py --apply|--decay|--log [options] [--agent X]"""
    argv = argv if argv is not None else sys.argv[1:]
    agent = os.environ.get('MIDNIGHT_AGENT')
    action = None
    feedback = ''
    patch = None
    set_args: list[tuple[str, str]] = []
    source = 'user'
    stale_days = DEFAULT_STALE_DAYS
    factor = DEFAULT_DECAY_FACTOR
    floor = DEFAULT_FLOOR

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--apply':
            action = 'apply'
        elif arg == '--decay':
            action = 'decay'
        elif arg == '--log':
            action = 'log'
        elif arg == '--feedback' and i + 1 < len(argv):
            feedback = argv[i + 1]
            i += 1
        elif arg == '--patch' and i + 1 < len(argv):
            patch = json.loads(argv[i + 1])
            i += 1
        elif arg == '--set' and i + 1 < len(argv):
            set_args.append(argv[i + 1])
            i += 1
        elif arg == '--source' and i + 1 < len(argv):
            source = argv[i + 1]
            i += 1
        elif arg == '--stale-days' and i + 1 < len(argv):
            stale_days = int(argv[i + 1])
            i += 1
        elif arg == '--factor' and i + 1 < len(argv):
            factor = float(argv[i + 1])
            i += 1
        elif arg == '--floor' and i + 1 < len(argv):
            floor = float(argv[i + 1])
            i += 1
        elif arg == '--agent' and i + 1 < len(argv):
            agent = argv[i + 1]
            i += 1
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 2
        i += 1

    if action == 'apply':
        patch = _build_patch(set_args, patch)
        result = apply_evolution(agent, feedback=feedback, patch=patch, source=source)
        print(json.dumps({'status': 'ok', **result}, ensure_ascii=False))
        return 0
    if action == 'decay':
        db_path = get_db_path(agent)
        if not os.path.exists(db_path):
            print(json.dumps({'status': 'ok', 'decayed': 0, 'removed': 0}))
            return 0
        result = decay_stale_edges(db_path, stale_days=stale_days, factor=factor, floor=floor)
        print(json.dumps({'status': 'ok', **result}))
        return 0
    if action == 'log':
        print(json.dumps(read_evolution_log(agent), ensure_ascii=False, indent=2))
        return 0

    print(__doc__.strip().splitlines()[-1] or "Usage: evolution.py --apply|--decay|--log", file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
