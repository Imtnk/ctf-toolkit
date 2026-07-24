#!/usr/bin/env bash
# tailscale-start.sh — bring Kali (WSL2) onto the tailnet, quietly.
# Starts tailscaled DETACHED with its logs redirected to a file (so they don't
# spam your terminal), then `tailscale up`. Idempotent — safe to re-run.
# Needs sudo. Env: TS_HOSTNAME (default kali-wsl).
set -u

STATE=/var/lib/tailscale/tailscaled.state
SOCK=/run/tailscale/tailscaled.sock
LOG=/var/log/tailscaled.log
TS_HOSTNAME="${TS_HOSTNAME:-kali-wsl}"

[ -e /dev/net/tun ] || echo "[!] /dev/net/tun missing — tailscaled will use userspace networking"

if pgrep -x tailscaled >/dev/null 2>&1; then
  echo "[ok] tailscaled already running"
else
  echo "[..] starting tailscaled (logs -> $LOG) ..."
  sudo mkdir -p "$(dirname "$STATE")" "$(dirname "$SOCK")"
  # nohup + background inside the sudo shell so the daemon detaches from this TTY.
  sudo sh -c "nohup tailscaled --state=$STATE --socket=$SOCK >$LOG 2>&1 &"
  sleep 2
fi

# Connect. Prints a one-time login URL only if this node isn't logged in yet.
sudo tailscale --socket="$SOCK" up --hostname="$TS_HOSTNAME"

echo
sudo tailscale --socket="$SOCK" status | head -6
echo "[ok] up as '$TS_HOSTNAME' — set CTF_AI_HOST to the Ollama host's tailnet name, then: ctf-eval <file> --local"
