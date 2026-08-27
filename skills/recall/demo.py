"""midnight-recall 端到端演示脚本。

快速体验完整流程：写日记 → 入库 → 召回。
"""
import os
import sys
import tempfile

# 确保可以导入 scripts 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file, ingest_directory
from scripts.recall import recall_associative, format_recall_output


def main():
    print("=" * 60)
    print("midnight-recall 端到端演示")
    print("=" * 60)

    # 1. 创建临时环境
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, 'recall.db')
    diary_dir = os.path.join(tmpdir, 'dailynote')
    os.makedirs(diary_dir, exist_ok=True)

    print(f"\n[1/5] 初始化数据库...")
    init_db(db_path)
    print(f"     数据库: {db_path}")

    # 2. 创建几篇测试日记
    print(f"\n[2/5] 写测试日记...")
    entries = [
        ("考试 压力 焦虑", "用户说下周要参加数学考试，压力很大，晚上睡不着。"),
        ("考试 复习", "用户今天复习了数学，做了很多练习题，感觉有些进步。"),
        ("旅行 美食 京都", "用户计划去京都旅行，听说那里的抹茶甜品很有名。"),
        ("编程 Python", "用户在学习 Python 装饰器，觉得语法糖很优雅。"),
        ("日常 天气", "今天天气很好，用户出去散步了，心情不错。"),
    ]
    client = FakeEmbeddingClient(dimension=16)

    for i, (tags, content) in enumerate(entries):
        file_path = os.path.join(diary_dir, f'diary_{i+1}.md')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"""---
maid: Nova
created: 2026-08-{10+i:02d}T10:00:00
tags: [{tags}]
---
{content}
""")
        result = ingest_file(file_path, db_path, client)
        print(f"     [{result['status']}] {tags}")

    # 3. 入库确认
    print(f"\n[3/5] 入库确认...")
    import sqlite3
    conn = sqlite3.connect(db_path)
    file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    tag_count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    co_count = conn.execute("SELECT COUNT(*) FROM tag_cooccurrence").fetchone()[0]
    conn.close()
    print(f"     文件: {file_count}, 片段: {chunk_count}, 标签: {tag_count}, 共现: {co_count}")

    # 4. 联想召回测试
    print(f"\n[4/5] 联想召回测试...")
    queries = [
        ("焦虑", "考试压力场景"),
        ("京都", "旅行场景"),
        ("Python", "编程场景"),
    ]

    for query, desc in queries:
        print(f"\n     查询: 「{query}」({desc})")
        results = recall_associative(query, db_path, client,
                                     k=5, tag_weight=0.5, time_ratio=0.3, decay=0.5)
        for r in results:
            print(f"       [{r['score']:.3f}] {r['content'][:50]}...")

    # 5. 联想验证
    print(f"\n[5/5] 联想验证（核心能力）...")
    print(f"     查询「焦虑」应该召回「考试」相关的内容，")
    print(f"     即使「焦虑」这个词本身没有出现在考试日记里。")
    results = recall_associative("焦虑", db_path, client,
                                 k=10, tag_weight=0.5, time_ratio=0.2)
    contents = [r['content'] for r in results]
    has_exam = any('考试' in c or '数学' in c for c in contents)
    print(f"     联想结果包含考试内容: {'是' if has_exam else '否'}")

    import shutil
    shutil.rmtree(tmpdir)

    print(f"\n{'=' * 60}")
    print(f"演示完成。{'联想正常工作' if has_exam else '联想未生效'}")
    print(f"{'=' * 60}")
    return 0 if has_exam else 1


if __name__ == '__main__':
    sys.exit(main())