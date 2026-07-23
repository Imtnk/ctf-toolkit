# Plan: Turn `ai.py` into a capable local CTF agent

**File:** `ctf-toolchain/ai.py` · **Model:** `qwen2.5-coder:14b` (Ollama, localhost) · **Date:** 2026-07-19

## Context / problem

Today `ai.py` is a **one-shot chat call**: it sends `system + user` to Ollama's `/api/chat` and
prints one reply. It can't take actions, can't iterate, can't inspect files or run tools — so for
anything beyond "answer this question" it stalls. We want it to handle **complex, multi-step CTF
tasks**: read a binary, run `strings`/`file`, try an exploit, read the output, adjust, and drive
toward a flag — locally, no cloud.

> **Scope honestly (per review):** a 14B local model is a strong **triage-and-scaffold assistant**
> with the human driving strategy — not an autonomous pwn-solver. It loses the thread over long,
> messy contexts and pattern-matches the wrong exploit class without correction. The plan compensates
> with per-turn `thought`, small subtasks, verification-before-finish, and mid-run steering. README
> claims should match that ceiling, or task #2 disappoints.

## Key design decision: a hand-rolled ReAct loop over JSON-in-content

We already proved (both Ollama endpoints) that `qwen2.5-coder:14b` **does not emit structured
`tool_calls`** — when asked to use a tool it prints the call as JSON *in the message content*:

```json
{ "name": "run_shell", "arguments": { "cmd": "strings ./chal | head" } }
```

Rather than fight that, **make it the protocol.** The agent prompts the model to reply with exactly
one JSON object per turn — either a tool call or a final answer — parses it from content, executes
the tool locally, appends the result as an observation, and loops. This needs **no** dependency on
Ollama's (broken) structured tool-calling and works with the models we already have. It's a classic
ReAct / tool-loop, implemented in ~stdlib Python.

## Architecture

Keep it dependency-light and single-purpose. Grow `ai.py` into a small package:

```
ctf-toolchain/
  ai.py          # CLI entry: one-shot chat (back-compat) + `agent` subcommand
  agent/
    __init__.py
    loop.py      # the ReAct loop: call model -> parse -> execute -> observe -> repeat
    protocol.py  # strict JSON extraction (strip ```json fences, grab first valid object)
    tools.py     # tool registry + implementations
    llm.py       # Ollama client (chat, num_ctx, model fallback, streaming)
    config.py    # host/model/limits/allowlist
```

`ai.py` stays backward compatible: `echo ... | ai.py` and `ai.py "question"` still do a plain
one-shot chat (no tools). New behavior is opt-in via `ai.py agent "<task>"`.

## Tools (CTF-focused registry)

Each tool = a Python function + a JSON schema string injected into the system prompt. Start set:

| Tool | Purpose | Notes |
|---|---|---|
| `run_shell(cmd)` | run a shell command | timeout, captured stdout/stderr, cwd-scoped |
| `python_exec(code)` | run a Python snippet | for pwntools/pycryptodome/sympy/z3 one-liners |
| `read_file(path)` / `write_file(path,text)` | file IO | size cap on reads |
| `list_dir(path)` | directory listing | |
| `file_info(path)` | `file` + size + sha256 | fast triage |
| `hexdump(path,n)` / `strings(path,min)` | binary triage | wrap `xxd`/`strings` |
| `http_request(method,url,...)` | web-chal interaction | via urllib; opt-in |
| `finish(answer)` | end the loop with the result | terminal action |

Tools live in one registry so adding one = one function + one schema line. `run_shell` +
`python_exec` already cover most CTF work (they can call `nmap`, `binwalk`, `openssl`, pwntools…),
so the rest is convenience/safety sugar.

## Agent loop mechanics (`loop.py`)

Every model turn is **one JSON object** with a required one-line `thought` plus either a tool call or
`finish`. The `thought` field is cheap chain-of-thought that keeps a small model coherent *and* gives
the user a human-readable reason to show while tokens stream (the JSON itself isn't readable prose).

```json
{ "thought": "triage the binary first", "tool": "run_shell", "args": { "cmd": "file ./chal" } }
```

1. Seed messages: `system` (role, tool catalog, strict JSON protocol, required `thought`, `finish`
   to end, `update_plan` to record intent) + `user` (task).
2. Call the model (`num_ctx` 8192→ raise as needed, temp ~0.1).
3. Extract the first valid JSON object (`protocol.py` tolerates ```json fences, leading prose, junk).
4. If `finish` → **run a verification step first** (e.g. confirm the flag matches the expected format
   / re-grep it) before accepting. Else look up the tool, gate on approval (see Safety), execute.
5. Append `assistant` (raw call incl. `thought`) + a truncated, labelled observation.
6. **Loop-control guards** (the real small-model failure mode is *productive-looking thrashing*, not
   bad JSON):
   - **Repeat detection** — hash each tool-call; on a recurrence feed back *"you already ran this →
     result was X; try something else."*
   - **No-progress heuristic** — if K steps pass with no `finish` and no new file/observation, **pause
     and ask the user** instead of silently burning the budget.
   - **Soft budget** — at `--max-steps` (default ~15) don't hard-stop with no answer; **prompt to
     continue / stop / steer**, preserving context.
