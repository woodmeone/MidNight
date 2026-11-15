"""Boot manifest — 开机清单（Issue #9）。

智能体开机那一下应该看见两件事：**我是谁** + **我有哪些长期内容**。

长期内容 = 智能体自己判断值得长期保留、下次能直接拿来用的东西
（四特征：自己判断 / 长期保留 / 能复用 / 会增删改）。
它不是数据库里的行，是工作区里的目录——所以这里只**扫**，不查库。

三级加载的第一级就由本模块产出：

    ① 一行类目（这里）  →  ② LONGTERM.md（智能体自己写）  →  ③ 具体文件

**不设字数上限，不裁剪。** 类目有几类列几类——挤了智能体自己会看到，
自己会合并。唯一例外是超过 HINT_THRESHOLD 时在末尾追加一行提醒（内容不动）。

CLI:
    python boot.py --identity NAME [--workspace PATH]
"""
import json
import os
import re
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from embedding 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用
from scripts.config import get_agent_dir  # noqa: E402
from scripts.self_model import read_self  # noqa: E402

# 长期内容总索引的默认文件名。智能体自己写，这里只负责把路径亮出来。
INDEX_FILENAME = 'LONGTERM.md'

# 超过这个字数就追加一行提醒——**只提醒，不裁剪**。
# 这是镜子，不是闸门：取舍权在智能体手里。
HINT_THRESHOLD = 2000

# Issue #16：paths 在开机清单里的**固定占位串**。
# 只承担「提醒有这两条路」的职责；具体去哪、问谁，读 self.md。
PATHS_HINT = '路径:先查技能库·有事问同伴'

# 第二行的缩进。中文是双宽，视觉上永远差一点，别去调对齐。
_INDENT = ' ' * 10


def scan_longterm(roots: list) -> dict:
    """扫长期内容根。返回 {'categories','index_file','root','unavailable'}。

    规则（见 Issue #9「扫描算法」）：
      - root 不存在 → 进 unavailable
      - root 下有 INDEX_FILENAME → 记第一个
      - root 的**直接子目录**各算一个类目，计数 = 其下递归文件数
      - root 直接放的散文件**不计入类目**（只能靠索引被发现）
      - `.` 开头的隐藏目录/文件跳过
      - categories 按 key 升序，保证确定性

    `index_file` 是**相对 root 的裸文件名**（Issue #14）：绝对路径会被智能体
    照抄进自己的索引，工作区一搬家就全断。绝对路径只放在 `root` 里当定位信息。
    """
    categories: dict = {}
    index_file = None
    index_root = None
    unavailable: list = []

    for root in roots or []:
        if not root or not os.path.isdir(root):
            if root:
                unavailable.append(root)
            continue

        candidate = os.path.join(root, INDEX_FILENAME)
        if index_file is None and os.path.isfile(candidate):
            index_file = INDEX_FILENAME        # 相对，不是绝对
            index_root = root

        for name in sorted(os.listdir(root)):
            if name.startswith('.'):
                continue
            sub = os.path.join(root, name)
            if not os.path.isdir(sub):
                continue
            count = 0
            for _dirpath, dirnames, filenames in os.walk(sub):
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                count += len([f for f in filenames if not f.startswith('.')])
            categories[name] = categories.get(name, 0) + count

    return {
        'categories': {k: categories[k] for k in sorted(categories)},
        'index_file': index_file,
        'root': index_root,
        'unavailable': unavailable,
    }


def _identity_parts(identity: str) -> list:
    """人设段的各个片段（供清单与 --show-paths 共用，避免两处漂移）。"""
    data = read_self(identity) or {}
    name = data.get('name') or identity
    mutable = data.get('mutable') or {}

    parts = [f'[开机] 我是{name}']
    if mutable.get('persona_style'):
        parts.append(mutable['persona_style'])
    if mutable.get('boundary'):
        parts.append(f"边界:{mutable['boundary']}")
    # Issue #16：paths 已写进 self.md 却从没显示出来，等于没写。
    # 这里只放**固定占位串**，不展开内容——paths 是长句（还可能带路径），
    # 动态截取必产出半句。细节让它自己去 read self.md。
    if mutable.get('paths'):
        parts.append(PATHS_HINT)
    return parts


def _render_identity(identity: str) -> str:
    """第一块：`[开机] 我是{name}｜{style}｜边界:{boundary}｜{paths 占位}`。

    缺失的段整段省略（连 `｜` 一起），不留空分隔符。
    self.md 不存在时降级为 `[开机] 我是{identity}`，不报错。
    """
    return '｜'.join(_identity_parts(identity))


