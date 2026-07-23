# Solutions — Practice Examples

> Spoilers. Only open after you've attempted the files from [[README.ai]].

## Warm-up: `rot13_note.txt`
ROT13 decode → `flag{welcome_to_forensics_practice}`
```bash
cat rot13_note.txt | tr 'A-Za-z' 'N-ZA-Mn-za-m'
```

## Generated set

### `secret.png` — wrong extension
`file secret.png` reports a **Zip archive**, not a PNG. The extension lies.
```bash
file secret.png            # -> Zip archive data
unzip secret.png           # -> _hint.txt
cat _hint.txt              # flag{extensions_are_liars}
```
Lesson: trust magic bytes, not extensions. → [[file-analysis.ai]]

### `cat_photo.bin` — appended ZIP
Valid PNG with a ZIP glued on the end.
```bash
binwalk cat_photo.bin      # shows PNG at 0x0 and Zip archive further in
unzip cat_photo.bin        # extracts _appended.txt
# -> flag{data_hidden_after_the_image}
```
Lesson: images can carry a payload after IEND. → [[file-analysis.ai]]

### `notes.txt` — ROT13
```bash
grep -v scrambled notes.txt | tr 'A-Za-z' 'N-ZA-Mn-za-m'
# -> flag{rot13_is_not_encryption}
```

### `data.b64` — Base64
```bash
base64 -d data.b64
# -> flag{base64_is_not_encryption_either}
```

### `meta.jpg` — EXIF metadata (bash-generated only)
```bash
exiftool meta.jpg | grep -i comment
# Comment : flag{metadata_is_the_easiest_points}
```
Lesson: always `exiftool` an innocent-looking media file. → [[metadata.ai]]

## Takeaway

Every one of these fell to a Step 1–5 reflex from [[01-methodology.ai]]: `file`, `strings`, `binwalk`, `exiftool`, and a decoder. That's ~80% of easy/medium forensics flags.
