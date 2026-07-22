# ctf-file

**One-command first-pass forensics triage for a single file.** Point it at a mystery
file from a CTF and it runs the whole recon reflex — identify → strings → metadata →
carving → steganography → password guessing → auto-decode — then prints a colour-coded
report ending in a **SUMMARY** of everything that looks like a flag.

It is **read-only on your file**; anything it extracts is written to `./<file>-work/`.
Every external tool is optional — missing tools are skipped, never fatal.

```
$ ctf-file locked.zip
=== IDENTIFY ===
  type : Zip archive data, at least v2.0 to extract
=== PASSWORD GUESSING (start: common list) ===
  >> password FOUND: 'dragon'  (zip)
  >> flag: flag{cracked_the_zip}
=== SUMMARY ===
  1 finding(s):
   * ARCHIVE zip (pw=dragon): flag{cracked_the_zip}
```

---

## Requirements

- **Kali Linux** (tested on base/rolling). It's plain `bash` + standard CLI forensics
  tools, so it also runs on Debian/Ubuntu/WSL with the same packages installed.
- `bash` 4+, and the GNU coreutils that ship with Kali (`file`, `stat`, `xxd`,
  `strings`, `tr`, `base64`, `find`, `xargs`, `sort`, `sed`, `awk`).

The forensics tools it *drives* (all optional — each is guarded, and skipped with a
note if absent) are installed for you by `install.sh`:

| Tool | Package (Kali) | Used for |
|------|----------------|----------|
| `file`, `xxd`, `strings` | `file`, `xxd`, `binutils` | identify / magic bytes / strings |
| `exiftool` | `libimage-exiftool-perl` | metadata |
| `binwalk` | `binwalk` | carving / embedded files |
| `unzip` | `unzip` | zip extraction |
| `john` (+ `zip2john`, `rar2john`, `pdf2john.pl`, `office2john.py`) | `john` | archive password cracking |
| `steghide`, `stegseek` | `steghide`, `stegseek` | JPEG/BMP/WAV stego + passphrase cracking |
| `zsteg` | `gem install zsteg` (needs `ruby`) | PNG/BMP LSB stego |
| `pngcheck` | `pngcheck` | PNG structure |
| rockyou wordlist | `wordlists` | medium/hard cracking tiers |

> **Base Kali note:** a minimal (`kali-linux-core`) install does **not** ship most of
> these. Run `install.sh` (below) — it installs everything via `apt` + one `gem`.

---

## Install

```bash
git clone <this-repo-url> ctf-file
cd ctf-file
./install.sh
```

`install.sh`:
1. `sudo apt-get install`s the packages in the table above (and `wordlists`),
2. `gem install zsteg` (installs `ruby` first if needed),
3. copies the `ctf-file` script to `~/.local/bin/ctf-file` (or `~/bin`) and `chmod +x`,
4. makes sure that directory is on your `PATH` (adds a line to `~/.bashrc` if missing).

Open a new shell (or `source ~/.bashrc`) and `ctf-file -h` should print the manual.

### Manual install (no script)