def _render_longterm(scan: dict) -> str:
    """第二块：三种情形（不可用 / 无 / 有类目）。

    索引路径写成**相对**（Issue #14），绝对路径只出现在「根」那句里当定位。
    这样智能体照抄进自己索引的，是 `LONGTERM.md` 而不是 `D:\\...\\LONGTERM.md`。
    """
    categories = scan.get('categories') or {}
    index_file = scan.get('index_file')
    root = scan.get('root')

    if not categories:
        unavailable = scan.get('unavailable') or []
        if unavailable:
            return f'长期内容  不可用（{unavailable[0]} 不存在）'
        if index_file:
            # 没有类目目录，但有索引——索引不能丢，条目可能都在根下
            location = f'（根 {root}）' if root else ''
            return f'长期内容  无类目\n{_INDENT}→ {index_file}{location}'
        return '长期内容  无'

    joined = ' · '.join(f'{name} {count}' for name, count in categories.items())
    lines = [f'长期内容  {joined}']
    if index_file:
        location = f'（根 {root}）' if root else ''
        lines.append(f'{_INDENT}→ {index_file}{location}')
    return '\n'.join(lines)


# --- Issue #14：索引里的路径检查 -----------------------------------------
#
# 检查只报不改：改不改是智能体自己的决定。
#
# **核心区分**（这条比「有没有绝对路径」重要得多）：
#
#   - 指向 root **内部**却写成绝对 → **错误**，必须改成相对（这才是搬机器会断的）
#   - 指向 root **外部**的绝对路径   → **提示**，当前写法是对的（另一个盘没法写相对），
#                                      只是迁移后需要重新指路
#
# 只按「有绝对路径」一刀切会误伤「外部真源指路」——那种索引一旦被当成噪音，
# 检查器就会被无视。
_CJK = re.compile(r'[\u4e00-\u9fff]')
# Windows 盘符：D:\... 或 C:/...
_WIN_TOKEN = re.compile(r'[A-Za-z]:[\\/][^\s`\'"|)\]}，。、；：]*')
# `~/...`——可移植写法，但归一后若落在 agent 目录内仍属「该修」
_TILDE_TOKEN = re.compile(r'~[\\/][^\s`\'"|)\]}，。、；：]*')
# POSIX 绝对：**必须有左边界**（行首/空白/反引号/括号），且至少两段。
# 没有左边界就会把 `new/list/...` 这类正文斜杠当成路径。
_POSIX_TOKEN = re.compile(
    r'(?:^|[\s`(\[{|,，])/(?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]+/?')


def _abs_tokens(line: str) -> list:
    """从一行里抠出绝对路径候选。宁缺勿滥——正文里的斜杠不算。"""
    tokens = []
    for pat in (_WIN_TOKEN, _TILDE_TOKEN, _POSIX_TOKEN):
        for m in pat.finditer(line):
            token = m.group(0).strip()
            # 去掉可能被一起吞掉的前导边界字符
            token = token.lstrip('`([{|,，').strip()
            token = token.rstrip('.,;:）)】]，。、；：')
            if token.startswith('file://'):
                token = token[len('file://'):]
            if not token or _CJK.search(token):
                continue
            if token.startswith('/') and token.count('/') < 2:
                continue
            if token not in tokens:
                tokens.append(token)
    return tokens


def _is_inside(path: str, root: str) -> bool:
    """判断绝对路径是否落在 root 之内。"""
    try:
        p = os.path.normcase(os.path.abspath(path))
        r = os.path.normcase(os.path.abspath(root))
    except (ValueError, OSError):
        return False
    return p == r or p.startswith(r + os.sep)


# --- Issue #15：路径可移植性三级判据 -------------------------------------
#
# 实测 12 个 agent 共 30 处绝对路径，其中 self.md 占 20 处——#10 加了 paths
# 之后，智能体照着自己机器的样子填的。发现不是两档而是三档：
#
#   inside   跟着 agent 目录搬 → 必断 → 写相对
#   home     跟着用户账户搬   → 换用户名就断 → 写 ~/
#   external 跟着别的项目走   → 只能绝对 → 标注即可
#
# 判据一句话：**这段路径跟着谁搬家？**


def classify_path(path: str, agent_dir: str) -> str | None:
    """返回 'inside' | 'home' | 'external' | None（不需要判级）。

    **已经是 `~/` 写法的直接返回 None**——它本来就跟着账户走，是可移植的，
    报出来只会制造噪音（实测里 `~/.agents/skills` 被误报成「可改进」）。
    """
    if not path:
        return None
    text = str(path).strip().strip('`\'"')
    if not text:
        return None

    if text.startswith('~'):
        # 唯一例外：`~/` 之后仍落在 agent 目录内（罕见但可能）
        expanded = os.path.expanduser(text)
        return 'inside' if _is_inside(expanded, agent_dir) else None

    if not os.path.isabs(text):
        return None

    if _is_inside(text, agent_dir):
        return 'inside'

    home = os.path.expanduser('~')
    if home and os.path.isabs(home) and _is_inside(text, home):
        return 'home'

    return 'external'


