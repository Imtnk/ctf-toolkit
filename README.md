# CTF Toolchain — Mac Model Server

This Mac (M3 Pro, 18 GB) runs **Ollama** and serves models over the LAN to a Kali WSL2 box
that runs the actual CTF tooling.

> [!important] Scope
> A 14B local model is a strong **triage-and-scaffold assistant** with the human driving strategy —
> not an autonomous pwn-solver. It loses the thread over long, messy contexts and pattern-matches
> the wrong exploit class without correction. The agent compensates with per-turn `thought`,
> small subtasks, verification-before-finish, and mid-run steering. README claims match that ceiling.

> [!success] Status (2026-07-21)
> All six implementation phases complete. One-shot and agent modes verified.

---

## Models

| Model | Role | Size |
|---|---|---|
| `deepseek-r1:14b` | **Primary** — chain-of-thought reasoning, CTF triage | ~9 GB |
| `qwen2.5-coder:14b` | Coding-focused alternative | ~9 GB |
| `dolphin-llama3:8b` | Uncensored fallback (auto-triggered on refusal) | ~5 GB |
| `nomic-embed-text` | Embeddings (pre-existing) | 274 MB |

Only one 14B model fits in RAM alongside OS headroom. Use `switch-model.sh` to swap.

---

## Quick start

```zsh
brew services list | grep ollama     # Ollama runs as a launchd service (auto-starts at login)
curl -s http://localhost:11434       # → "Ollama is running"
ipconfig getifaddr en0               # LAN IP for Kali (currently 192.168.1.11; DHCP — may drift)
```

---

## `ai.py` — one-shot and agent modes

### `ai` — menu + shortcut

`ai-ui.py` is a thin launcher aliased to **`ai`** (in `~/.bashrc` and `~/.zshrc`). Bare
`ai` opens an interactive menu (ask / run agent / resume, with toggles for local-vs-remote
brain, approve-auto, and dry-run); any arguments pass straight through to `ai.py`:

```zsh
ai                          # interactive menu (shows the current brain)
ai "find the vulnerability" # one-shot passthrough
ai agent "triage ./chal"    # agent passthrough (all ai.py flags work)
```

### One-shot (backward-compatible)

```zsh
echo "solve this RSA: n=... e=... c=..." | python3 ai.py
cat challenge.py | python3 ai.py "find the vulnerability"
python3 ai.py "what does XOR with a repeating key look like in ciphertext?"
```

Sends a single prompt to Ollama and prints the response. No tools, no loop.

### Agent mode — ReAct loop with tools

```zsh
python3 ai.py agent "what type is ./chal and what are its strings?"
python3 ai.py agent --approve auto "triage ./chal — architecture, protections, interesting strings"
python3 ai.py agent --dry-run "what would you do with ./chal?"
python3 ai.py agent -m dolphin "exploit the vuln in ./vuln.py"
cat chal.py | python3 ai.py agent "find and explain the vulnerability"

# Resume a crashed or interrupted run
python3 ai.py agent --resume
python3 ai.py agent --resume .agent/run-20260721-143022.jsonl
```

| Flag | Default | Meaning |
|---|---|---|
| `-m / --model` | brain default | Override with a specific **local** Ollama model id |
| `--local` | off | Force the local Ollama brain instead of the remote gateway |
| `--approve auto` | manual | Skip prompts for non-allowlisted commands |
| `--dry-run` | off | Show planned commands; execute nothing |
| `--max-steps` | 15 | Steps before soft-budget prompt |
| `--resume [FILE]` | — | Resume latest (or specific) `.agent/*.jsonl` transcript |

---

## Brain: remote gateway vs local Ollama

The agent's **brain** (reasoning) is decoupled from its **hands** (`agent/tools.py`, which run
real subprocesses). By default the brain is a large hosted model on an **OpenAI-compatible
gateway**; the local machine still executes every tool. A local `dolphin-llama3:8b` remains the
refusal fallback.

| Env var | Default | Meaning |
|---|---|---|
| `CTF_REMOTE_API_KEY` | *(unset)* | **Secret.** Bearer key for the gateway. Sourced from `~/.config/ctf-toolchain/secrets.env` (chmod 600, outside this repo). Never commit it. |
| `CTF_REMOTE_MODEL` | `qwen3.6-35b-a3b` | Remote model id |
| `CTF_REMOTE_BASE_URL` | `https://gateway.9arm.co/v1` | OpenAI-compatible base (`POST {base}/chat/completions`) |
| `CTF_BRAIN` | `remote` | Set to `local` to force the Ollama brain globally |
| `CTF_AI_HOST` | `localhost` | Ollama host for the local brain / fallback |

**Selection:** remote is used when a key is present and neither `CTF_BRAIN=local`, `--local`, nor
`-m <model>` is in play. With no key it degrades to local `deepseek-r1:14b` (a one-time warning is
printed); `ctf-eval` degrades further to its offline heuristic if Ollama is also unreachable.

