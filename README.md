# ctf-toolkit

**v0.3** — remote-brain-first; full-category tooling (RE/pwn, web, mobile); Android APK triage.

A CTF **forensics triage + AI-evaluation** toolkit that runs on **Kali (WSL2)**. It shells out to
the installed toolset (binwalk, foremost, steghide, zsteg, john/hashcat, pwntools, …) and layers an
AI **brain** on top for triage evaluation and an agentic ReAct loop.

The brain is decoupled from the hands: by default reasoning runs on a large hosted model over an
**OpenAI-compatible gateway**; a **local Ollama** server (e.g. a Mac on the LAN) is the offline
fallback. Kali always executes the actual tools.

```
your Kali (WSL2)                       brain (reasoning only)
┌─────────────────────────┐            ┌──────────────────────────────┐
│ ctf-file   triage        │  prompt →  │ remote gateway (default)     │
│ ctf-eval   triage+eval   │  ────────  │   qwen3.6-35b-a3b            │
│ ai / ai.py one-shot+agent│  ← verdict │ or local Ollama (fallback)   │
└─────────────────────────┘            └──────────────────────────────┘
        runs every tool                        never touches the disk
```

> [!important] Scope
> A hosted ~35B (or local 14B) model is a strong **triage-and-scaffold assistant** with the human
> driving strategy — not an autonomous pwn-solver. The agent compensates with per-turn `thought`,
> small subtasks, verification-before-finish, and mid-run steering.

---

## Install (on Kali / WSL2)

```bash
git clone https://github.com/Imtnk/ctf-toolkit.git ~/ctf-toolkit
cd ~/ctf-toolkit
./install.sh                 # symlinks bin/ctf-file, bin/ctf-eval, and the `ai` launcher onto PATH
```

The Python glue is **stdlib-only** (`urllib`, `json`, `subprocess`); the CTF power comes from the
system tools it shells out to. `install.sh` provisions the full toolset across every competition
category — forensics, RE/pwn, web, crypto, network, and mobile (see **Toolset by category** below).
`requirements.txt` lists the Python libs (pwntools, pycryptodome, z3, PyJWT, beautifulsoup4, …) the
agent's `python_exec` tool draws on.

### Environment

| Var | Default | Meaning |
|---|---|---|
| `CTF_REMOTE_API_KEY` | *(unset)* | **Secret.** Bearer key for the gateway. Store in `~/.config/ctf-toolchain/secrets.env` (chmod 600, **outside the repo**), sourced from `~/.bashrc`/`~/.zshrc`. Never commit it. |
| `CTF_REMOTE_MODEL` | `qwen3.6-35b-a3b` | Remote model id |
| `CTF_REMOTE_BASE_URL` | `https://gateway.9arm.co/v1` | OpenAI-compatible base (`POST {base}/chat/completions`) |
| `CTF_BRAIN` | `remote` | Set to `local` to force the Ollama brain globally |
| `CTF_AI_HOST` | `localhost` | Ollama host for the local brain / fallback (prefer a stable Tailscale name — see *Local Ollama is optional*) |

One-time key setup (paste the real key yourself — it never passes through anyone else):

```bash
mkdir -p ~/.config/ctf-toolchain && chmod 700 ~/.config/ctf-toolchain
printf 'export CTF_REMOTE_API_KEY=%q\n' 'sk-REAL' >> ~/.config/ctf-toolchain/secrets.env
chmod 600 ~/.config/ctf-toolchain/secrets.env
# add to ~/.bashrc and ~/.zshrc:
echo '[ -f ~/.config/ctf-toolchain/secrets.env ] && source ~/.config/ctf-toolchain/secrets.env' >> ~/.bashrc
```

---

## Commands

### `ctf-file` — forensics triage

Runs a battery of forensics tools over a file (type ID, strings, metadata, embedded-file carving,
stego, archive cracking) and prints a report. Recognizes **Android APKs** and auto-decompiles them
(jadx + apktool, manifest via aapt, native-lib strings). Extracted payloads land in `./<file>-work/`.

```bash
ctf-file suspicious.png                 # default triage
ctf-file locked.zip -d hard -c          # deeper dig + cracking tiers
```

### `ctf-eval` — triage **+ AI verdict**

Runs `ctf-file`, then feeds **both** the report and the extracted artifacts to the brain, which
returns a structured verdict (SOLVED / NEEDS_MORE_WORK / INCONCLUSIVE + flag + next steps). A flag
sitting only inside an extracted file still counts as ground truth. Outputs land in `./<file>-work/`
(`triage-report.txt`, `eval-trace.txt`, `eval.json`).

