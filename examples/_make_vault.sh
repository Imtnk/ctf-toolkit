#!/usr/bin/env bash
# Build a harder layered test: a rockyou-tier password-protected zip whose
# payload holds the flag base64-encoded (deterministic pipeline can't auto-solve;
# the remote brain must read the artifact and reason out the encoding).
set -euo pipefail
cd "$(dirname "$0")"

PASS="butterfly"                       # in rockyou, NOT in ctf-file's built-in common list
FLAG='flag{l4y3r3d_f0r3ns1cs_2026}'
RY=/home/imtnk/wordlists/rockyou.txt

echo "== preflight =="
printf 'butterfly is an exact line in rockyou: '
if grep -qxF "$PASS" "$RY"; then echo YES; else echo "NO — aborting"; exit 1; fi

# clean any prior run
rm -rf vault vault.zip vault.zip-work
mkdir -p vault

# payload 1: a narrative hint (NO literal flag{} token, so nothing is trivially grep-able)
cat > vault/README.txt <<'TXT'
Vault access log
----------------
The keeper never stored the key in the clear. What you seek is wrapped once
more in the usual traveller's cipher (radix sixty-four). Unwrap it to proceed.
TXT

# payload 2: the flag, base64-encoded (this is the only place the flag lives)
printf '%s' "$FLAG" | base64 > vault/secret.b64

echo "== payload =="
echo "secret.b64 contents: $(cat vault/secret.b64)"
echo "decodes to: $(base64 -d vault/secret.b64)"

# zip with a password (ZipCrypto, which zip2john/john handle)
zip -q -j -P "$PASS" vault.zip vault/README.txt vault/secret.b64
rm -rf vault

echo "== verify =="
echo "file type: $(file -b vault.zip)"
printf 'unzip with correct password works: '
if unzip -o -P "$PASS" vault.zip -d _verify >/dev/null 2>&1; then echo YES; else echo NO; fi
printf 'unzip with EMPTY password fails (encrypted): '
if unzip -o -P '' vault.zip -d _verify2 >/dev/null 2>&1; then echo "NO (not encrypted!)"; else echo YES; fi
printf 'zip2john produces a hash: '
if zip2john vault.zip 2>/dev/null | grep -q ':\$'; then echo YES; else echo NO; fi
rm -rf _verify _verify2
echo "== done: $(pwd)/vault.zip =="
ls -la vault.zip
