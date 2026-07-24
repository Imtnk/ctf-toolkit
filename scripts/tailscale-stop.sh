#!/usr/bin/env bash
# tailscale-stop.sh — disconnect Kali from the tailnet AND stop the daemon.
# `tailscale down` on its own leaves tailscaled running (and it keeps logging);
# this also stops the daemon so nothing lingers on your terminal. Needs sudo.
set -u

SOCK=/run/tailscale/tailscaled.sock

sudo tailscale --socket="$SOCK" down 2>/dev/null || true

if pgrep -x tailscaled >/dev/null 2>&1; then
  echo "[..] stopping tailscaled ..."
  sudo pkill -x tailscaled || true
  sleep 1
  pgrep -x tailscaled >/dev/null 2>&1 \
    && echo "[!] tailscaled still running — try: sudo pkill -9 -x tailscaled" \
    || echo "[ok] tailscaled stopped"
else
  echo "[ok] tailscaled not running"
fi
