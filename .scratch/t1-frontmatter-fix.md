## Parent

#2

## What to build

技能导入器能正确解析每个 skill 的 frontmatter 并在技能库详情页展示 name/description。recall 的 description 内嵌 ASCII 双引号导致 YAML 解析失败、详情页空白；修复为中文弯引号，并验证四个 skill 全部可解析。

## Acceptance criteria

- [ ] 四个 SKILL.md 的 frontmatter 均可被 yaml.safe_load 解析
- [ ] recall description 语义不变，仅内层引号形态修正

## Blocked by

- None (can start immediately)

**Status:** done（commit d3b35fd）
