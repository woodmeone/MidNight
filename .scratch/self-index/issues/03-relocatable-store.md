# 03 — 记忆库可迁移（路径相对化）

Issue: #11 ｜ Spec: `../spec.md` ｜ Blocked by: 无 ｜ 分支: `feat/self-index`

## 用户故事

作为**用户 YG**，我想要打包一个智能体就能搬走、解压就能用，
以便迁移不丢记忆、不丢人设，换台机器换用户名的路径下也读得到日记源。

## 背景 / 为什么要变

实测（`~/.midnight/recall/*/recall.db`）：

```
C:\Users\WoodMe\.midnight\recall\seagull\dailynote\2026-11-14_173000.md
C:\Users\WoodMe\.midnight\recall\qinglan\dailynote\2026-08-27_220734.md
```

`files.file_path` 存的是**绝对路径，带用户名**。ADR-0002 说「库是单文件，跟着 agent 走」——
库能走，路径不走。换机器 / 换用户名，`file_path` 全断。

这是**迁移的硬阻塞**，也是本项目唯一需要碰既有数据的改动。

## 验收标准

- [ ] `ingest.py` 新增数据写**相对路径**（相对 agent 目录，如 `dailynote/2026-11-14_173000.md`），
      不含盘符、不含用户名
- [ ] 读取侧向后兼容：`file_path` 是绝对路径（老数据）→ 原样返回；
      是相对路径（新数据）→ 按 `os.path.dirname(db_path)` 还原后返回
- [ ] **老数据不做迁移也能正常工作**（相对化是优化，不是前置条件）
- [ ] 可选迁移命令：`maintenance.py --relativize-paths [--agent X] [--dry-run]`
      - **`--dry-run` 为默认**，只打印将要改的行数与样例，零写入
      - 真执行时：先 `VACUUM INTO` 或文件复制备份整库，再 `UPDATE files SET file_path = ?`
      - **只 `UPDATE`，绝不 `DELETE` / `DROP` / 改 `content`**
- [ ] 搬迁验证测试：把整个 agent 目录复制到另一个路径，`--timeline` / `--literal` 仍可读
- [ ] 全量测试与 G1 基线一致（**343 passed / 6 skipped**，2026-11-14 实测）

## 关键设计：为什么兼容而不是强制迁移

`recall(db_path)` 和 `timeline_recall` 只拿到 `db_path`，不知道 agent 名。所以还原基准取
`os.path.dirname(db_path)`——它天然就是 agent 目录。这样：

- 新库：存 `dailynote/x.md`，读时拼回 `<db 所在目录>/dailynote/x.md`
- 老库：存绝对路径，`os.path.isabs()` 判定后原样返回

两种共存，零迁移也能跑。迁移只是把老库也变成可搬的。

## 票（垂直切片，按序实现）

- [ ] 票1：`ingest.py` 写相对路径 + 读取侧兼容（新老共存）｜ Blocked by: 无
- [ ] 票2：`--relativize-paths --dry-run` 预览 + 备份 + 真执行 ｜ Blocked by: 票1
- [ ] 票3：搬迁往返测试（复制目录 → 读时间轴 → 断言内容一致）｜ Blocked by: 票1

## 范围外（本轮不做）

- **不做打包脚本**（`bundle.py` / tar）：路径相对化完成后再单开 Issue
- **不迁移长期内容**（长期内容本来就存相对工作区的路径，且不进库）
- 不改 `chunks` / `files` 以外的任何表
- 不动 `dailynote/*.md` 一个字节

## 对抗式自检（写测试时问自己）

- 老库混合新老格式（迁移一半失败）→ 读取侧能不能同时处理
- `db_path` 是相对路径传入（`recall.db`）→ `dirname` 得到空串，还原会不会变成相对当前目录
- Windows 反斜杠 vs 正斜杠 → 存哪种，读出能不能 `os.path.join` 正常拼
- 迁移中途断电 → 备份能不能恢复
- `diary_date` 为 NULL 的老行 → 迁移 SQL 会不会把它一起改坏
- 迁移后再跑一次 `--relativize-paths` → 幂等不重复改

## 真相影响

- **PROJECT.md**：「关键数据结构」补一句 `files.file_path` 存相对 agent 目录的路径；
  「必须遵守的约束」补「路径相对化：库里不存盘符与用户名」
- **CONTEXT.md**：新增术语 **相对路径（relocatable path）**
- **ADR**：`docs/adr/0005-relocatable-store-paths.md`——记录「为什么兼容而不是强制迁移」
  （取舍：多一层 `isabs` 分支 vs 要求所有库先迁移才能用）
