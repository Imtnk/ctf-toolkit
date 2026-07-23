#!/usr/bin/env zsh
# Swap the loaded Ollama model to free / reclaim RAM (M3 Pro, 18 GB).
#   ./switch-model.sh deepseek  -> deepseek-r1:14b    (primary; chain-of-thought; ~9 GB)
#   ./switch-model.sh coder     -> qwen2.5-coder:14b  (coding-focused; ~9 GB)
#   ./switch-model.sh dolphin   -> dolphin-llama3:8b  (uncensored fallback; ~5 GB)
#   ./switch-model.sh status    -> what's loaded + RAM usage
set -e

DEEPSEEK="deepseek-r1:14b"
CODER="qwen2.5-coder:14b"
DOLPHIN="dolphin-llama3:8b"

_stop_all() {
  ollama stop "$DEEPSEEK" 2>/dev/null || true
  ollama stop "$CODER"    2>/dev/null || true
  ollama stop "$DOLPHIN"  2>/dev/null || true
}

case "$1" in
  deepseek)
    _stop_all
    ollama run "$DEEPSEEK" ""
    ;;
  coder)
    _stop_all
    ollama run "$CODER" ""
    ;;
  dolphin)
    _stop_all
    ollama run "$DOLPHIN" ""
    ;;
  status|"")
    echo "=== loaded (ollama ps) ==="; ollama ps
    echo "=== installed (ollama list) ==="; ollama list
    ;;
  *)
    echo "usage: $0 {deepseek|coder|dolphin|status}" >&2
    exit 1
    ;;
esac
