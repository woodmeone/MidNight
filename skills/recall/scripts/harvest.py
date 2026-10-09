"""拉取式沉淀（harvest）：AI Coding 工具落盘会话摘要 → recall 日记。

定位：手写日记是主动渠道，本模块只做**补充**——把工具自动留下的
"精华"（intent/outcome/learned）沉淀成遵守日记协议的日记，让联想
召回能命中手写没记的基础设施决策与踩坑经验。

为什么是拉取式：Trae 等工具的会话摘要是 IDE 内部压缩上下文时自动
落盘的（trigger=auto），不暴露生命周期 hook，推送式没有抓手；但只
要它"在磁盘留痕"，我们就能定时/手动扫盘取件。对方无需配合任何东西。

扩展方式：一个转换内核（parse→record_to_diary→水位线→ingest）+
每工具一个薄适配器（只回答"文件在哪、怎么解析"）。新增工具只加适
配器，不动内核。

转换时强制遵守既有日记协议：
- 一事一记：一条摘要记录 = 一篇日记（Trae 侧已按话题压缩，粒度可接受）
- created 取真：用 message_summary_time，严禁臆造
- tags 只进 frontmatter：技术锚点（ASCII 词）+ CJK 高频 2-gram
- 信息密度：learned 与 outcome 均空的记录视为低价值，跳过
- 可溯源：正文出处行带 message_id

用法：
    python harvest.py --agent qinglan --dry-run          # 干跑看样例
    python harvest.py --agent qinglan                    # 增量导入
"""
import glob
import json
import os
import re
import sys
from collections import Counter

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))

from scripts.config import get_db_path, get_dailynote_path, get_agent_dir, ensure_agent  # noqa: E402
from scripts.ingest import ingest_file  # noqa: E402

DEFAULT_TRAE_ROOT = os.path.expanduser("~/.trae-cn/memory")
MAX_TAGS = 6
MAX_DIARY_CHARS = 2000  # 单篇上限：拉取式是补充渠道，不配撑爆召回预算

# ASCII 技术锚点：字母开头、含 . _ - 的 ≥3 字符串（bge-m3、tokenizer.json…）
_ASCII_TOKEN = re.compile(r'[A-Za-z][A-Za-z0-9._-]{2,}')
# CJK 连续段（用于 2-gram 词频）
_CJK_RUN = re.compile(r'[\u4e00-\u9fff]+')

# 泛词停用：进标签没有区分度
_STOP = {
    'the', 'and', 'for', 'with', 'this', 'that', 'from', 'have', 'not',
    'user', 'agent', 'test', 'tests', 'code', 'file', 'files', 'json',
    'md', 'py', 'com', 'www', 'https', 'http', 'api', 'xxx', 'TODO',
    'python', 'windows', 'error', 'true', 'false', 'none',
}


def parse_trae_record(line):
    """一行 jsonl → 规范化记录 dict；畸形/缺字段/低价值 → None（跳过不崩）。"""
    line = (line or '').strip()
    if not line:
        return None
    try:
        d = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    mid = d.get('message_id')
    when = d.get('message_summary_time')
    intent = d.get('intent')
    if not mid or not when or not intent:
        return None
    learned_raw = d.get('learned')
    if not isinstance(learned_raw, list):
        learned_raw = []  # 类型错乱（字符串/None/dict）→ 视为无 learned，不逐字迭代
    learned = [s for s in learned_raw if isinstance(s, str) and s.strip()]
    outcome_raw = d.get('outcome')
    outcome = outcome_raw.strip() if isinstance(outcome_raw, str) else ''
    if not learned and not outcome:
        return None  # 精华缺失 → 低价值，不采
    actions_raw = d.get('actions')
    if not isinstance(actions_raw, list):
        actions_raw = []
    return {
        'message_id': str(mid),
        'when': str(when),
        'intent': str(intent),
        'actions': [str(a) for a in actions_raw if isinstance(a, str)],
        'outcome': outcome,
        'learned': learned,
    }