def _suggest(path: str, kind: str, agent_dir: str) -> str:
    """给一条「该改成什么」的建议。"""
    if kind == 'inside':
        try:
            rel = os.path.relpath(os.path.expanduser(path), agent_dir)
            if not rel.startswith('..'):
                return rel.replace('\\', '/')
        except ValueError:
            pass
        return '相对 agent 目录（它会跟着搬）'
    if kind == 'home':
        home = os.path.expanduser('~')
        try:
            rel = os.path.relpath(os.path.expanduser(path), home)
            if not rel.startswith('..'):
                return '~/' + rel.replace('\\', '/')
        except ValueError:
            pass
        return '~/...'
    return '保留绝对，但标注为外部真源'


def _strings_in(obj) -> list:
    """递归取出 JSON 结构里所有字符串（列表/字典/标量都吃）。"""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, list):
        out = []
        for item in obj:
            out.extend(_strings_in(item))
        return out
    if isinstance(obj, dict):
        out = []
        for value in obj.values():
            out.extend(_strings_in(value))
        return out
    return []


def _norm_key(path: str) -> str:
    """归一化用于去重：去掉多余反斜杠转义，统一大小写（Windows）。"""
    text = str(path).strip()
    while '\\\\' in text:
        text = text.replace('\\\\', '\\')
    return os.path.normcase(text.replace('\\', '/').rstrip('/'))


def check_portability(agent: str) -> list:
    """体检一个 agent 的三处载体：self.md / agent.json / LONGTERM.md。

    finding = {'source','line','path','kind','suggest'}
    只读，不改任何文件。

    去重键是**归一化后的路径**：self.md 的 mutable 是 JSON，同一段路径
    在原文里是双反斜杠、在解析后是单反斜杠，不归一会重复计数。
    """
    agent_dir = get_agent_dir(agent)
    findings = []
    seen = set()

    def _add(source: str, lineno: int, token: str):
        token = token.strip()
        if not token:
            return
        kind = classify_path(token, agent_dir)
        if kind is None:
            return
        key = _norm_key(token)
        if key in seen:
            return
        seen.add(key)
        findings.append({'source': source, 'line': lineno, 'path': token,
                         'kind': kind,
                         'suggest': _suggest(token, kind, agent_dir)})

    # 1) self.md —— 先取 mutable（解析后的值，转义已还原），再扫正文
    self_path = os.path.join(agent_dir, 'self.md')
    if os.path.isfile(self_path):
        data = read_self(agent) or {}
        for value in _strings_in(data.get('mutable') or {}):
            for token in _abs_tokens(value):
                _add('self.md', 0, token)
        try:
            text = open(self_path, encoding='utf-8', errors='replace').read()
        except OSError:
            text = ''
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in _abs_tokens(line):
                _add('self.md', lineno, token)

    # 2) agent.json
    meta_path = os.path.join(agent_dir, 'agent.json')
    if os.path.isfile(meta_path):
        try:
            text = open(meta_path, encoding='utf-8', errors='replace').read()
        except OSError:
            text = ''
        try:
            meta = json.loads(text)
        except (ValueError, TypeError):
            meta = {}
        for value in _strings_in(meta):
            for token in _abs_tokens(value):
                _add('agent.json', 0, token)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in _abs_tokens(line):
                _add('agent.json', lineno, token)

    # 3) LONGTERM.md
    index = os.path.join(agent_dir, 'longterm', INDEX_FILENAME)
    if os.path.isfile(index):
        try:
            text = open(index, encoding='utf-8', errors='replace').read()
        except OSError:
            text = ''
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in _abs_tokens(line):
                _add('LONGTERM.md', lineno, token)

    return findings


def check_index_paths(root: str) -> list | None:
    """扫 root 下 LONGTERM.md 里的绝对路径。返回 findings 或 None（无索引文件）。

    finding = {'line': int, 'text': str, 'path': str, 'kind': 'inside'|'outside'}
      - kind='inside'  → 指向 root 内却写成绝对，**必须改成相对**
      - kind='outside' → 指向 root 外的外部真源，当前写法合理，迁移后需重指
    """
    index = os.path.join(root, INDEX_FILENAME)
    if not os.path.isfile(index):
        return None

    findings = []
    with open(index, 'r', encoding='utf-8', errors='replace') as f:
        for lineno, line in enumerate(f, start=1):
            for token in _abs_tokens(line):
                findings.append({
                    'line': lineno,
                    'text': line.strip(),
                    'path': token,
                    'kind': 'inside' if _is_inside(token, root) else 'outside',
                })
    return findings


