# -*- coding: utf-8 -*-
"""票3：文档契约测试——规则被"写进 SKILL.md"这件事本身必须可回归。

为什么值得给文档写测试：本轮的核心资产不是代码，是**规则**。规则写在 prompt 里、
靠 Agent 自觉遵守，一旦哪天被人"顺手简化"掉（比如把"md 永不作为检索目标"删成
"尽量用算法"），能力还在、约束没了，坏行为会静默回来。

所以这里断言的是**不可删的句子**，而不是措辞优美。
"""
import os

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SKILL = os.path.join(REPO_ROOT, 'skills', 'recall', 'SKILL.md')
PROJECT = os.path.join(REPO_ROOT, 'PROJECT.md')
CONTEXT = os.path.join(REPO_ROOT, 'CONTEXT.md')
ADR2 = os.path.join(REPO_ROOT, 'docs', 'adr', '0002-md-is-source-not-index.md')
ADR3 = os.path.join(REPO_ROOT, 'docs', 'adr', '0003-associative-trunk-with-constraints.md')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def skill():
    return _read(SKILL)


# ============================================================
# 1. 检索铁律：一条主干 + 两个约束 + md 不是索引 + 例外条件
# ============================================================

def test_skill_declares_trunk_plus_constraints(skill):
    """ADR-0003：检索是「一条主干 + 两个约束」，不是三条并列通道。"""
    assert '检索铁律' in skill
    assert '主干' in skill
    assert '约束 A：时间窗' in skill
    assert '约束 B：字面' in skill
    assert '--timeline' in skill
    assert '--literal' in skill
    assert '--since' in skill and '--until' in skill


def test_skill_states_constraint_is_not_ranking(skill):
    """最容易搞混的一句：约束过滤候选池，主干才排序。"""
    assert '约束是过滤候选池' in skill
    assert '主干是排序' in skill


def test_skill_shows_combined_time_semantic_query(skill):
    """「十月以后关于备课的」必须能一次问出口，不是两次调用再对齐。"""
    assert '--since 2026-10-01' in skill
    hits = [l for l in skill.splitlines() if '--since 2026-10-01' in l]
    assert hits
    assert any('--query' in l for l in hits), '合并查询示例里必须有 --query'


def test_skill_says_md_is_not_index_but_constraints_are(skill):
    # 这句是整条铁律的核心：源 ≠ 索引
    assert '永远不是检索目标' in skill
    assert 'recall.db' in skill


def test_skill_states_the_explicit_authorization_exception(skill):
    # 例外口子必须写成"用户明确说"，不能留成"视情况自行判断"
    assert '仅当用户明确说' in skill
    assert '读原文' in skill and '看文件' in skill


def test_skill_has_self_check_trigger(skill):
    """发现自己要 grep/read dailynote 时必须停手改道——这是防止规则被遗忘的钩子。"""
    assert '自检触发点' in skill
    assert '停手' in skill


def test_no_line_teaches_reading_md_as_a_default_path(skill):
    """任何提到 grep 的行，必须同时是"禁止/例外/停手"，不能是"先 grep 一下"。"""
    allowed = ('停手', '仅当', '不要', '禁止', '不读', '别', '禁止跨')
    for line in skill.splitlines():
        if 'grep' in line:
            assert any(w in line for w in allowed), f'可疑的 grep 指引：{line!r}'


# ============================================================
# 2. 查询派生协议
# ============================================================

def test_skill_has_query_derivation_protocol(skill):
    assert '查询派生协议' in skill
    assert '2–5 个名词性线索' in skill
    assert 'anchor' in skill
    assert '--multi-scale' in skill
    assert '不要把用户原话直接当 query' in skill


# ============================================================
# 3. 留痕可核查
# ============================================================

def test_skill_documents_ledger_and_audit(skill):
    assert 'retrieval_ledger.jsonl' in skill
    assert '--audit' in skill
    assert '不要试图绕过它' in skill


def test_skill_says_prep_is_covered_by_ledger(skill):
    """默认入口 prep.py 必须也在留痕范围内——否则"每次检索都留痕"是假话。"""
    assert 'prep.py' in skill
    for line in skill.splitlines():
        if 'retrieval_ledger.jsonl' in line:
            assert 'prep.py' in line, f'留痕声明漏了默认入口：{line!r}'


def test_skill_requires_identity_for_deterministic_channels(skill):
    assert '必须显式带 `--identity/--agent`' in skill or '必须显式带 --identity/--agent' in skill