```bash
ctf-eval locked.zip                     # triage + eval with the remote brain (default)
ctf-eval locked.zip -v                  # + stream the model's live thinking to stderr
ctf-eval locked.zip --local             # force local Ollama instead of the remote brain
ctf-eval locked.zip --offline           # skip all models — deterministic heuristic only
ctf-eval locked.zip -- -d hard -c       # everything after `--` is passed to ctf-file
```

| Flag | Meaning |
|---|---|
| *(none)* | Remote brain (if a key is set), else local Ollama, else offline heuristic |
| `-v` / `--verbose` | Stream the model's live thinking/output to stderr (off by default) |
| `--local` | Force local `deepseek-r1:14b` |
| `--fast` | Local `qwen2.5-coder:14b` (faster, no `<think>`) — implies `--local` |
| `--model M` | A specific local Ollama model — implies `--local` |
| `--offline` | Deterministic heuristic only (no model call) |

**Degrade ladder:** remote brain → local Ollama → offline heuristic. Each rung is only tried if the
one above is unavailable or fails. The summary tags the evaluator's **cost**: amber `remote · paid`
vs green `local · free`.

### `ai` — one-shot Q&A + ReAct agent

`ai` (a thin launcher over `ai.py`) opens an interactive menu when run bare, or passes arguments
straight through:

```bash
ai                                      # interactive menu (shows the current brain)
ai "what does XOR with a repeating key look like in ciphertext?"   # one-shot (remote by default)
ai --local "quick question"             # one-shot, forced local
ai agent "what type is ./chal and what are its strings?"           # ReAct agent with tools
```

One-shot sends a single prompt and prints the answer (no tools). Agent mode is the multi-step ReAct
loop below.

#### Agent flags

```bash
ai agent --approve auto "triage ./chal — architecture, protections, interesting strings"
ai agent --dry-run "what would you do with ./chal?"
ai agent --local "…"                    # force the local Ollama brain
ai agent --resume                       # resume the latest (or a specific) .agent/*.jsonl run
```

| Flag | Default | Meaning |
|---|---|---|
| `-m / --model` | brain default | Override with a specific **local** Ollama model id |
| `--local` | off | Force local Ollama instead of the remote gateway |
| `--approve auto` | manual | Skip prompts for non-allowlisted commands |
| `--dry-run` | off | Show planned commands; execute nothing |
| `-v / --verbose` | off | Stream the brain's live thinking. Off by default — a spinner shows progress and only the step actions/results print |
| `--max-steps` | 15 | Steps before the soft-budget pause |
| `--resume [FILE]` | — | Resume latest (or specific) `.agent/*.jsonl` transcript |

The agent is **quiet by default**: each step prints its `thought`, tool call, and result, with a
spinner while the model thinks. Pass `-v` to stream the raw reasoning. Tasks needn't be flag hunts —
a plain request ("list the files here", "identify this binary") finishes as soon as it's answered.
**Ctrl-C** mid-run pauses to steer (type a hint), resume (Enter), or quit (`q`, or Ctrl-C again).

**Selection:** the remote brain is used when a key is present and none of `CTF_BRAIN=local`,
`--local`, or `-m <model>` is in play. With no key it degrades to local `deepseek-r1:14b` (one-time
warning); a remote error at call time falls back to local automatically. Local `dolphin-llama3:8b`
is the refusal fallback.

---

## Tools coverage

Tools `install.sh` provisions, sorted by competition topic (the AI brain shells out to these — it
never solves in its head). **Bold** = added most recently.

