# scripts/ — automated triage

## `ctf-file` — one-command first-pass triage

Runs the whole [[01-methodology.ai]] reflex sweep on a single file: identify → strings → metadata → carving → steganography → password guessing → auto-decode.

**Installed in Kali WSL** at `~/bin/ctf-file`, on your `PATH` with an alias (added to `~/.bashrc`). `ctf-file.sh` here is the version-controlled copy — if you edit one, sync the other:
```bash
cp ~/bin/ctf-file /mnt/d/obsidian-vault/CTF-Forensics/scripts/ctf-file.sh   # WSL -> vault
cp /mnt/d/obsidian-vault/CTF-Forensics/scripts/ctf-file.sh ~/bin/ctf-file && chmod +x ~/bin/ctf-file  # vault -> WSL
```

### Usage
```bash
ctf-file <file>              # full read-only sweep; prompts before heavy cracking (interactive)
ctf-file <file> -d hard      # non-interactive: escalate straight to rockyou + john rules
ctf-file <file> -c           # non-interactive: run the wordlist tier automatically
ctf-file <file> -n           # skip auto-extraction (big disk/memory images)
ctf-file <file> -v           # verbose: echo every underlying tool command as it runs
ctf-file <file> -w list.txt  # custom wordlist instead of rockyou for medium/hard
ctf-file -h                  # full manual (man-page style)
```
`-h` prints a complete manual (NAME / SYNOPSIS / DESCRIPTION / OPTIONS / SECTIONS / EXAMPLES).

### Flag format (what it searches for)
The prefix(es) hunted for (the part before `{`) are resolved in priority order:
1. `CTF_FLAG_FORMAT` env var — `CTF_FLAG_FORMAT=ctf ctf-file chall` (comma/space separated for several)
2. `~/.config/ctf-file/format` — one prefix per line, `#` comments allowed
3. built-in default: `flag ctf key`

"Just the beginning" is enough — put `ctf` to hunt `ctf{...}`. The **rot13 form of each prefix is derived automatically** (so `flag`→`synt`, `ctf`→`pgs`), meaning a rot13-encoded flag is still detected in STRINGS and AUTO-DECODE. Edit the file for the event you're playing:
```bash
printf 'ctf\n' > ~/.config/ctf-file/format      # this event uses ctf{...}
```

### Verbose / command log
`-v` echoes each real tool command (`file`, `strings … | grep`, `binwalk -e`, `zip2john`, `john …`, `stegseek`, …) as it runs. **The full command list is always saved to `<file>-work/commands.log`** (even without `-v`) so any run is reproducible. Commands only — the spinner loop is deliberately not traced (no `set -x` noise).

### What each section does
| Section | Tools | Notes |
|---|---|---|
| IDENTIFY | `file`, `stat`, `xxd` | real type + magic bytes (ignores the extension) |
| STRINGS | `strings` (ASCII + UTF-16LE) | greps for `flag{`/`synt{`/`ctf{`/`key{` |
| METADATA | `exiftool` | EXIF/doc props (filesystem noise filtered out); flags flag-lines |
| CARVING | `binwalk`, `unzip` | lists + auto-extracts embedded files; greps carved data for a flag |
| STEGANOGRAPHY | `pngcheck`, `zsteg`, `steghide` | **only runs on images/audio** (branches on `file` type) |
| PASSWORD GUESSING | `*2john`+`john`, `steghide`, `stegseek` | common list first (always), then escalate — see below |
| AUTO-DECODE | `tr`, `base64` | ROT13/base64 on flag-like strings |
| SUMMARY | — | every finding collected in one green list |

### TCTT coverage additions (2026-07-23)
Driven by past **Thailand Cyber Top Talent** forensics/network challenges, `ctf-file` now
branches on more real file types (all bounded + `have`-guarded, so the piped report stays
clean for `ctf-eval`). Two new sections (`TOTAL` bumped 9→11):

| New / extended | Type | Tools | What it does |
|---|---|---|---|
| **NETWORK** (new section) | pcap/pcapng | `capinfos`, `tshark`, `tcpflow` | protocol hierarchy, HTTP requests, **cleartext creds** (http-basic/ftp), `--export-objects http`, full TCP-stream reassembly → flag-grep |
| **CARVING** (extended) | pdf | `pdfinfo`/`pdfimages`/`pdfdetach` | embedded images + attachments → flag-grep; also `foremost` fallback when binwalk carves nothing |
| **STEGANOGRAPHY** (extended) | image | `zbarimg` | **QR/barcode** decode |
| **STEGANOGRAPHY** (extended) | jpeg | `outguess` | empty-key extraction |
| **STEGANOGRAPHY** (extended) | audio | `sox` | **spectrogram** PNG written to the work dir (flags hidden in the spectrum) |
| **PASSWORD GUESSING** (extended) | office | `olevba` | VBA **macro dump** + flag-grep |
| **DEEP ANALYSIS** (new, `-H/--heavy`) | disk image | `mmls`/`fls`/`icat` | partition table + filesystem walk (offset auto-picked from mmls, GPT/Extended-safe) |
| **DEEP ANALYSIS** (new, `-H/--heavy`) | memory dump | Volatility3 (`vol`/`vol.py`) | `windows.info`/`pslist`/`cmdline`/`filescan` |

