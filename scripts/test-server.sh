#!/usr/bin/env bash
# Health check for the Mac Ollama server.
#   On the Mac:            ./test-server.sh
#   From Kali / Windows:   ./test-server.sh 192.168.1.11
# Exits 0 only if every check passes.
set -u

HOST="${1:-localhost}"
PORT="${2:-11434}"
BASE="http://${HOST}:${PORT}"
PASS=0; FAIL=0
ok(){ echo "  [PASS] $1"; PASS=$((PASS+1)); }
no(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "Testing Ollama server at ${BASE}"
echo "----------------------------------------"

# 1. server reachable
if curl -s -m 5 "${BASE}" | grep -q "Ollama is running"; then
  ok "server reachable"
else
  no "server NOT reachable (check IP, that Ollama is running, and OLLAMA_HOST=0.0.0.0)"
fi

# 2. required models present
TAGS=$(curl -s -m 5 "${BASE}/api/tags")
for m in "qwen2.5-coder:14b" "dolphin-llama3:8b"; do
  if echo "$TAGS" | grep -q "\"${m}\""; then ok "model present: ${m}"; else no "model MISSING: ${m}"; fi
done

# 3. generation works end-to-end
RESP=$(curl -s -m 120 "${BASE}/api/generate" -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-coder:14b","prompt":"Reply with exactly one word: PONG","stream":false,"options":{"num_ctx":8192,"temperature":0}}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','').strip())" 2>/dev/null)
if [ -n "${RESP}" ]; then ok "generation works (model replied: ${RESP:0:40})"; else no "generation failed"; fi

echo "----------------------------------------"
echo "Result: ${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ]
