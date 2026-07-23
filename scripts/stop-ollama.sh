#!/usr/bin/env bash
# Stop the Ollama model server (frees RAM for SageMath/Ghidra/etc.).
set -u

brew services stop ollama
sleep 1

if curl -s -m 3 http://localhost:11434 >/dev/null 2>&1; then
  echo "[warn] still responding — give it a moment, or check: brew services list | grep ollama"
else
  echo "[ok] Ollama stopped"
fi