7. **Mid-run steering** — a keypress injects a `user` message into history ("flag format is `CTF{…}`,
   stop brute-forcing") *without* restarting, so the user corrects course instead of Ctrl-C + re-run.
8. On unparseable output → short "reply with ONE JSON object" corrector, capped retries.

## Safety model (non-negotiable — this runs shells for a security user)

`run_shell`/`python_exec` are arbitrary code execution (and `python_exec` **must** go through the
same gate — a Python snippet is as dangerous as a shell command). Guardrails:
- **Three-tier approval (fail-closed), not two blunt modes.** A binary manual/auto choice fails:
  per-command Enter-gating on `file`/`strings`/`hexdump` is unusable over a 12-step triage, so users
  flip to `auto` and lose all safety. Instead:
  1. **auto-run allowlist** of read-only triage tools (`file`, `strings`, `hexdump`, `ls`, `nmap`,
     `binwalk`, …) — regex/prefix rules.
  2. **prompt** for everything else, with a **"always allow commands like this"** option that appends
     a rule to the allowlist (learns as you go).
  3. **`--dry-run`** shows planned commands, executes nothing.
  Default posture for anything not on the allowlist is *ask*; `--approve auto` stays opt-in.
- **Denylist is a backstop, not the primary defense** (blocklists fail open — `curl|sh`, `rm -rf
  $HOME`, fork-bomb variants slip through). The allowlist is the fail-closed default; the denylist
  just hard-blocks obvious destroyers even under `auto`.
- **Diff-before-write:** `write_file` shows a diff and requires approval before touching disk — never
  silently overwrite an exploit script.
- **Timeouts** on every command; **output truncation** fed back to the model.
- **Working-dir scoping:** default cwd = a per-task dir; warn on paths outside it. Never auto-`sudo`.
- Everything local — no prompt/output leaves the machine (preserves the offline/private rationale).

## Model handling

- Default `qwen2.5-coder:14b`; `--model dolphin` to swap. **Refusal fallback to `dolphin-llama3:8b`**
  — but *not* by substring-matching tool output (a `strings` dump can literally contain "I cannot").
  Trigger on an explicit refusal-classification turn or a user keypress.
- Reuse `switch-model.sh` semantics; keep `num_ctx` explicit (avoid the 2048 default cutoff).
- **Context management via pinned facts, not model-summarization** (a 14B summarizing mid-run will
  drop the flag). Hard-truncate old observations but keep a pinned block: target, flag format,
  confirmed findings, current plan.

## CLI / UX

```
ai.py "question"                 # one-shot chat (unchanged, no tools)
ai.py agent "task"               # agentic loop
ai.py agent --approve auto "…"   # run tools without prompting
ai.py agent --dry-run "…"        # show planned commands only
ai.py agent -m dolphin "…"       # uncensored model
cat chal.py | ai.py agent "find and exploit the vuln"
```

Print each step as `▸ [thought] tool(args)` → `└ result (elapsed)` so the user follows and can
interrupt. Stream the **tool result** (a long `nmap`/`strings` streams as it runs, not a silent block
then a dump); 14B-on-local-Ollama is multi-second per turn, so per-step elapsed time signals "alive".

### Session persistence & transcript
Persist message history to `.agent/run-<ts>.jsonl` every step. This gives **`ai.py agent --resume`**
(a run killed by crash/Ctrl-C/sleep doesn't lose all context) and doubles as an auditable
**transcript** of exactly which commands touched a target — important for a security user.

## Phased implementation

1. **Core loop + 2 tools** (`run_shell`, `finish`) + strict JSON parser + required `thought` +
   verification-before-finish. Prove it converges on a simple task ("what type is file X").
2. **Approval tiers** — auto-run allowlist + "always allow like this" + `--dry-run`; denylist backstop.
   (Highest-impact UX/safety item — do it before adding more tools.)
3. **Full tool set** (`python_exec` through the same gate, file/binary triage, `http_request` with
   diff-before-write for `write_file`).
4. **Loop control** — repeat/no-progress detection, soft budget prompt, mid-run steering keypress.
5. **Robustness + persistence** — refusal-classification fallback, pinned-facts truncation,
   retry-on-bad-JSON, streamed tool output + per-step elapsed, `.agent/*.jsonl` transcript + `--resume`.
6. **Back-compat + docs** — keep one-shot mode; update `README.md` (scope claims to triage-assistant).

## Dependencies
Core loop = **stdlib only** (`urllib`, `json`, `subprocess`) so it stays portable and matches the
current file. CTF power comes from tools shelling out to the already-installed toolset
(pwntools/pycryptodome/sympy/z3 via `python_exec`), not from importing heavy libs into the agent.

## Verification
- Unit: JSON extractor against fenced / prose-wrapped / multi-object outputs.
- Loop: a scripted task with a known answer (e.g. decode a base64 flag in a file) converges in ≤3 steps.
- Safety: `--dry-run` executes nothing; denylist blocks a destructive command; timeout fires.
- Back-compat: existing `echo … | ai.py` one-shot still works unchanged.
