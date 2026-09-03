"""Session-start context compiler — light identity digest for midnight-recall.

V2: a new session shouldn't start blank (remember self + current object), but
must NOT stuff the full persona into context like letta does. This module only
compiles an identity digest from self.md's key fields into the first-turn
system/user prompt; everything else is left to associative recall.

身份摘要是**最基础的信息**，可能含关键基础内容，所以**绝不拦腰硬截**——能有多少给多少；
精简靠"只取关键字段"（name / 锚标签 / 可动层）而非字符截断。

CLI:
    python session_start.py [--agent X]
"""
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from scripts.self_model 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用
from scripts.self_model import read_self  # noqa: E402

GUIDANCE_TEXT = (
    "[身份] 首次运行，尚未定位自我。可用 self_model.py --init 创建 self 锚；"
    "或直接告诉我你希望我是什么样的人。其余记忆靠联想召回。"
)


def compile_identity_summary(agent: str = None) -> str:
    """Compile self.md's key fields into an identity digest.

    Only the 定海锚 (name / anchor_tags) plus a 可动层 overview
    (persona_style / capabilities) are included — not the whole self.md.
    不设长度上限、不截断：身份是最基础的，短则尽短，长则完整。
    Returns '' when no self.md exists — callers should fall back to GUIDANCE_TEXT.
    """
    data = read_self(agent)
    if not data or not data.get('name'):
        return ''
    name = data.get('name') or 'midnight-agent'
    anchor_tags = data.get('anchor_tags') or []
    mutable = data.get('mutable') or {}
    persona_style = mutable.get('persona_style') or ''
    capabilities = mutable.get('capabilities') or []
    if isinstance(capabilities, list):
        cap_str = '、'.join(str(c) for c in capabilities)
    else:
        cap_str = str(capabilities)

    parts = [f"我是{name}"]
    if anchor_tags:
        parts.append('锚标签:' + ' '.join(anchor_tags))
    if persona_style:
        parts.append(f"风格:{persona_style}")
    if cap_str:
        parts.append(f"能力:{cap_str}")
    return '；'.join(parts)


def main(argv=None) -> int:
    """CLI: python session_start.py [--agent X]"""
    argv = argv if argv is not None else sys.argv[1:]
    agent = os.environ.get('MIDNIGHT_AGENT')
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--agent' and i + 1 < len(argv):
            agent = argv[i + 1]
            i += 1
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 2
        i += 1

    summary = compile_identity_summary(agent)
    if not summary:
        # 无 self.md：输出引导文案，不报错
        print(GUIDANCE_TEXT)
    else:
        print(f"[身份] {summary}（其余记忆靠联想召回）")
    return 0


if __name__ == '__main__':
    sys.exit(main())