`--heavy` is **off by default** so the fast path stays cheap and bounded for `ctf-eval`;
without it, disk/memory images are only *detected* and suggested commands printed. Untrusted
decoded text (QR payloads, packet fields) is run through a `scrub` helper (strips ANSI/control
bytes, flattens newlines, caps length) before printing — no injection into the report.

**Tool install (Kali):** `sudo apt-get install -y tshark tcpflow poppler-utils zbar-tools
sleuthkit foremost testdisk sox python3-oletools outguess stegseek pngcheck` · `gem install
zsteg` · `pipx install volatility3`. Verified live 2026-07-23 on `~/ctf-challenges/tctt/`:
NETWORK (`flag{pcap_http_object_recovered}` + `admin:hunter2` cred), zsteg LSB
(`flag{zsteg_lsb_channel_ok}`), disk `--heavy` (fls lists `flag.txt`), audio spectrogram,
memory negative-test (graceful), `-n` gating, 0 ANSI/0 CR when piped, all existing
regressions green. A code-review agent found 10 issues (memory heuristic matching "image
data", mmls "Extended"/GPT offset bug, `-n` not honoured by pcap/pdf, unsanitised QR/cred
output, `pdfdetach -saveall` dir, unbounded foremost/pdf listings, `vol` name, missing
`logcmd`) — **all fixed and re-verified**.

Built-in common passwords: *(empty)*, `password`, `123456`, `admin`, `secret`, `flag`, `letmein`, `qwerty`, `dragon`, `root`, `toor`, `ctf`, …, the filename. Edit the `COMMON=(...)` array to add your own.

### Password guessing — always-common-then-escalate
1. The **cheap built-in common list is always tried first**, at every tier, for both encrypted archives (zip/rar/pdf/office) and steghide media. Weak passwords fall here instantly — a default `ctf-file locked.zip` cracks and shows the flag with no flags needed.
2. If that misses, ctf-file **escalates to rockyou**:
   - **Interactive terminal, no `-d`:** prompts `Try MEDIUM (rockyou)? [y/N]`, then `Try HARD (rockyou + rules)?`. Answers are read from `/dev/tty`.
   - **`-d medium|hard` or `-c`:** runs that tier automatically, no prompt.
   - **Piped / non-interactive (e.g. `ctf-eval`):** never prompts — saves the hash and tells you to re-run with `-c`.
3. A cracked **zip is auto-extracted** with the found password and its `flag{…}` shown (other archive types report the password to extract manually).

### Design choices
- **Read-only on your file.** Anything extracted goes into `./<file>-work/`.
- **Missing tools are skipped**, not fatal — every tool is guarded with `command -v`.
- **Extraction is on by default** (binwalk `-e` + zip auto-unzip); disable with `-n`.
- **Never blocks on a prompt** — encrypted archives are probed with `</dev/null`; escalation prompts only fire when stdout **and** stdin are terminals.
- **Per-run john pot** — cracking uses a fresh `<file>-work/john.pot` (cleared each run), so a password cached in the global `~/.john/john.pot` from an earlier crack never makes a weaker tier falsely report success. A tier "cracks" only if *its* wordlist found it this run.

### Colour & progress display
Colour-coded results — **cyan** headers, **green** flags/successes, **yellow** skips/warnings, **dim** "nothing found" — plus a **live 9-step progress bar** (`[6/9] [################......] PASSWORD GUESSING`) and a **spinner** during slow ops (binwalk extraction, `john`). Colour is stdout-TTY-gated; the bar/spinner are stderr-TTY-gated. Piping the report anywhere yields clean plain text; `NO_COLOR=1` forces everything off.

### Verified against the test challenges (`~/ctf-challenges/test/`)
Self-test files live in Kali (created for exercising each path — not in the vault):
- `secret_image.png` → METADATA surfaces `flag{metadata_never_lies}`
- `encoded.txt` → AUTO-DECODE base64 → `flag{base64_decoded_me}`
- `locked.zip` → common-list crack (`dragon`), auto-extracted → `flag{cracked_the_zip}`
- `hard_locked.zip` → **needs `-d hard`**: password `Hunterhunter` (jumbo rules mangle the rockyou word `hunter`). Not in the common list or plain rockyou, so easy/medium fail; hard cracks in ~6 s → `flag{hard_mode_needs_john_rules}`.

