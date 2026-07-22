#!/usr/bin/env bash
# install.sh — install ctf-file and its forensics dependencies on Kali (or Debian/Ubuntu).
# Safe to re-run (idempotent). Run as a normal user; it uses sudo only for apt/gem.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/ctf-file"
[ -f "$SCRIPT" ] || { echo "error: ctf-file not found next to install.sh"; exit 1; }

# ---- pick an install dir on PATH -----------------------------------------
if printf '%s' ":$PATH:" | grep -q ":$HOME/.local/bin:"; then
  BIN="$HOME/.local/bin"
elif printf '%s' ":$PATH:" | grep -q ":$HOME/bin:"; then
  BIN="$HOME/bin"
else
  BIN="$HOME/.local/bin"          # default; we'll add it to PATH below
fi

echo "==> Installing apt packages (needs sudo) ..."
APT_PKGS="file binutils xxd binwalk libimage-exiftool-perl unzip john steghide stegseek pngcheck ruby wordlists"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  # install what's available; don't abort the whole run if one package name differs
  for p in $APT_PKGS; do
    sudo apt-get install -y "$p" || echo "   (skipped '$p' — not found in this repo)"
  done
else
  echo "   apt-get not found — install these yourself: $APT_PKGS"
fi

echo "==> Installing zsteg (ruby gem) ..."
if command -v gem >/dev/null 2>&1; then
  sudo gem install zsteg || echo "   (zsteg install failed — PNG LSB stego will be skipped)"
else
  echo "   ruby/gem not present — skipping zsteg (install 'ruby' then 'gem install zsteg')"
fi

# ---- install the script ---------------------------------------------------
echo "==> Installing ctf-file -> $BIN/ctf-file"
install -Dm755 "$SCRIPT" "$BIN/ctf-file"

# ---- ensure PATH ----------------------------------------------------------
if ! printf '%s' ":$PATH:" | grep -q ":$BIN:"; then
  LINE="export PATH=\"$BIN:\$PATH\""
  if ! grep -qsF "$LINE" "$HOME/.bashrc"; then
    printf '\n# added by ctf-file install.sh\n%s\n' "$LINE" >> "$HOME/.bashrc"
    echo "==> Added $BIN to PATH in ~/.bashrc — run 'source ~/.bashrc' or open a new shell."
  fi
fi

echo
echo "Done. Try:  ctf-file -h"
echo "(if 'command not found', run:  source ~/.bashrc )"