| Category | Tools |
|---|---|
| **Digital Forensic** | `ctf-file` triage: binwalk, foremost, exiftool, steghide, stegseek, zsteg, outguess, sleuthkit, volatility3, oletools, pdf/qr/audio |
| **Reverse Eng. & Pwnable** | gdb+gef, radare2/rizin, ghidra, objdump/readelf/nm, checksec, ROPgadget, ropper, **one_gadget**, **patchelf**, **seccomp-tools**, **pwninit**, **strace**/**ltrace**, pwntools, z3, capstone, unicorn, angr |
| **Web Application** | curl, ffuf, gobuster, feroxbuster, wfuzz, sqlmap, nikto, nuclei, whatweb, httpx, burpsuite, zaproxy, **jq**, requests, **PyJWT**, **beautifulsoup4** |
| **Network Security** | tshark, tcpdump, tcpflow, nmap, scapy, wireshark |
| **Cryptography** | openssl, hashcat, john, pycryptodome, sympy, gmpy2, z3 |
| **Mobile Security** | `ctf-file` auto-APK triage: jadx, apktool, dex2jar, aapt, apksigner, adb; **frida-tools**/**objection** for dynamic hooking (needs a device/emulator) |
| **Programming** | python3 (+ the agent's `python_exec`), gcc, nasm, xxd |

Only **SageMath** is intentionally skipped (heavy; install it yourself if a challenge needs lattice /
advanced-ECC crypto). Everything else is handled by `install.sh`.

**Approach notes.** *Pwn/RE:* the brain triages (mitigations via `checksec`, function/vuln spotting,
gadget listing) and scaffolds a pwntools script with a local/remote toggle — pwntools does the offset
math, `pwninit`/`one_gadget` handle supplied-libc leaks; a human (or a tight `python_exec` loop) drives
the final exploit. *Web:* fingerprint (whatweb/httpx) → discover (ffuf) → **hypothesis-first** targeted
request for the bug class (SQLi/SSTI/IDOR/JWT/LFI/SSRF/deserialization), using `requests` for stateful
chains; fall back to sqlmap/nuclei only when a manual hypothesis stalls. *Mobile (lowest priority):*
static only — `ctf-file` auto-decompiles the APK; grep the jadx/smali output for flags, secrets, and
endpoints. Add frida/objection + an emulator only for runtime-hooking challenges.

## Agent loop (ReAct)

Each turn: **model → JSON `{thought, tool, args}` → approval → execute → observe → repeat**

### Tools

| Tool | Approval tier | Purpose |
|---|---|---|
| `run_shell(cmd)` | allowlist / ask / deny | Shell command; streams output line-by-line |
| `python_exec(code)` | ask (denylist scanned) | Python snippet; pwntools/pycryptodome/z3 |
| `read_file(path)` | auto (read-only) | Text file, 8 KB cap |
| `write_file(path, text)` | always diff+confirm | Diff shown before any write |
| `list_dir(path)` | auto | Directory listing with sizes |
| `file_info(path)` | auto | `file` command + size + SHA-256 |
| `hexdump(path, n)` | auto | First n bytes, hex+ASCII |
| `strings(path, min_len)` | auto | Printable strings |
| `http_request(method, url, …)` | ask | Web requests via urllib |
| `finish(answer)` | — | End loop; triggers verification first |

### Approval tiers

1. **auto** (allowlist) — `file`, `strings`, `ls`, `cat`, `grep`, `hexdump`, `binwalk` (no `-e`), `base64`, `openssl` inspect ops, … — runs silently
2. **ask** — everything else; `[y] once / [a] always / [N] deny` ("a" learns a session rule)
3. **deny** (denylist) — `rm -rf`, `sudo`, `curl|sh`, `dd of=/dev/`, fork bombs, `shred` — hard-blocked even under `--approve auto`

### Guards

- **Repeat detection** — duplicate tool+args → "you already ran this", skipped
- **No-progress heuristic** — 3 consecutive empty/duplicate observations → pause prompt
- **Soft budget** — at `--max-steps`: continue 10 more / stop / inject hint / enter answer
- **Mid-run steering** — type + Enter anytime; injected as `[user hint]` without restarting
- **Verification before finish** — proposed answer goes through a separate classification call
- **Refusal fallback** — clean-context classifier detects refusals → auto-switch to `dolphin-llama3:8b`
- **Context management** — pinned facts (task, flag format, confirmed findings) survive truncation; history bounded by the **active** model's context window

### Transcript + resume

Every step is appended to `.agent/run-YYYYMMDD-HHMMSS.jsonl`. `--resume` reloads history and
continues; the system prompt is rebuilt fresh (catalog changes take effect).

---

## Local Ollama is optional

The default brain is the **remote gateway**, so with a valid API key the toolkit works fully with
**no local model at all** — no Mac, no Ollama, no LAN. A local Ollama is only a *fallback*.

### Remote brain only (just an API key)

The minimal setup, and all most people need. Put three vars in
`~/.config/ctf-toolchain/secrets.env` (chmod 600, sourced from your shell rc):

```bash
export CTF_REMOTE_API_KEY=sk-...                         # your key (the only secret)
export CTF_REMOTE_BASE_URL=https://gateway.9arm.co/v1    # any OpenAI-compatible endpoint
export CTF_REMOTE_MODEL=qwen3.6-35b-a3b                  # a model that endpoint serves
```

With this alone: `ctf-eval <file>`, `ai "…"`, and `ai agent "…"` all run on the remote brain, and
`ctf-eval` degrades to a **deterministic offline heuristic** if a remote call ever fails — still no
local model required. Only these *fallback* rungs use a local Ollama, and each is silently skipped
when it's absent: the agent's remote-error retry, the refusal→`dolphin` switch (agent path only),
and `ai.py`'s one-shot on remote failure. `CTF_AI_HOST` can stay unset (defaults to `localhost`).

### Optional local Ollama fallback (e.g. a Mac), reached over Tailscale

If you *do* run Ollama on another box, point Kali at it and set `CTF_BRAIN=local` (or pass `--local`).
Prefer the host's **Tailscale MagicDNS name** over a Wi-Fi DHCP lease so the address never drifts:

```bash
# on the Ollama host (e.g. the Mac): serve on the tailnet, not just localhost
launchctl setenv OLLAMA_HOST 0.0.0.0     # then restart Ollama (macOS app: Settings → "Expose on the network")
tailscale up                             # host must be on the tailnet

# on Kali (WSL2): join the same tailnet with the helper scripts, then use the stable name
scripts/tailscale-start.sh               # starts tailscaled quietly + `tailscale up` (login once)
export CTF_AI_HOST=my-macbook            # the host's MagicDNS name (stable), or its 100.x tailnet IP
ctf-eval locked.zip --local
scripts/tailscale-stop.sh                # disconnect + stop the daemon when you're done
```

**Run tailscaled quietly.** In WSL2 (no systemd) `tailscaled` is a foreground daemon — start it with
`&` and its logs stream into your terminal. `scripts/tailscale-start.sh` detaches it and redirects
logs to `/var/log/tailscaled.log`. Note that `tailscale down` only disconnects the *node*; the daemon
keeps running (and logging), so use `scripts/tailscale-stop.sh` to actually stop it.

| Script | What it does |
|---|---|
| `scripts/tailscale-start.sh` | Start tailscaled detached (logs → file), then `tailscale up --hostname=kali-wsl`. Idempotent. `TS_HOSTNAME=` overrides the name. |
| `scripts/tailscale-stop.sh` | `tailscale down` **and** stop the daemon so nothing lingers on your terminal. |

To bring the daemon up silently on every WSL launch without systemd, add to `/etc/wsl.conf` (then
`wsl --shutdown`); you still run `tailscale up` once to log in:

```ini
[boot]
command = /usr/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock >/var/log/tailscaled.log 2>&1 &
```

| Model | Role |
|---|---|
| `deepseek-r1:14b` | Local primary — chain-of-thought reasoning |
| `qwen2.5-coder:14b` | Coding-focused (`--fast`) |
| `dolphin-llama3:8b` | Uncensored refusal fallback (agent path only) |

Scripts in `scripts/` (`switch-model.sh`, `start-ollama.sh`, `test-server.sh`, …) manage an Ollama
host. Always pass `"num_ctx": 8192`+ in raw API calls — Ollama defaults to 2048 on some builds and
truncates long replies; the tools here already set it.

---

## Layout

```
ctf-toolkit/
  bin/
    ctf-file         # forensics triage (bash)
    ctf-eval         # triage + AI verdict (python; reuses agent/config.py)
  ai.py              # one-shot + `agent` subcommand
  ai-ui.py           # `ai` launcher: menu + passthrough
  agent/
    config.py        # host / models / remote-brain settings (single source of truth)
    llm.py           # brain router: remote gateway (SSE) vs Ollama /api/chat
    protocol.py      # JSON extractor (<think> tags, ```json fences, nested braces)
    tools.py         # tool registry (streaming run_shell + python_exec)
    approval.py      # three-tier gate + session allowlist + write-diff
    loop.py          # ReAct loop (guards, steering, truncation, transcript)
    transcript.py    # .agent/*.jsonl write + load_resume
    refusal.py       # clean-context refusal classifier + dolphin fallback
    context.py       # pinned-facts + maybe_truncate
  scripts/           # Ollama host helpers
  examples/          # sample runs
  docs/              # forensics notes
  install.sh · requirements.txt
```