def _extract_tags(rec):
    """frontmatter tags：ASCII 锚点 top + CJK 高频 2-gram top，总数 ≤ MAX_TAGS。"""
    text = ' '.join([rec['intent'], rec['outcome']] + rec['learned'])
    ascii_counts = Counter(
        t for t in _ASCII_TOKEN.findall(text)
        if t.lower() not in _STOP and not t.isdigit()
    )
    bigram_counts = Counter()
    for run in _CJK_RUN.findall(text):
        for i in range(len(run) - 1):
            bigram_counts[run[i:i + 2]] += 1
    tags = []
    for t, _ in ascii_counts.most_common(3):
        # 点号转连字符：parse_diary 按 \w- 提取会把 SKILL.md 拆成 SKILL+md，
        # 两条含 .md 的锚点就会撞出重复标签（md, md）
        t = t.replace('.', '-')
        if t not in tags:
            tags.append(t)
    for t, c in bigram_counts.most_common(6):
        if c >= 2 and t not in tags:
            tags.append(t)
        if len(tags) >= MAX_TAGS:
            break
    # parse_diary 的点号会拆词（SKILL.md→md），两条文件名可撞出同名 tag；此处再去重保序
    deduped = []
    for t in tags:
        if t not in deduped:
            deduped.append(t)
    return deduped[:MAX_TAGS]


def _iso_time(when):
    """'2026-09-08 16:51:17' → '2026-09-08T16:51:17'（取真时间，不臆造）。"""
    m = re.match(r'(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})', when)
    if m:
        return f'{m.group(1)}T{m.group(2)}'
    return when


def record_to_diary(rec, agent='default'):
    """记录 → (确定性文件名, 日记全文)。同记录必同名 → 幂等重跑的前提。"""
    iso = _iso_time(rec['when'])
    date = iso[:10].replace('-', '')
    # 文件名注入对抗：message_id 只留安全字符
    safe_mid = re.sub(r'[^A-Za-z0-9_-]', '', rec['message_id'])[:12] or 'x'
    name = f'harvest_{date}_{safe_mid}.md'
    tags = _extract_tags(rec)
    lines = [
        '---',
        f'maid: {agent}',
        f'created: {iso}',
        'importance: low',  # 补充渠道：召回权重天然低于手写（medium/high）
        f'tags: [{", ".join(tags)}]',
        '---',
        f'核心概念：{rec["intent"]}。',
    ]
    if rec['actions']:
        lines.append('关键经过：' + '；'.join(rec['actions']) + '。')
    if rec['outcome']:
        lines.append(f'结果：{rec["outcome"]}。')
    if rec['learned']:
        lines.append('反思与洞察：')
        lines.extend(f'- {s}' for s in rec['learned'])
    lines.append(f'信源/出处：Trae 会话摘要 message_id={rec["message_id"]}（拉取式沉淀，非手写）。')
    content = '\n'.join(lines) + '\n'
    if len(content) > MAX_DIARY_CHARS:
        suffix = '\n（截断：原文超出单篇上限）\n'
        content = content[:MAX_DIARY_CHARS - len(suffix)].rstrip() + suffix
    return name, content


def _load_state(state_path):
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                return set(json.load(f).get('seen', []))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _save_state(state_path, seen):
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump({'seen': sorted(seen)}, f, ensure_ascii=False, indent=1)


def iter_trae_records(root, project_filter=None):
    """扫 <root>/projects/*/*/session_memory_*.jsonl，逐行产出规范化记录。

    会话粒度去重：同一 message_id 只取首条（防重跑间格式漂移产生重复）。
    project_filter：只取项目目录名含该子串的（作用域控制，避免跨域污染标签网）。
    """
    pattern = os.path.join(root, 'projects', '*', '*', 'session_memory_*.jsonl')
    seen_ids = set()
    for fp in sorted(glob.glob(pattern)):
        if project_filter and project_filter not in fp:
            continue
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                for line in f:
                    rec = parse_trae_record(line)
                    if not rec or rec['message_id'] in seen_ids:
                        continue
                    seen_ids.add(rec['message_id'])
                    yield rec
        except OSError:
            continue


