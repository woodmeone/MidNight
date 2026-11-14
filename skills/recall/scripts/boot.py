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
import os
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

# 第二行的缩进。中文是双宽，视觉上永远差一点，别去调对齐。
_INDENT = ' ' * 10


def scan_longterm(roots: list) -> dict:
    """扫长期内容根。返回 {'categories','index_file','unavailable'}。

    规则（见 Issue #9「扫描算法」）：
      - root 不存在 → 进 unavailable
      - root 下有 INDEX_FILENAME → 记第一个
      - root 的**直接子目录**各算一个类目，计数 = 其下递归文件数
      - root 直接放的散文件**不计入类目**（只能靠索引被发现）
      - `.` 开头的隐藏目录/文件跳过
      - categories 按 key 升序，保证确定性
    """
    categories: dict = {}
    index_file = None
    unavailable: list = []

    for root in roots or []:
        if not root or not os.path.isdir(root):
            if root:
                unavailable.append(root)
            continue

        candidate = os.path.join(root, INDEX_FILENAME)
        if index_file is None and os.path.isfile(candidate):
            index_file = candidate

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
        'unavailable': unavailable,
    }


def _render_identity(identity: str) -> str:
    """第一块：`[开机] 我是{name}｜{style}｜边界:{boundary}`。

    缺失的段整段省略（连 `｜` 一起），不留空分隔符。
    self.md 不存在时降级为 `[开机] 我是{identity}`，不报错。
    """
    data = read_self(identity) or {}
    name = data.get('name') or identity
    mutable = data.get('mutable') or {}
    style = mutable.get('persona_style') or ''
    boundary = mutable.get('boundary') or ''

    parts = [f'[开机] 我是{name}']
    if style:
        parts.append(style)
    if boundary:
        parts.append(f'边界:{boundary}')
    return '｜'.join(parts)


def _render_longterm(scan: dict) -> str:
    """第二块：三种情形（不可用 / 无 / 有类目）。"""
    categories = scan.get('categories') or {}
    index_file = scan.get('index_file')

    if not categories:
        unavailable = scan.get('unavailable') or []
        if unavailable:
            return f'长期内容  不可用（{unavailable[0]} 不存在）'
        return '长期内容  无'

    joined = ' · '.join(f'{name} {count}' for name, count in categories.items())
    lines = [f'长期内容  {joined}']
    if index_file:
        lines.append(f'{_INDENT}→ {index_file}')
    return '\n'.join(lines)


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
    """CLI: python boot.py --identity NAME [--workspace PATH]"""
    argv = argv if argv is not None else sys.argv[1:]
    identity = None
    workspace = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--identity' and i + 1 < len(argv):
            identity = argv[i + 1]; i += 2
        elif arg == '--workspace' and i + 1 < len(argv):
            workspace = argv[i + 1]; i += 2
        else:
            print(f'Unknown option: {arg}', file=sys.stderr)
            return 2

    if not identity:
        print('Usage: boot.py --identity NAME [--workspace PATH]', file=sys.stderr)
        return 2

    print(compile_boot_manifest(identity, workspace=workspace), end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
