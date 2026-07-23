# Practice Examples

Hands-on files to build the reflexes from [[01-methodology.ai]]. Two ways to use this:

1. **Generate fresh challenges** with the script, then solve them *before* reading the solutions.
2. **Poke at the checked-in sample** (`rot13_note.txt`) to warm up.

## Generate a practice set

The generator makes a handful of classic easy forensics artifacts in `examples/generated/`.

- **Bash / WSL / Kali** (preferred — has the real tools to solve them):
  ```bash
  cd /d/obsidian-vault/CTF-Forensics/examples
  bash make-practice.sh
  ```
- **Windows PowerShell** (no extra tools needed to generate):
  ```powershell
  cd D:\obsidian-vault\CTF-Forensics\examples
  .\make-practice.ps1
  ```

Both produce the same challenges:

| File | Trick to spot | Note that teaches it |
|---|---|---|
| `secret.png` | It's **not** a PNG — extension lies, magic bytes are a ZIP | [[file-analysis.ai]] |
| `cat_photo.bin` | A real PNG with a **ZIP appended** to the end | [[file-analysis.ai]] |
| `notes.txt` | **ROT13** flag (`synt{...}`) | [[01-methodology.ai]] |
| `data.b64` | **Base64** flag | [[01-methodology.ai]] |
| `meta.jpg` *(bash only)* | Flag in **EXIF Comment** (needs exiftool to plant) | [[metadata.ai]] |

## Solve them (don't peek until you've tried)

```bash
cd generated
file *                                  # which extensions are lying?
strings -n 5 * | grep -iE 'flag|synt'   # cheap wins
binwalk cat_photo.bin                   # find the appended zip
unzip cat_photo.bin                     # ...extract it
cat notes.txt | tr 'A-Za-z' 'N-ZA-Mn-za-m'   # rot13
base64 -d data.b64                      # base64
exiftool meta.jpg                       # metadata
```

Solutions are in [[solutions.ai]] — but really, try first.

## Warm-up file (already here)

`rot13_note.txt` — a single ROT13 line. Decode it:
```bash
cat rot13_note.txt | tr 'A-Za-z' 'N-ZA-Mn-za-m'
```
