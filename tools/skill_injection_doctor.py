"""skill_injection_doctor — 诊断「同一个 skill 被注入两遍」的浪费。

## 为什么有这个工具

DSH 的 skill 注入走两条正交的路径：

    skill-filesystem   只供货（发现 SKILL.md），不注入
    tool-skill         注入方（agent/pre-step 两个监听器）

所以「重复注入」的成因**只可能**是 `tool-skill` 被启用了多次。
而 DSH 的配置是分层叠加的：host 层一份，每个 agent preset 各一份。
两处都开 = 两个 listener = 同一份正文注入两遍。

## 两个子命令

    --sessions   扫会话日志，数「同一轮里同名 skill 注入了几次」。
                 >1 即红。这是**判定 bug 存不存在**的硬证据（用户视角症状）。
    --config     读 `dsh --dump-config` 的组合结果，数 `tool-skill` /
                 `skill-filesystem` 在几处被启用。>1 即红。
                 这是**定位成因层**的硬证据（配置视角原因）。

两者独立可跑：`--sessions` 证明症状，`--config` 证明病因。
修完必须两个都转绿才算完 —— 只绿一个说明还没对上号。

## 退出码

    0  绿（无重复）
    1  红（有重复）
    2  参数/环境错误

用法：

    python tools/skill_injection_doctor.py --sessions
    python tools/skill_injection_doctor.py --sessions --limit 20
    python tools/skill_injection_doctor.py --config
    python tools/skill_injection_doctor.py --config --dump-file dump.txt
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import os
import sys

# 目标插件：只关心会「注入」或「供货」skill 的那两个。
INJECTOR = 'tool-skill'
PROVIDER = 'skill-filesystem'

# 会话日志默认位置。可用 --sessions-root 或环境变量覆盖。
DEFAULT_SESSIONS_ROOT = os.path.join(
    os.environ.get('DSH_HOME') or os.path.expanduser('~/.dsh'), 'sessions')


# ---------------------------------------------------------------- sessions 侧

def _iter_session_files(root: str) -> list:
    """会话日志文件列表（v4 格式是 zstd 压缩的 jsonl）。"""
    patterns = ('session*.jsonl.zstd', 'session*.jsonl')
    found = []
    for pat in patterns:
        found.extend(glob.glob(os.path.join(root, '*', '*', pat)))
    return sorted(found)


def _read_lines(path: str) -> list:
    """读一个会话文件的所有行。.zstd 需要 zstandard，没有就跳过并记下。"""
    if path.endswith('.zstd'):
        try:
            import zstandard as zstd
        except ImportError:
            raise RuntimeError(
                'reading .zstd sessions needs the `zstandard` package: '
                'pip install zstandard')
        with open(path, 'rb') as f:
            raw = zstd.ZstdDecompressor().stream_reader(f).read()
    else:
        with open(path, 'rb') as f:
            raw = f.read()
    return raw.decode('utf-8', errors='replace').splitlines()\
        if isinstance(raw, bytes) else raw


def scan_session_file(path: str) -> list:
    """数一个会话里「同一轮同名 skill 注入次数」。

    返回 [{turn, name, count, digest}]，只含 count > 1 的项。
    轮次边界是 `turn/start` 事件；没有该事件的历史文件整体算一轮。
    """
    counter = collections.Counter()
    digests = {}

    def flush(turn: int, out: list):
        for name, count in counter.items():
            if count > 1:
                out.append({'turn': turn, 'name': name, 'count': count,
                            'digest': digests.get(name)})
        counter.clear()
        digests.clear()

    out = []
    turn = 0
    for line in _read_lines(path):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get('type')
        if kind == 'turn/start':
            flush(turn, out)
            turn += 1
            continue
        if kind != 'user/message':
            continue
        data = event.get('data') or {}
        source = data.get('source') or {}
        if source.get('kind') != 'skill-invocation':
            continue
        name = source.get('name')
        if not name:
            continue
        counter[name] += 1
        if name not in digests:
            text = ''.join(block.get('text', '') for block in (data.get('content') or [])
                           if block.get('type') == 'text')
            digests[name] = hashlib.sha256(text.encode('utf-8')).hexdigest()[:10]
    flush(turn, out)
    return out


def report_sessions(root: str, limit: int = 0) -> int:
    """扫会话日志并report。返回退出码。"""
    if not os.path.isdir(root):
        print(f'[config] sessions root 不存在：{root}', file=sys.stderr)
        return 2
    files = _iter_session_files(root)
    if not files:
        print(f'sessions root 下没找到会话日志：{root}', file=sys.stderr)
        return 2

    findings = []
    for path in files:
        try:
            hits = scan_session_file(path)
        except RuntimeError as exc:
            print(f'  跳过 {os.path.basename(path)}：{exc}', file=sys.stderr)
            continue
        for hit in hits:
            hit['session'] = os.path.basename(os.path.dirname(path))
            findings.append(hit)

    scanned = len(files)
    if not findings:
        print(f'[绿] 扫了 {scanned} 个会话，没有同轮重复注入。')
        return 0

    # 按 (name, digest) 聚合，方便看「是不是同一份正文」
    grouped = collections.Counter(
        (f['name'], f['count'], f['digest']) for f in findings)
    print(f'[红] 扫了 {scanned} 个会话，共 {len(findings)} 轮存在同轮重复注入。')
    print()
    print(f'{"skill":<22}{"次数/轮":<10}{"正文指纹":<14}{"涉及轮数":<8}')
    print('-' * 56)
    shown = 0
    for (name, count, digest), rounds in grouped.most_common():
        print(f'{name:<22}{count:<10}{str(digest):<14}{rounds:<8}')
        shown += 1
        if limit and shown >= limit:
            print(f'...（还有 {len(grouped) - shown} 项未列出，--limit 可调）')
            break
    print()
    print('同一个指纹 = 逐字节相同的正文，不是"两次不同内容"。')
    return 1


# ------------------------------------------------------------------ config 侧

def active_preset(text: str) -> str | None:
    """从 dump 里读出当前生效的 agent preset。

    来源是 `agent-preset-registry` 的 `selectedDefault`（缺省回落到 `default`）。
    预设不止一个，但**同一时刻只有一个是 active** —— 不认这一点就会把
    「三个预设各挂一份」误算成「同时注入三份」，报告直接失真。
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != '- id: agent-preset-registry':
            continue
        indent = len(line) - len(line.lstrip())
        for follow in lines[index + 1:index + 12]:
            follow_indent = len(follow) - len(follow.lstrip())
            if follow.strip() and follow_indent <= indent:
                break
            key, _, value = follow.strip().partition(':')
            if key in ('selectedDefault', 'default'):
                value = value.strip()
                if value and value != 'null':
                    return value
    return None


