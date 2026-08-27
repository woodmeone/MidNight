#!/usr/bin/env bash
# Midnight Skills 一键安装脚本 — 安装到各编码编辑器的 Agent Skills 目录
#
# 用法:
#   bash install-skills.sh claude           # 安装到 Claude Code 全局 (~/.claude/skills/)
#   bash install-skills.sh cursor .         # 安装到当前项目 (.cursor/skills/)
#   bash install-skills.sh trae .           # 安装到 Trae (.trae/skills/)
#   bash install-skills.sh codebuddy .      # 安装到 CodeBuddy (.codebuddy/skills/)
#   bash install-skills.sh all .            # 全部安装
#
# 依赖: Python 3.8+, pip install requests

set -euo pipefail

# 项目根目录（脚本所在目录的上一级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/../skills"

SKILLS=(recall core pulse compass)

usage() {
    echo "用法: bash install-skills.sh <target> [project_dir]"
    echo ""
    echo "target:"
    echo "  claude      安装到 Claude Code 全局 (~/.claude/skills/)"
    echo "  cursor      安装到 Cursor 项目级 (.cursor/skills/)"
    echo "  trae        安装到 Trae 项目级 (.trae/skills/)"
    echo "  codebuddy   安装到 CodeBuddy 项目级 (.codebuddy/skills/)"
    echo "  all         安装到所有支持的编辑器"
    exit 1
}

install_to() {
    local target="$1"
    local proj_dir="${2:-.}"
    local dest=""

    case "$target" in
        claude)
            dest="$HOME/.claude/skills"
            ;;
        cursor)
            dest="$proj_dir/.cursor/skills"
            ;;
        trae)
            dest="$proj_dir/.trae/skills"
            ;;
        codebuddy)
            dest="$proj_dir/.codebuddy/skills"
            ;;
        *)
            echo "未知目标: $target"
            usage
            ;;
    esac

    echo "→ 安装到 $dest"
    mkdir -p "$dest"

    for skill in "${SKILLS[@]}"; do
        if [ -d "$SKILLS_SRC/$skill" ]; then
            cp -r "$SKILLS_SRC/$skill" "$dest/"
            echo "  ✓ $skill"
        else
            echo "  ⚠ 跳过 $skill（源目录不存在）"
        fi
    done

    echo "  完成。在编辑器中输入 skill 名（如 recall）即可触发。"
}

[ $# -eq 0 ] && usage

TARGET="$1"
PROJ_DIR="${2:-.}"

case "$TARGET" in
    all)
        install_to claude "$PROJ_DIR"
        install_to cursor "$PROJ_DIR"
        install_to trae "$PROJ_DIR"
        install_to codebuddy "$PROJ_DIR"
        ;;
    claude|cursor|trae|codebuddy)
        install_to "$TARGET" "$PROJ_DIR"
        ;;
    *)
        usage
        ;;
esac