```bash
sudo apt-get update
sudo apt-get install -y file binutils xxd binwalk libimage-exiftool-perl unzip \
                        john steghide stegseek pngcheck ruby wordlists
sudo gem install zsteg

install -Dm755 ctf-file ~/.local/bin/ctf-file
# ensure ~/.local/bin is on PATH:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

You can also just run it in place without installing: `./ctf-file <file>`.

---

## Usage

```
ctf-file <file> [-d easy|medium|hard] [-c] [-n] [-v] [-w wordlist] [-h]
```

```bash
ctf-file suspicious.bin        # full read-only sweep; prompts before heavy cracking
ctf-file locked.zip            # common-list crack cracks a weak password instantly
ctf-file photo.jpg -d hard     # non-interactive: escalate straight to rockyou + john rules
ctf-file dump.raw -n           # skip auto-extraction (big disk/memory image)
ctf-file chall.png -v          # verbose: echo every underlying tool command as it runs
ctf-file chall.png -w list.txt # use a custom wordlist instead of rockyou
ctf-file -h                    # full man-page style manual
```

### Options

| Option | Meaning |
|--------|---------|
| `-d easy\|medium\|hard` | Force the cracking effort and skip the interactive prompts. **easy** = built-in common list only (instant); **medium** = common list then rockyou; **hard** = common list then rockyou + john mangling rules. |
| `-c` | Non-interactive escalation: run the wordlist tier automatically (pairs with `-d`). |
| `-n` | Don't auto-extract embedded files (skip `binwalk -e` and zip extraction). |
| `-v`, `--verbose` | Echo every underlying tool command as it runs. |
| `-w <path>` | Use this wordlist instead of rockyou for medium/hard. |
| `-h`, `--help` | Show the full manual. |

If `-d` is omitted and you're at a terminal, `ctf-file` tries the common list first, then
**prompts** (`y/N`, read from `/dev/tty`) before escalating to rockyou, then to rockyou +
rules. Piped or non-interactive runs never prompt — they save the hash and tell you to
re-run with `-c`.

---

## Flag format — what it searches for

The prefix(es) it hunts (the part before `{`) are resolved in priority order:

1. **`CTF_FLAG_FORMAT`** env var — `CTF_FLAG_FORMAT=ctf ctf-file chall` (comma/space
   separated for several).
2. **`~/.config/ctf-file/format`** — one prefix per line, `#` comments allowed.
3. Built-in default: `flag ctf key`.

"Just the beginning" is enough — put `ctf` to hunt `ctf{...}`. The **rot13 form of each
prefix is derived automatically** (`flag`→`synt`, `ctf`→`pgs`), so a rot13-encoded flag is
still detected in STRINGS and AUTO-DECODE.

```bash
mkdir -p ~/.config/ctf-file
printf 'ctf\n' > ~/.config/ctf-file/format      # this event uses ctf{...}
```

---

## What each section does

| Section | Tools | Notes |
|---------|-------|-------|
| **IDENTIFY** | `file`, `stat`, `xxd` | real type + magic bytes (ignores the extension) |
| **STRINGS** | `strings` (ASCII + UTF-16LE) | greps for `flag{`/`synt{`/`ctf{`/`key{` |
| **METADATA** | `exiftool` | EXIF / doc properties (filesystem noise filtered) |
| **CARVING** | `binwalk`, `unzip` | lists + auto-extracts embedded files; greps carved data |
| **STEGANOGRAPHY** | `pngcheck`, `zsteg`, `steghide` | **only runs on images/audio** |
| **PASSWORD GUESSING** | `*2john` + `john`, `steghide`, `stegseek` | common list first, then escalate |
| **AUTO-DECODE** | `tr`, `base64` | ROT13 / base64 on flag-like strings |
| **SUMMARY** | — | every finding collected in one list |

Password guessing always tries a cheap built-in **common list first** (empty, `password`,
`123456`, `dragon`, `flag`, the filename, …), at every tier. Only if that misses does it
escalate to rockyou (automatically with `-d`/`-c`, or by prompting interactively). A
cracked **zip is auto-extracted** and its flag shown.

---

## Output & exit status

- Report on **stdout**; the progress bar + spinner on **stderr** (interactive terminals only).
- Everything extracted goes to `./<file>-work/`, including `commands.log` — the full list
  of every real command the run issued (always saved, reproducible).
- **Exit 0** on success, **1** on a usage error / missing file.
- Colour, the progress bar and prompts are TTY-gated: piping the output anywhere
  (`ctf-file chall.png | less`, into another tool, or to a file) yields clean plain text.
  `NO_COLOR=1` forces colour off.

---

## Safety notes

- **Read-only on the input.** All writes go to `./<file>-work/`, which is cleared at the
  start of each run.
- **Untrusted extraction is guarded.** `binwalk -e` drives external extractors on
  attacker-controlled data (RCE / zip-slip class, cf. CVE-2022-4510), so it is **never**
  run as root / with `--run-as=root`. Extracted symlinks whose target escapes the work dir
  are flagged and ignored; all flag-greps read **regular files only**, so nothing outside
  the work dir is ever trusted as a flag. Still: run it as a normal user, ideally in a VM
  or throwaway directory when triaging genuinely untrusted files.

---

## Extending it

It's a single self-contained bash script. Add a section by copying the `sec "NAME"`
pattern (each `sec` call also advances the progress bar — bump `TOTAL` if you add one).
Good next additions: `pdfimages`/`pdfdetach` for PDFs, `tshark` summary for pcaps,
`volatility` for memory dumps.

---

## License

MIT — see [LICENSE](LICENSE).