# ============================================================
# 4. 真相回写（PROJECT / CONTEXT / ADR）
# ============================================================

def test_project_truth_updated():
    project = _read(PROJECT)
    assert 'ledger.py' in project
    assert 'retrieval_ledger.jsonl' in project
    assert '--timeline' in project
    assert 'ADR-0002' in project
    assert '检索只走库' in project
    # Issue #7 / ADR-0003：主干 + 约束
    assert '联想主干' in project
    assert '时间窗' in project
    assert 'ADR-0003' in project


def test_context_terms_added():
    context = _read(CONTEXT)
    for term in ('检索通道', '联想主干', '时间窗约束', '字面约束', '检索留痕', 'md 源文件'):
        assert f'**{term}**' in context


def test_adr_0002_exists_and_has_three_parts():
    assert os.path.exists(ADR2)
    adr = _read(ADR2)
    for part in ('## 背景', '## 决定', '## 后果'):
        assert part in adr
    assert '不是索引' in adr or '不作检索索引' in adr


def test_adr_0003_exists_and_records_the_convergence():
    """ADR-0003 必须写清"约束 ≠ 排序"以及时间窗要压两处。"""
    assert os.path.exists(ADR3), 'ADR-0003 缺失'
    adr = _read(ADR3)
    for part in ('## 背景', '## 决定', '## 理由', '## 后果'):
        assert part in adr
    assert 'expand_tag_candidates' in adr, '必须写明标签扩增也要压窗口'
    assert '缓存键' in adr
    assert '排完再筛' in adr


# ============================================================
# 5. 能力经验（Issue #10）
# ============================================================

def test_skill_md_has_skill_experience_section(skill):
    """能力经验章节不可被删：标签约定与「不打分」是它的全部价值。"""
    assert '## 能力经验' in skill
    assert 'skill经验' in skill
    assert '踩坑' in skill
    assert '不打分' in skill


def test_skill_md_says_paths_not_catalog(skill):
    """能力存在性走「一句指路」，不是清单——这句不许被改成「列出来」。"""
    assert '一句指路' in skill or '现查现用' in skill
    # 反面：不许出现「开机清单里列 skill」这类指引
    for line in skill.splitlines():
        if '开机清单' in line and 'skill' in line.lower():
            assert '不' in line or '别' in line, f'可疑的清单指引：{line!r}'


def test_default_template_keeps_paths():
    """paths 两句不能被人顺手删掉。"""
    from scripts.self_model import DEFAULT_PATHS, DEFAULT_TEMPLATE
    assert DEFAULT_TEMPLATE['mutable']['paths'] == DEFAULT_PATHS
    joined = ' '.join(DEFAULT_PATHS)
    assert '技能库' in joined
    assert '同伴' in joined


# ============================================================
# 6. 文档与实现对齐（Issue #17）——反向锁
# ============================================================

# 这些参数只存在于库函数 recall_associative() 的签名里，CLI 从不暴露。
# 实测：recall.py / prep.py 传这些一律 Unknown option 退出 2。
LIB_ONLY_FLAGS = ('--tag-weight', '--time-ratio', '--truncate')


def _cli_lines(text):
    """抽出所有 ```bash / ``` 代码块里的行（只查命令行示例）。"""
    lines = []
    in_block = False
    for line in text.splitlines():
        if line.strip().startswith('```'):
            in_block = not in_block
            continue
        if in_block:
            lines.append(line)
    return lines


def test_skill_md_has_no_fake_cli_flags(skill):
    """命令行示例里不得出现 CLI 不存在的参数。

    这是本 Issue 的核心反向锁：把「文档教了跑不通的参数」变成测试失败，
    而不是靠人记得改。
    """
    for line in _cli_lines(skill):
        for flag in LIB_ONLY_FLAGS:
            assert flag not in line, (
                f'SKILL.md 的命令行示例用了 CLI 不存在的参数 {flag}：{line!r}\n'
                f'（它只在 recall_associative() 的 Python 签名里）'
            )


def test_skill_md_lists_all_scripts(skill):
    """实际存在的每个 scripts/*.py，都要在「文件结构」里出现。"""
    import glob
    scripts_dir = os.path.join(REPO_ROOT, 'skills', 'recall', 'scripts')
    real = {os.path.basename(p) for p in glob.glob(os.path.join(scripts_dir, '*.py'))}
    real.discard('__init__.py')
    missing = sorted(n for n in real if n not in skill)
    assert not missing, f'SKILL.md 文件结构漏了这些脚本：{missing}'