def parse_dump_config(text: str) -> list:
    """从 `dsh --dump-config` 输出里找出目标插件的每条启用记录。

    返回 [{line, id, layer, preset, disabled}]。
    `layer` = 'host'（顶层，无缩进）或 'preset:<名字>'（缩进内）。
    `preset` = 该条目所属预设名，顶层条目为 None。
    """
    records = []
    current_preset = None
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith('- id: '):
            name = line[len('- id: '):].strip()
            if name.startswith('preset-'):
                current_preset = name[len('preset-'):]
            else:
                current_preset = None

        stripped = line.strip()
        if not stripped.startswith('- id: '):
            continue
        entry_id = stripped[len('- id: '):].strip()
        if entry_id not in (INJECTOR, PROVIDER):
            continue

        indent = len(line) - len(line.lstrip())
        is_nested = indent > 0
        records.append({
            'line': index + 1,
            'id': entry_id,
            'layer': f'preset:{current_preset}' if (is_nested and current_preset) else 'host',
            'preset': current_preset if is_nested else None,
            'disabled': _entry_disabled(lines, index, indent),
        })
    return records


def _entry_disabled(lines: list, index: int, indent: int) -> bool:
    """读某条目自己的 `disabled:`。

    缩进规则：`- id:` 的横线在 I，它的键在 I+2，下一个兄弟条目又回到 I。
    所以「本条目的正文」= 缩进 > I 的那些行；第一个正文行的缩进就是键缩进，
    只有正好在键缩进上的 `disabled:` 才算本条目的 —— 嵌套 config 里更深层的
    `disabled:` 不能算。
    """
    key_indent = None
    for follow in lines[index + 1:index + 8]:
        if not follow.strip():
            continue
        follow_indent = len(follow) - len(follow.lstrip())
        if follow_indent <= indent:
            break                       # 兄弟条目或退到父作用域，本条目结束
        if key_indent is None:
            key_indent = follow_indent
        if follow_indent != key_indent:
            continue                    # 嵌套块，跳过
        if follow.strip().startswith('disabled:'):
            return follow.strip().split(':', 1)[1].strip() == 'true'
    return False


