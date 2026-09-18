#!/usr/bin/env bash
# Symlinks this skill directory into every AI coding agent's native skills
# root it can find, so Claude Code, Codex CLI, OpenCode, Cursor, and Kimi
# Code all discover it as a real skill (SKILL.md), not a copy-pasted prompt.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="$(basename "$SRC")"

TARGETS=(
  "$HOME/.claude/skills/$NAME"           # Claude Code
  "$HOME/.codex/skills/$NAME"            # Codex CLI (default CODEX_HOME)
  "$HOME/.agents/skills/$NAME"           # Codex CLI external root; also scanned by OpenCode
  "$HOME/.cursor/skills/$NAME"           # Cursor
  "$HOME/.kimi-code/skills/$NAME"        # Kimi Code
)

for target in "${TARGETS[@]}"; do
  parent="$(dirname "$target")"
  if [ ! -d "$parent" ]; then
    echo "skip: $parent doesn't exist (agent not installed?)"
    continue
  fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$SRC" ]; then
      echo "ok:   $target already linked"
      continue
    fi
    echo "skip: $target already exists and isn't linked to this repo (remove it manually if you want to relink)"
    continue
  fi
  ln -s "$SRC" "$target"
  echo "linked: $target -> $SRC"
done

echo
echo "OpenCode also auto-scans ~/.claude/skills and ~/.agents/skills by default"
echo "(disable with OPENCODE_DISABLE_EXTERNAL_SKILLS=1), so no separate OpenCode"
echo "target is created here."
