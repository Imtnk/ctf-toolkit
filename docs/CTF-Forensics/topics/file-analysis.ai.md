# File Analysis & Carving

The foundation of all forensics. If you only master one note, master this one.

## Magic bytes — the file's real identity

Every file type starts with a signature. `file` reads these; so should you. Common ones (view with `xxd file | head -1`):

| Hex header | ASCII | Type |
|---|---|---|
| `89 50 4E 47` | `.PNG` | PNG image |
| `FF D8 FF` | | JPEG image |
| `47 49 46 38` | `GIF8` | GIF image |
| `42 4D` | `BM` | BMP image |
| `50 4B 03 04` | `PK..` | ZIP (also .docx, .jar, .apk, .odt) |
| `1F 8B` | | GZIP |
| `52 61 72 21` | `Rar!` | RAR |
| `25 50 44 46` | `%PDF` | PDF |
| `7F 45 4C 46` | `.ELF` | ELF executable / core dump |
| `4D 5A` | `MZ` | Windows PE (.exe/.dll) |
| `D0 CF 11 E0` | | Old MS Office (.doc/.xls) |
| `55 AA` at offset 510 | | MBR boot sector (disk image) |

**Trick #1 — wrong extension.** A file called `cat.jpg` whose header is `89 50 4E 47` is actually a PNG. Rename it and move on. Always trust `file`, never the extension.

**Trick #2 — corrupted/edited header.** If `file` says "data" but you expected a PNG, check whether the first bytes were zeroed or altered. Fix them in a hex editor and the image opens.

## strings — the workhorse

```bash
strings -n 6 file.bin                 # printable runs of length >= 6
strings -n 6 file.bin | grep -i flag  # go for the flag
strings -e l file.bin | grep -i flag  # UTF-16LE (Windows text)
strings -a file.bin                   # scan the WHOLE file, not just data sections
```

When on Windows without WSL, use the vault's PowerShell equivalent:
```powershell
E:\CTF\scripts\extract_strings.ps1 -Path .\file.bin -MinLen 6 | Select-String flag
```

## Appended / embedded data

A favorite CTF trick: glue a second file onto the end of a valid one. The image still opens; the payload rides along.

```bash
binwalk file.png            # lists signatures found anywhere in the file
binwalk -e file.png         # extracts them into _file.png.extracted/
foremost -i file.png -o carved/   # alternative carver
unzip file.png              # sometimes a ZIP is just appended — this works directly!
```

If `binwalk` shows a Zip archive at some offset, you can also carve manually:
```bash
dd if=file.png of=payload.zip bs=1 skip=<offset>
```

## Concatenation & polyglots

- `cat a.jpg b.zip > poly.jpg` → opens as image, unzips as archive. Detect with `binwalk`.
- PDFs, GIFs, and ZIPs are common polyglot hosts because their format tolerates trailing/leading junk.

## Compression layers

Re-run `file` after every extraction. Chains like `.zip → .tar.gz → disk.img → deleted file` are normal. Handy:
```bash
unzip x.zip ; tar xzf x.tar.gz ; gunzip x.gz ; 7z x x.7z
```

## Password-protected archives

```bash
zip2john secret.zip > hash.txt
john hash.txt --wordlist=/usr/share/wordlists/rockyou.txt
```
Same pattern with `pdf2john`, `rar2john`, `office2john`.

## Practice

See `examples/` — the generator makes a "wrong extension" file and an "appended zip" file for you to identify. → [[README.ai]]