def report_config(text: str) -> int:
    """判组合结果里目标插件在**当前生效预设**下被启用了几处。返回退出码。"""
    records = parse_dump_config(text)
    if not records:
        print('[config] 没在 dump 里找到 tool-skill / skill-filesystem。', file=sys.stderr)
        print('  确认 dump 是 `dsh --profile <名字> --dump-config` 的输出。', file=sys.stderr)
        return 2

    active = active_preset(text)
    print(f'当前生效预设：{active or "（没读到 selectedDefault）"}')
    print()

    def effective(record) -> bool:
        """这条在当前生效预设下会不会真的加载。

        host 层总是加载；预设层只有 active 那个才加载。
        """
        if record['preset'] is None:
            return True
        return record['preset'] == active

    print(f'{"行号":<8}{"插件":<18}{"层":<26}{"状态":<10}{"本轮生效":<10}')
    print('-' * 72)
    for r in records:
        state = 'disabled' if r['disabled'] else '启用'
        live = '—' if r['disabled'] else ('是' if effective(r) else '否（非当前预设）')
        print(f'{r["line"]:<8}{r["id"]:<18}{r["layer"]:<26}{state:<10}{live:<10}')
    print()

    ok = True
    live_injectors = [r for r in records
                      if r['id'] == INJECTOR and not r['disabled'] and effective(r)]
    live_providers = [r for r in records
                      if r['id'] == PROVIDER and not r['disabled'] and effective(r)]

    if len(live_injectors) > 1:
        ok = False
        layers = ' + '.join(r['layer'] for r in live_injectors)
        print(f'[红] {INJECTOR} 在当前配置下启用 {len(live_injectors)} 处：{layers}')
        print(f'     → 每个 pre-step listener 注入一遍，同一轮被塞 {len(live_injectors)} 份。')
        n = len(live_injectors)
        print(f'     → 白烧 ≈ {n - 1} 份 SKILL.md 正文。')
    elif not live_injectors:
        ok = False
        print(f'[红] {INJECTOR} 当前一处都没启用 —— skill 工具与目录都不会出现。')
    else:
        print(f'[绿] {INJECTOR} 只在 {live_injectors[0]["layer"]} 启用一次。')

    if len(live_providers) > 1:
        print(f'[提示] {PROVIDER} 也启用 {len(live_providers)} 处 —— '
              f'它不注入（只发现文件），不是本 bug 元凶，但目录扫两遍。')
    return 0 if ok else 1


# ---------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='诊断同一个 skill 被注入两遍的浪费')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--sessions', action='store_true',
                       help='扫会话日志数「同轮同名 skill 注入次数」')
    group.add_argument('--config', action='store_true',
                       help='读 dsh --dump-config 输出，数插件被启用的层数')
    parser.add_argument('--sessions-root', default=DEFAULT_SESSIONS_ROOT,
                        help=f'会话日志根目录（默认 {DEFAULT_SESSIONS_ROOT}）')
    parser.add_argument('--dump-file', default=None,
                        help='--config 时从文件读 dump；缺省从 stdin 读')
    parser.add_argument('--limit', type=int, default=0,
                        help='--sessions 最多列出几项（0 = 全列）')
    args = parser.parse_args(argv)

    if args.sessions:
        return report_sessions(args.sessions_root, limit=args.limit)

    if args.dump_file:
        try:
            with open(args.dump_file, encoding='utf-8') as f:
                text = f.read()
        except OSError as exc:
            print(f'[config] 读不了 {args.dump_file}：{exc}', file=sys.stderr)
            return 2
    else:
        text = sys.stdin.read()
    return report_config(text)


if __name__ == '__main__':
    sys.exit(main())