def harvest_trae(root=DEFAULT_TRAE_ROOT, agent=None, dry_run=True,
                 state_path=None, diary_dir=None, db_path=None, client=None,
                 project_filter=None):
    """拉取式主流程：扫描 → 水位线去重 → 生成日记 → 入库 → 更新水位线。

    dry_run=True 时不写任何盘（含 state），只统计与返回样例。
    """
    seen = _load_state(state_path) if state_path else set()
    out = {'candidates': 0, 'written': 0, 'ingested': 0,
           'skipped_seen': 0, 'samples': []}

    for rec in iter_trae_records(root, project_filter=project_filter):
        out['candidates'] += 1
        if rec['message_id'] in seen:
            out['skipped_seen'] += 1
            continue
        name, content = record_to_diary(rec, agent=agent or 'default')
        if dry_run:
            out['samples'].append({'file': name, 'content': content})
            continue
        os.makedirs(diary_dir, exist_ok=True)
        fp = os.path.join(diary_dir, name)
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(content)
        out['written'] += 1
        r = ingest_file(fp, db_path, client)
        if r['status'] == 'ingested':
            out['ingested'] += 1
        seen.add(rec['message_id'])
        _save_state(state_path, seen)
    return out


def main(argv=None) -> int:
    """CLI: python harvest.py --agent NAME [--adapter trae] [--root PATH] [--dry-run]"""
    argv = argv if argv is not None else sys.argv[1:]
    agent = None
    adapter = 'trae'
    root = None
    project = None
    dry_run = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--agent' and i + 1 < len(argv):
            agent = argv[i + 1]; i += 2
        elif a == '--adapter' and i + 1 < len(argv):
            adapter = argv[i + 1]; i += 2
        elif a == '--root' and i + 1 < len(argv):
            root = argv[i + 1]; i += 2
        elif a == '--project' and i + 1 < len(argv):
            project = argv[i + 1]; i += 2
        elif a == '--dry-run':
            dry_run = True; i += 1
        else:
            print(f'Unknown option: {a}', file=sys.stderr)
            return 2

    # 记忆隔离硬约束：读写必须显式指定 agent，禁止默认兜底
    agent = agent or os.environ.get('MIDNIGHT_AGENT')
    if not agent:
        print('必须显式指定 --agent（记忆隔离硬约束）', file=sys.stderr)
        return 2
    if adapter != 'trae':
        print(f'暂不支持的适配器: {adapter}（当前只有 trae）', file=sys.stderr)
        return 2

    ensure_agent(agent)
    root = root or DEFAULT_TRAE_ROOT
    state_path = os.path.join(get_agent_dir(agent), 'harvest_state.json')
    diary_dir = get_dailynote_path(agent)
    db_path = get_db_path(agent)

    client = None
    if not dry_run:
        from embedding import load_embedding_client
        client = load_embedding_client({'api_key': os.environ.get('SILICONFLOW_API_KEY', ''),
                                        'dimension': 1024})

    out = harvest_trae(root=root, agent=agent, dry_run=dry_run,
                       state_path=state_path, diary_dir=diary_dir,
                       db_path=db_path, client=client, project_filter=project)
    print(f'[harvest:{adapter}] agent={agent} dry_run={dry_run} '
          f'候选={out["candidates"]} 新写={out["written"]} '
          f'入库={out["ingested"]} 已见跳过={out["skipped_seen"]}')
    if dry_run:
        for s in out['samples'][:3]:
            print('--- 样例', s['file'], '---')
            print(s['content'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
