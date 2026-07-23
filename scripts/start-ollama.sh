#!/usr/bin/env bash
# Start the Ollama model server (launchd/brew service, bound to 0.0.0.0:11434).
set -u

brew services start ollama
sleep 2

if curl -s -m 5 http://localhost:11434 | grep -q "Ollama is running"; then
  IP=$(ipconfig getifaddr en0 2>/dev/null || echo "192.168.1.11")
  echo "[ok] Ollama running  ->  http://localhost:11434  (LAN: http://${IP}:11434)"
else
  echo "[..] service started; not answering yet — re-check with: curl -s http://localhost:11434"
fi