One-time key setup (paste the real key yourself — it never needs to pass through anyone else):

```zsh
printf 'export CTF_REMOTE_API_KEY=%q\n' 'sk-REAL' >> ~/.config/ctf-toolchain/secrets.env
# secrets.env is chmod 600 and sourced from ~/.bashrc and ~/.zshrc
```

---

## Agent loop

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
| `strings(path, min_len)` | auto | Printable strings (system `strings` + Python fallback) |
| `http_request(method, url, …)` | ask | Web challenge requests via urllib |
| `finish(answer)` | — | End loop; triggers verification step first |

### Approval tiers

1. **auto** (allowlist) — `file`, `strings`, `ls`, `cat`, `grep`, `hexdump`, `nmap`, `objdump`, `readelf`, `binwalk` (without `-e`), `base64`, `openssl` inspect ops, … — runs silently
2. **ask** — everything else; prompt shows `[y] once / [a] always / [N] deny`; "a" appends a prefix rule to the session allowlist
3. **deny** (denylist) — `rm -rf`, `sudo`, `curl|sh`, `dd of=/dev/`, fork bombs, `shred` — hard-blocked even under `--approve auto`

### Loop guards

- **Repeat detection** — duplicate tool+args hash → injects "you already ran this" and skips
- **No-progress heuristic** — 3 consecutive empty/duplicate observations → pause prompt
- **Soft budget** — at `--max-steps`: continue 10 more / stop / inject hint / enter answer
- **Mid-run steering** — type and press Enter at any time; injected as `[user hint]` without restarting
- **Verification before finish** — proposed answer goes through a separate classification call
- **Refusal fallback** — refusal detected via a clean-context classifier call (not substring-matching tool output); auto-switches to `dolphin-llama3:8b`

### Context management

- Pinned facts (task, flag format, confirmed findings) survive truncation
- Messages pruned above 40; last 12 preserved alongside pinned block
- Flag-like strings (`WORD{...}`) auto-extracted from observations into pinned findings

### Transcript + resume

Every step appended to `.agent/run-YYYYMMDD-HHMMSS.jsonl`. `--resume` reloads message history and continues. System prompt rebuilt fresh on resume (catalog changes take effect).

---

## Helper scripts

```zsh
./switch-model.sh deepseek   # load deepseek-r1:14b (primary)
./switch-model.sh coder      # load qwen2.5-coder:14b
./switch-model.sh dolphin    # load dolphin-llama3:8b (uncensored / RAM-saver)
./switch-model.sh status     # ollama ps + ollama list

./start-ollama.sh            # start service, confirm localhost + LAN reachable
./stop-ollama.sh             # stop service to free RAM (e.g. before Ghidra)
./test-server.sh             # health check: reachable, models present, generation works
./test-server.sh 192.168.1.11   # same check from Kali over LAN
```

---

## From Kali

Point the Kali-side helper at the Mac over the LAN. `ai.py` and the agent read the
**`CTF_AI_HOST`** env var (default `localhost`), so no code edit is needed:

```zsh
export CTF_AI_HOST=192.168.1.11   # Mac's LAN IP (DHCP — may drift; see below)
python3 ai.py agent "triage ./chal"
```

> [!note] IP drift
> The Mac is on DHCP and its LAN IP has drifted (`192.168.1.124` → `192.168.1.11`). Set a
> **DHCP reservation** on the router for a permanent address; until then `CTF_AI_HOST` covers it.

See `[[local-ai-ctf-setup]]` section 07–08 for connectivity setup and tests.

> [!warning]
> Always pass `"num_ctx": 8192` in API calls — Ollama defaults to 2048 on some builds and will
> truncate long responses mid-stream. `ai.py` already sets this.

---

## Architecture

```
ctf-toolchain/
  ai.py              # CLI: one-shot (unchanged) + agent subcommand
  agent/
    config.py        # host / model / limits
    llm.py           # Ollama /api/chat wrapper
    protocol.py      # JSON extractor (handles <think> tags, ```json fences, nested braces)
    tools.py         # tool registry (10 tools, streaming run_shell + python_exec)
    approval.py      # three-tier gate + session-learned allowlist + check_write diff
    loop.py          # ReAct loop (all guards, steering, truncation, transcript writes)
    transcript.py    # .agent/*.jsonl write + load_resume
    refusal.py       # clean-context refusal classifier + dolphin fallback
    context.py       # pinned-facts + maybe_truncate
  switch-model.sh
  start-ollama.sh / stop-ollama.sh
  test-server.sh
  AGENT-PLAN.md      # original implementation plan
```

Dependencies: **stdlib only** (`urllib`, `json`, `subprocess`, `threading`, `select`, `difflib`).
CTF power comes from shelling out to the installed toolset (pwntools, pycryptodome, z3, binwalk, …).