def test_skill_md_no_phantom_dir(skill):
    """不许列出不存在的目录（references/ 从没建过）。"""
    import os as _os
    if not _os.path.isdir(_os.path.join(REPO_ROOT, 'skills', 'recall', 'references')):
        assert 'references/' not in skill, 'SKILL.md 列了不存在的 references/ 目录'


def test_skill_md_description_of_session_start_cli(skill):
    """session_start 已改为不截断，文档不许再写「≤200 字」。"""
    for line in skill.splitlines():
        if 'session_start' in line and '200' in line:
            pytest.fail(f'session_start 描述已过期（实现早改成不截断）：{line!r}')


# ============================================================
# 7. 概念校准（Issue #18）——反向锁
# ============================================================

# 技能库位置是 harness 运行时事实，不是文档能规定的常量。
# 写死具体路径，换 harness 照抄就错。
HARDCODED_SKILL_PATHS = ('.dsh/skills', '.agents/skills', '.dsh\\skills', '.agents\\skills')


def test_skill_md_no_hardcoded_skill_path(skill):
    """SKILL.md 不得把某个 harness 的技能库路径当范例写死。"""
    for name in HARDCODED_SKILL_PATHS:
        assert name not in skill, (
            f'SKILL.md 写死了技能库路径 {name!r}。\n'
            f'技能库在哪是 harness 运行时告诉的，不同 harness 不一样。'
        )


def test_context_no_hardcoded_skill_path():
    """CONTEXT.md 同样不许写死。"""
    text = _read(CONTEXT)
    for name in HARDCODED_SKILL_PATHS:
        assert name not in text, f'CONTEXT.md 写死了技能库路径 {name!r}'


def test_closing_question_not_action_only(skill):
    """收尾问句必须问「东西」，不能缩回「动作」。

    「动作」只覆盖「重新做」（工具/模板/清单），漏掉「重新想」（范式/结论/图例）。
    """
    # 定位收尾那一刻那一段
    marker = '收尾那一刻'
    assert marker in skill, '收尾触发点不见了'
    start = skill.index(marker)
    segment = skill[start:start + 400]

    assert '哪些东西' in segment, (
        '收尾问句必须问「哪些东西」——「动作」只覆盖重新做，漏掉重新想'
    )
    assert '哪些动作' not in segment, '收尾问句又缩回「动作」了'


# ============================================================
# 8. 开机流程（Issue #19）——boot.py 必须进流程
# ============================================================

def test_skill_md_teaches_boot_on_session_start(skill):
    """触发条件表里必须出现 boot.py —— 否则它造好也没人跑。"""
    marker = '## 触发条件'
    assert marker in skill
    start = skill.index(marker)
    segment = skill[start:start + 1800]      # 触发条件那一节

    assert 'boot.py' in segment, (
        '触发条件表没教开机跑 boot.py——能力有了但接不上，等于没有'
    )
    assert '会话第一条' in segment or '开机' in segment, '触发条件表缺「开机」这一行'


def test_skill_md_has_boot_order_section(skill):
    """必须有「开机顺序」一节，讲清 boot 与 prep 的分工。"""
    assert '## 开机顺序' in skill
    start = skill.index('## 开机顺序')
    segment = skill[start:start + 1200]

    assert 'boot.py' in segment
    assert 'prep.py' in segment


def test_skill_md_states_boot_once(skill):
    """必须明写 boot.py 只跑一次，防有人把它加进「每次回复前」，每轮烧一遍。

    断言锚在**分工表那一行**，不锚「一次」二字——标题里也有「一次」，
    只查博字符串会被标题自己满足，测试就废了。
    """
    assert '| `boot.py` |' in skill, '分工表缺 boot.py 那一行'
    for line in skill.splitlines():
        if line.startswith('| `boot.py`'):
            assert '一次' in line, (
                f'分工表里 boot.py 那行必须明写「一次」：{line!r}'
            )
            break

    # 反面：不许把 boot.py 和「每次回复前」绑在一起。
    # 只查表行（以 | 开头）——正文那句「每次回复前，先查一下记忆」是讲召回，不涉及 boot。
    for line in skill.splitlines():
        if line.startswith('|') and '每次回复前' in line:
            assert 'boot.py' not in line, (
                f'boot.py 不许出现在「每次回复前」——会每轮重烧开机清单：{line!r}'
            )
