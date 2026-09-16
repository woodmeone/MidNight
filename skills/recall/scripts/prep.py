"""prep — 可移植的「回复前记忆准备」核心（票4）。

设计目标（Issue #2）：把散在 SKILL.md 提示词 + recall.py CLI 里的召回流程
下沉为**与运行时无关**的纯编排函数 `prep_for_reply`——门控→取 query→联想召回
→去重→MMR 重排→预算收敛→格式化文本。skill 只作薄跳板（CLI），未来迁移到有
hook 的运行时，核心函数一字不改、只换调用入口。

铁律：
- 本模块不 import 任何运行时/框架/hook 代码，只依赖同目录的 recall/embedding/config；
- 不读真实时间做门控——时钟由调用方显式注入（`now`/`last_recall_ts`），保证确定性；
- 不触发写、不改数据——只做"这轮要不要查、查什么、怎么排、塞多少"。
"""
import os
import sys
import time

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from embedding 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用

from embedding import load_embedding_client  # noqa: E402
from scripts.config import get_db_path, ensure_agent  # noqa: E402
from scripts.recall import (  # noqa: E402
    recall_associative, dedupe_results, fit_to_budget, format_recall_output,
)

# 命中即必召回的意图触发词（对齐 SKILL.md「触发条件」表）。
DEFAULT_TRIGGER_WORDS = (
    '记住', '记一下', '还记得', '记得吗', '你记得', '帮我回忆', '回忆',
    '我上次', '上次说', '之前提', '上次聊',
)

# 短于该长度的消息视为寒暄/语气词，默认不召回（除非命中触发词或 force）。
DEFAULT_MIN_LEN = 4

# 同一会话两次召回的最小间隔（秒）；0 表示不做冷却。
DEFAULT_COOLDOWN = 0.0


def should_recall(message: str, now: float = None, last_recall_ts: float = None,
                  cooldown_seconds: float = DEFAULT_COOLDOWN,
                  min_len: int = DEFAULT_MIN_LEN,
                  trigger_words=DEFAULT_TRIGGER_WORDS) -> bool:
    """门控：这轮要不要查记忆（确定性——时钟由参数注入，不读真实时间）。

    优先级：
      1. 触发词命中 → 必召回（用户明确要回忆，冷却也拦不住）；
      2. 冷却期内（now − last_recall_ts < cooldown_seconds）→ 不召回；
      3. 空/超短寒暄（len < min_len）→ 不召回；
      4. 其余实质消息 → 召回。
    """
    msg = (message or '').strip()
    if not msg:
        return False
    if any(w in msg for w in trigger_words):
        return True
    if (cooldown_seconds and cooldown_seconds > 0
            and last_recall_ts is not None and now is not None):
        if (now - last_recall_ts) < cooldown_seconds:
            return False
    if len(msg) < min_len:
        return False
    return True


def prep_for_reply(user_msg: str, db_path: str = None, identity: str = None,
                   embedding_client=None, query: str = None, force: bool = False,
                   budget_chars: int = None, k: int = 10,
                   tag_weight: float = 0.3, time_ratio: float = 0.2,
                   multi_scale: bool = False, mmr_lambda: float = None,
                   now: float = None, last_recall_ts: float = None,
                   cooldown_seconds: float = DEFAULT_COOLDOWN,
                   min_len: int = DEFAULT_MIN_LEN,
                   trigger_words=DEFAULT_TRIGGER_WORDS) -> dict:
    """回复前记忆准备：门控→取 query→联想召回→去重→MMR→预算→格式化文本。

    A 左接口：`query` 是上层 AI 判断出的"要查什么语义"，显式给出则优先于用户原话
    （保留 AI 对语境的深层理解）；不给则回退用 `user_msg` 原文。

    返回 {recalled: bool, text: str, results: list[dict]}：
      - recalled=False（被门控挡下）→ text=""、results=[]；
      - 否则 text 为可直接注入回复开头的文本块，results 为结构化结果
        （供未来 hook 直接消费，不经文本再解析）。
    """
    # 1. 门控
    if not force and not should_recall(
            user_msg, now=now, last_recall_ts=last_recall_ts,
            cooldown_seconds=cooldown_seconds, min_len=min_len,
            trigger_words=trigger_words):
        return {'recalled': False, 'text': '', 'results': []}

    # 2. 取 query（AI 定语义优先，否则原话）
    effective_query = (query or '').strip() or (user_msg or '').strip()
    if not effective_query:
        return {'recalled': False, 'text': '', 'results': []}

    # 3. 解析库与客户端
    if db_path is None:
        if identity:
            ensure_agent(identity)
        db_path = get_db_path(identity)
    if embedding_client is None:
        embedding_client = load_embedding_client(
            {'api_key': os.environ.get('SILICONFLOW_API_KEY', ''), 'dimension': 1024})

    # 4. 联想召回（透传票2 多尺度 / 票3 MMR）
    results = recall_associative(effective_query, db_path, embedding_client,
                                 k=k, tag_weight=tag_weight, time_ratio=time_ratio,
                                 multi_scale=multi_scale, mmr_lambda=mmr_lambda)

    # 5. 去重 → 预算收敛（顺序：先去重再收预算，避免重复条目白占预算）
    results = dedupe_results(results)
    results = fit_to_budget(results, budget_chars)

    # 6. 格式化文本块（保留完整正文，不拦腰截断）
    text = format_recall_output(results)
    return {'recalled': True, 'text': text, 'results': results}


def main(argv=None) -> int:
    """薄 CLI：python prep.py --message '...' [--identity NAME] [--db PATH]
    [--query '...'] [--budget N] [--k N] [--force] [--multi-scale] [--mmr 0.5]

    被门控挡下时不打印任何内容、退出码 0（skill 侧据此跳过注入）。
    """
    argv = argv if argv is not None else sys.argv[1:]
    message = None
    query = None
    identity = os.environ.get('MIDNIGHT_AGENT')
    db_path = None
    budget = None
    k = 10
    force = False
    multi_scale = False
    mmr = None
    cooldown = DEFAULT_COOLDOWN

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--message' and i + 1 < len(argv):
            message = argv[i + 1]; i += 2
        elif arg == '--query' and i + 1 < len(argv):
            query = argv[i + 1]; i += 2
        elif arg in ('--identity', '--agent') and i + 1 < len(argv):
            identity = argv[i + 1]; i += 2
        elif arg == '--db' and i + 1 < len(argv):
            db_path = argv[i + 1]; i += 2
        elif arg == '--budget' and i + 1 < len(argv):
            budget = int(argv[i + 1]); i += 2
        elif arg == '--k' and i + 1 < len(argv):
            k = int(argv[i + 1]); i += 2
        elif arg == '--mmr' and i + 1 < len(argv):
            mmr = float(argv[i + 1]); i += 2
        elif arg == '--cooldown' and i + 1 < len(argv):
            cooldown = float(argv[i + 1]); i += 2
        elif arg == '--force':
            force = True; i += 1
        elif arg == '--multi-scale':
            multi_scale = True; i += 1
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 2

    if not message:
        print("Usage: prep.py --message '...' [--identity NAME] [--query '...'] "
              "[--budget N] [--k N] [--force] [--multi-scale] [--mmr 0.5]",
              file=sys.stderr)
        return 1

    out = prep_for_reply(message, db_path=db_path, identity=identity,
                         query=query, force=force, budget_chars=budget, k=k,
                         multi_scale=multi_scale, mmr_lambda=mmr,
                         now=time.time(), cooldown_seconds=cooldown)
    if out['recalled'] and out['text']:
        print(out['text'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