Quick self-test: `for f in ~/ctf-challenges/test/*; do ctf-file "$f"; done`  (each ends with a green SUMMARY; `hard_locked.zip` needs `-d hard` non-interactively, or answer the escalation prompts).

> **Wordlist note:** rockyou ships gzipped and `/usr/share/wordlists/` isn't user-writable, so `resolve_rockyou` decompresses it once into `~/wordlists/rockyou.txt` (writable). The `jumbo` ruleset name is case-insensitive (`--rules=Jumbo` == `jumbo`).

### Security & robustness hardening (post-review, 2026-07-21)
A code-review agent audited the tool; the applied fixes:
- **No `--run-as=root`** fallback for `binwalk -e` on untrusted files (RCE/zip-slip class, cf. CVE-2022-4510). Extraction stays default-on but symlinks whose target escapes `<file>-work/` are flagged, and all flag-greps read **regular files only** (`flagtok_in`, no symlink-following) so nothing outside the work dir is ever trusted as a flag.
- **Leading-dash filenames** (`-x.jpg`) are normalized to `./-x.jpg` so they can't be parsed as tool options.
- **`<file>-work/` is cleared at the start of each run** — no stale flag from a previous different file with the same basename, and re-extraction works.
- **stegseek** now extracts with `-xf <work>/stegseek.out` and greps the payload (previously the recovered file was dropped in CWD and its flag missed).
- **`pdf2john`/`office2john`** resolved from candidate names (`pdf2john.pl`, `office2john.py`) so Kali's naming doesn't skip cracking.
- **PNG/GIF no longer run the steghide passphrase loop** (steghide only supports JPEG/BMP/WAV).
- Smaller: `zsteg -a` runs once (not twice), rockyou decompress is temp-then-`mv`, empty-metadata prints nothing, steghide extract `rm -f`s its target first.
- **Config parser** handles a `format` file whose last line has no trailing newline (`read … || [ -n "$line" ]`).

### Extending it
It's a plain bash script — add a section by copying the `sec "NAME"` pattern (each `sec` call also advances the progress bar; bump `TOTAL` if you add sections). Good next additions: `pdfdetach`/`pdfimages` for PDFs, `tshark` summary for pcaps, `vol windows.info` for memory dumps.

---

## `ctf-eval` — triage + local-AI evaluation (Python, v1.0)

`ctf-eval.py` (installed as `~/bin/ctf-eval`) runs `ctf-file`, then sends the report to the Mac's Ollama server and returns a **structured verdict**. It talks to Ollama directly — no `ai.py` dependency. Full setup notes live in `local-ai-ctf-setup.ai.md` §10.

```bash
ctf-eval <file>                 # triage + eval with deepseek-r1:14b (default)
ctf-eval <file> --fast          # qwen2.5-coder:14b (faster, no <think> trace)
ctf-eval <file> --model NAME    # any Ollama model
ctf-eval <file> --offline       # deterministic verdict from the report alone (no Mac)
ctf-eval <file> -- -d hard -c   # args after `--` pass through to ctf-file
```

**Forced reply schema** (parsed, not free text): `VERDICT` (SOLVED / NEEDS_MORE_WORK / INCONCLUSIVE) · `FLAG` · `CONFIDENCE` · `WHY` · `NEXT_STEPS` · `COMMANDS`.

**Outputs** (in `<file>-work/`): `triage-report.txt` (ground truth), `eval-trace.txt` (raw reply incl. deepseek `<think>`), `eval.json` (version-stamped verdict + model + timestamp). **Exit code** = verdict: `0` solved, `3` needs work, `4` inconclusive.

**Guardrails:** a claimed flag must appear **verbatim** in the report or it's marked `UNVERIFIED` and a `SOLVED` is downgraded (anti-hallucination); a flagless `SOLVED` abstains; a flag the model missed but that's in the report still wins; deepseek `<think>` is split off; refusals auto-retry once on dolphin; requests carry `keep_alive=30m`; if the Mac is unreachable it falls back to a deterministic offline heuristic. Streamed reasoning → stderr (TTY only), clean `=== EVAL ===` summary → stdout.

> **Verified live 2026-07-21:** full round-trip against the Mac's Ollama — deepseek-r1:14b (`SOLVED`/verified flag + a `NEEDS_MORE_WORK` with parsed next-steps), reasoning captured to `eval-trace.txt`, `--fast` qwen fallback, offline heuristic, schema parse, and exit codes all confirmed on `~/ctf-challenges/test/`. The Mac's IP is DHCP (was `.124`, now `192.168.1.11`); `ctf-eval` defaults to `.11` and honours `CTF_AI_HOST` for drift.
