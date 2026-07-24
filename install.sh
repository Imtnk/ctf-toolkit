#!/usr/bin/env bash
# install.sh — install ctf-file and its forensics dependencies on Kali (or Debian/Ubuntu).
# Safe to re-run (idempotent). Run as a normal user; it uses sudo only for apt/gem.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/bin/ctf-file" ] || { echo "error: bin/ctf-file not found next to install.sh"; exit 1; }

# ---- pick an install dir on PATH -----------------------------------------
if printf '%s' ":$PATH:" | grep -q ":$HOME/.local/bin:"; then
  BIN="$HOME/.local/bin"
elif printf '%s' ":$PATH:" | grep -q ":$HOME/bin:"; then
  BIN="$HOME/bin"
else
  BIN="$HOME/.local/bin"          # default; we'll add it to PATH below
fi

echo "==> Installing apt packages (needs sudo) ..."
# core triage + stego + carving + archive cracking (+ jq for JSON/web work)
APT_CORE="file binutils xxd binwalk libimage-exiftool-perl unzip john steghide stegseek pngcheck outguess ruby wordlists jq"
# network (pcap), documents, QR, audio, disk/memory forensics
APT_FORENSICS="tshark tcpflow poppler-utils zbar-tools sleuthkit foremost testdisk sox python3-oletools"
# reverse engineering & pwnable (gdb+gef usually already present; ROPgadget/ropper/checksec via pip/pkg)
APT_REVERSE="patchelf strace ltrace gdb"
# mobile security — static APK analysis (dynamic frida/objection via pipx below)
APT_MOBILE="apktool jadx dex2jar adb apksigner aapt"
APT_PKGS="$APT_CORE $APT_FORENSICS $APT_REVERSE $APT_MOBILE"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  # install what's available; don't abort the whole run if one package name differs
  for p in $APT_PKGS; do
    sudo apt-get install -y "$p" || echo "   (skipped '$p' — not found in this repo)"
  done
else
  echo "   apt-get not found — install these yourself: $APT_PKGS"
fi

echo "==> Installing ruby gems (zsteg, one_gadget, seccomp-tools) ..."
# zsteg: PNG LSB stego. one_gadget/seccomp-tools: pwnable (execve one-shots, seccomp filters).
if command -v gem >/dev/null 2>&1; then
  for g in zsteg one_gadget seccomp-tools; do
    sudo gem install "$g" || echo "   (gem '$g' failed — the related checks will be skipped)"
  done
else
  echo "   ruby/gem not present — install 'ruby' then 'gem install zsteg one_gadget seccomp-tools'"
fi

echo "==> Installing pwninit (auto-patch a binary to a supplied libc) ..."
if command -v pwninit >/dev/null 2>&1; then
  echo "   pwninit already present"
elif command -v cargo >/dev/null 2>&1; then
  cargo install pwninit || echo "   (cargo install pwninit failed — see github.com/io1/pwninit)"
else
  mkdir -p "$BIN"
  PW_URL="$(curl -fsSL https://api.github.com/repos/io1/pwninit/releases/latest 2>/dev/null \
            | grep -oE 'https://[^"]*x86_64-unknown-linux-musl' | head -1)"
  if [ -n "$PW_URL" ] && curl -fsSL "$PW_URL" -o "$BIN/pwninit"; then
    chmod +x "$BIN/pwninit"; echo "   pwninit -> $BIN/pwninit"
  else
    echo "   (couldn't fetch a pwninit release — install manually: github.com/io1/pwninit)"
  fi
fi

echo "==> Installing Volatility3 for the --heavy memory-dump path (pipx) ..."
if command -v pipx >/dev/null 2>&1; then
  pipx install volatility3 || echo "   (volatility3 install failed — memory analysis will be skipped)"
  pipx ensurepath >/dev/null 2>&1 || true
else
  echo "   pipx not present — run 'sudo apt-get install -y pipx' then 'pipx install volatility3' for memory support"
fi

echo "==> Installing Python web libs (PyJWT, BeautifulSoup) ..."
# Used by the agent's python_exec on the Web category (JWT forgery, HTML parsing).
PIP_WEB="pyjwt beautifulsoup4"
if [ -n "${VIRTUAL_ENV:-}" ] && command -v pip >/dev/null 2>&1; then
  pip install $PIP_WEB || echo "   (pip install failed in venv)"
elif command -v pip3 >/dev/null 2>&1; then
  pip3 install --user $PIP_WEB 2>/dev/null \
    || pip3 install --break-system-packages $PIP_WEB 2>/dev/null \
    || echo "   (pip install failed — activate your ctf venv and 'pip install $PIP_WEB')"
else
  echo "   pip not present — install $PIP_WEB into your ctf Python env"
fi

echo "==> Installing frida-tools + objection (mobile dynamic instrumentation, pipx) ..."
# Optional: only needed for runtime hooking (device/emulator). Static APK analysis
# (jadx/apktool/aapt above) covers most Jeopardy mobile challenges without these.
if command -v pipx >/dev/null 2>&1; then
  pipx install frida-tools || echo "   (frida-tools install failed — dynamic mobile will be skipped)"
  pipx install objection   || echo "   (objection install failed)"
else
  echo "   pipx not present — 'pipx install frida-tools objection' for dynamic mobile"
fi

# ---- install the commands (symlinks into this repo, so `git pull` updates them) ----
mkdir -p "$BIN"
chmod +x "$HERE/bin/ctf-file" "$HERE/bin/ctf-eval" "$HERE/ai-ui.py" "$HERE/ai.py" 2>/dev/null || true
echo "==> Linking commands into $BIN (symlinks -> $HERE)"
ln -sf "$HERE/bin/ctf-file" "$BIN/ctf-file"
ln -sf "$HERE/bin/ctf-eval" "$BIN/ctf-eval"
ln -sf "$HERE/ai-ui.py"     "$BIN/ai"
echo "    ctf-file, ctf-eval, ai -> $HERE"

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
