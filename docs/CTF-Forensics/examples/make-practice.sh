#!/usr/bin/env bash
# Generates a set of beginner forensics practice files in ./generated/
# Run in Kali/WSL where you also have the tools to SOLVE them.
set -euo pipefail
cd "$(dirname "$0")"
OUT="generated"
mkdir -p "$OUT"

if ! command -v zip >/dev/null 2>&1; then
  echo "ERROR: 'zip' not found. Run this in Kali/WSL (sudo apt install zip)," >&2
  echo "       or use the Windows version: powershell .\\make-practice.ps1" >&2
  exit 1
fi

rot13() { echo "$1" | tr 'A-Za-z' 'N-ZA-Mn-za-m'; }

# 1) Wrong extension: a ZIP named .png -----------------------------------------
echo "flag{extensions_are_liars}" > /tmp/_hint.txt
( cd /tmp && zip -q _sneaky.zip _hint.txt )
cp /tmp/_sneaky.zip "$OUT/secret.png"    # looks like an image, actually a zip

# 2) Appended data: a real PNG with a ZIP glued on the end ----------------------
# minimal 1x1 PNG
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82' > "$OUT/cat_photo.bin"
echo "flag{data_hidden_after_the_image}" > /tmp/_appended.txt
( cd /tmp && zip -q _appended.zip _appended.txt )
cat /tmp/_appended.zip >> "$OUT/cat_photo.bin"   # append the zip

# 3) ROT13 -------------------------------------------------------------------
{ echo "You intercepted this note. It's scrambled:"; rot13 "flag{rot13_is_not_encryption}"; } > "$OUT/notes.txt"

# 4) Base64 ------------------------------------------------------------------
printf 'flag{base64_is_not_encryption_either}' | base64 > "$OUT/data.b64"

# 5) EXIF metadata (only if exiftool is present) -----------------------------
if command -v exiftool >/dev/null 2>&1; then
  cp "$OUT/cat_photo.bin" "$OUT/meta.jpg" 2>/dev/null || true
  # make a tiny valid jpg instead so exiftool can write to it
  printf '\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9' > "$OUT/meta.jpg"
  exiftool -overwrite_original -Comment="flag{metadata_is_the_easiest_points}" "$OUT/meta.jpg" >/dev/null
else
  echo "(exiftool not found — skipping the metadata challenge; apt install exiftool)"
fi

rm -f /tmp/_hint.txt /tmp/_sneaky.zip /tmp/_appended.txt /tmp/_appended.zip
echo "Done. Practice files are in: $OUT/"
echo "Now try to solve them WITHOUT reading solutions.ai.md."