_KIND_LABEL = {
    'inside': ('✗', '该修', '指向自己却写绝对，搬机器必断'),
    'home': ('⚠', '可改进', '在用户目录下，写 ~/ 就能搬'),
    'external': ('ℹ', '外部真源', '当前只能绝对，迁移后重指'),
}


def _report_portability(agent: str) -> tuple:
    """返回 (输出文本, 是否有该修的)。该修 = inside 或 home。"""
    findings = check_portability(agent)
    if not findings:
        return f'[路径体检] @{agent} 未发现绝对路径。', False

    counts = {'inside': 0, 'home': 0, 'external': 0}
    for f in findings:
        counts[f['kind']] += 1

    lines = [f'[路径体检] @{agent}']
    for kind in ('inside', 'home', 'external'):
        group = [f for f in findings if f['kind'] == kind]
        if not group:
            continue
        icon, label, why = _KIND_LABEL[kind]
        lines.append(f'  {icon} {len(group)} 处{label}（{why}）')
        for item in group:
            where = f"{item['source']}"
            if item['line']:
                where += f" 第 {item['line']} 行"
            lines.append(f'    {where}  {item["path"]}')
            lines.append(f'    → {item["suggest"]}')

    total = len(findings)
    must_fix = counts['inside'] + counts['home']
    lines.append('')
    lines.append(f'共 {total} 处：该修 {counts["inside"]} · '
                 f'可改进 {counts["home"]} · 外部 {counts["external"]}')
    return '\n'.join(lines), must_fix > 0


def compile_boot_manifest(identity: str, workspace: str = None) -> str:
    """编译开机清单。返回可直接注入上下文的文本块（含末尾换行）。

    工作区优先：`--workspace` 的索引文件先被找到。
    """
    roots = [os.path.join(get_agent_dir(identity), 'longterm')]
    if workspace:
        roots.insert(0, workspace)

    text = _render_identity(identity) + '\n\n' + _render_longterm(scan_longterm(roots))

    if len(text) > HINT_THRESHOLD:
        # 只追加，不改内容。裁剪是另一种错。
        text += (f'\n（这份清单已占约 {len(text)} 字。'
                 f'token 和上下文都很宝贵——考虑合并或退休几项。）')
    return text + '\n'


def main(argv=None) -> int:
    """CLI: python boot.py --identity NAME [--workspace PATH] [--check [--strict]]"""
    argv = argv if argv is not None else sys.argv[1:]
    identity = None
    workspace = None
    check = False
    strict = False
    show_paths = False
    check_all = False

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--identity' and i + 1 < len(argv):
            identity = argv[i + 1]; i += 2
        elif arg == '--workspace' and i + 1 < len(argv):
            workspace = argv[i + 1]; i += 2
        elif arg == '--check':
            check = True; i += 1
        elif arg == '--strict':
            strict = True; i += 1
        elif arg == '--all':
            check_all = True; i += 1
        elif arg == '--show-paths':
            show_paths = True; i += 1
        else:
            print(f'Unknown option: {arg}', file=sys.stderr)
            return 2

    if check_all:
        check = True                      # --all 隐含 --check

    if not identity and not check_all:
        print('Usage: boot.py --identity NAME [--workspace PATH] '
              '[--check [--strict] [--all]] [--show-paths]', file=sys.stderr)
        return 2

    if show_paths:
        # 展开 paths 全文——只给调试/体检用，不进开机清单（会占上下文）。
        paths = (read_self(identity) or {}).get('mutable', {}).get('paths')
        if not paths:
            print('[路径] 未设置。可用 self_model.py --add-paths 补上。')
            return 0
        items = paths if isinstance(paths, list) else [paths]
        print('[路径] self.md 里的 paths 全文：')
        for item in items:
            print(f'  - {item}')
        return 0

    if check:
        if check_all:
            from scripts.config import list_agents
            names = [a['name'] for a in list_agents()]
        else:
            names = [identity]
        has_issue = False
        blocks = []
        for name in names:
            text, issue = _report_portability(name)
            blocks.append(text)
            has_issue = has_issue or issue
        print('\n\n'.join(blocks))
        return 1 if (strict and has_issue) else 0

    print(compile_boot_manifest(identity, workspace=workspace), end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
