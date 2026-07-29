"""ReAct agent loop — Phase 5.

Phase 5 additions:
  - Refusal-classification fallback to dolphin (via refusal.py)
  - Pinned-facts context truncation (via context.py)
  - Streaming tool output for run_shell / python_exec
  - .agent/*.jsonl transcript written every step
  - --resume: load a prior transcript and continue
"""
import hashlib, itertools, os, select, sys, threading, time
from . import approval, config, context, llm, protocol, refusal, tools, transcript

NO_PROGRESS_LIMIT = 3


# ── Progress spinner (quiet mode) ─────────────────────────────────────────────
# When not --verbose the brain's live tokens aren't echoed, so a blocking model
# call (a remote "thinking" model can take many seconds) would look hung. This
# tiny stderr spinner shows it's alive with an elapsed counter, and is wiped
# before the step's result prints. Silent when stderr isn't a TTY (piped/logged).

_SPIN_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class _Spinner:
    def __init__(self, label="thinking", enabled=True):
        self.label = label
        self.enabled = enabled and sys.stderr.isatty()
        self._stop = threading.Event()
        self._t = None

    def __enter__(self):
        if self.enabled:
            self._t = threading.Thread(target=self._run, daemon=True)
            self._t.start()
        return self

    def _run(self):
        t0 = time.monotonic()
        for ch in itertools.cycle(_SPIN_FRAMES):
            if self._stop.is_set():
                break
            dt = time.monotonic() - t0
            sys.stderr.write(f"\r\033[2m{ch} {self.label}… {dt:0.0f}s\033[0m\033[K")
            sys.stderr.flush()
            self._stop.wait(0.12)

    def __exit__(self, *exc):
        self._stop.set()
        if self._t:
            self._t.join()
        if self.enabled:
            sys.stderr.write("\r\033[K")   # wipe the spinner line
            sys.stderr.flush()


def _chat(messages, model, host, verbose, label="thinking"):
    """A model call with a progress indicator. verbose → stream the brain's live
    tokens (they are their own indicator); quiet → a spinner while the call blocks."""
    if verbose:
        return llm.chat(messages, model=model, host=host)
    with _Spinner(label):
        return llm.chat(messages, model=model, host=host, stream_echo=False)


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a CTF and security assistant agent. Complete the USER'S TASK step by step
using tools. The task may be a flag hunt OR a plain request (list files, identify a
binary, extract an archive, read a value). Do exactly what was asked — nothing more.

Each turn output EXACTLY ONE JSON object — nothing before or after it.
Always include the "thought" field (one line explaining your next action).

To call a tool:
{{"thought":"<reason>","tool":"<name>","args":{{<args>}}}}

To finish:
{{"thought":"<summary>","tool":"finish","args":{{"answer":"<the answer>"}}}}

Call finish AS SOON AS the task is answered. If the task asked for a flag, put the
flag{{...}} in "answer"; otherwise put the direct answer (e.g. the file listing).
NOT every task has a flag — do not keep hunting for one when the user only asked for
something else. Briefly re-read your answer from the tool output before finishing.

Available tools:
{catalog}

Rules:
- thought is REQUIRED on every turn
- Output ONE JSON object only — no prose outside it
- Finish as soon as you've answered the task; don't invent extra work or search for
  a flag the task did not ask for
- Never repeat an identical tool call you already made
- Never decode, decrypt, or compute a value in your head (base64, hex, rot13,
  arithmetic, etc.) — run a tool to do it and read the result
- Keep "thought" to ONE short sentence; never repeat text or loop
- If stuck, explain in thought what you tried and try a different approach

Exploitation notes (authorized CTF/lab targets only):
- Reverse shells: through a WEB param / injected command, do NOT use `bash -i >& /dev/tcp`
  (needs bash; injected cmds run under /bin/sh and the URL mangles it). Prefer an nc-mkfifo
  or python3 payload and URL-encode it. Use the `revshell` tool / `ctf-rev gen --for-web`.
- Privilege escalation: after RCE, run `sudo -n -l`, find SUID (`find / -perm -4000`), and
  check capabilities. When a standard binary is exploitable, look it up on GTFOBins
  (https://gtfobins.org/gtfobins) for the exact Sudo/SUID/Capabilities one-liner to get root
  instead of guessing.
"""


def _build_system() -> str:
    return _SYSTEM.format(catalog=tools.catalog())


# ── Verification ──────────────────────────────────────────────────────────────

_VERIFY_PROMPT = (
    'The agent proposes this answer: "{answer}"\n\n'
    'Does it answer the task (a valid flag, OR the information the user asked for)? '
    'If yes, confirm with: {{"thought":"verified","tool":"finish","args":{{"answer":"{answer}"}}}}\n'
    'Only if it clearly does NOT answer the task, continue with a tool call to double-check.'
)


def _verify(answer: str, messages: list, model: str, host: str,
            pinned: dict | None = None, verbose: bool = False) -> str | None:
    verify_msgs = messages + [
        {"role": "user", "content": _VERIFY_PROMPT.format(answer=answer)},
    ]
    if pinned is not None:
        verify_msgs = context.maybe_truncate(verify_msgs, pinned, config.context_char_budget(model))
    # Verification is an internal check — never spray its tokens (stream_echo=False),
    # but show a spinner in quiet mode so the finish step doesn't look hung.
    with _Spinner("verifying", enabled=not verbose):
        raw = llm.chat(verify_msgs, model=model, host=host, temperature=0, stream_echo=False)
    try:
        obj = protocol.extract_json(raw)
        protocol.validate(obj)
    except ValueError:
        return None
    return obj["args"].get("answer", answer) if obj["tool"] == "finish" else None


# ── Scope warning ─────────────────────────────────────────────────────────────

def _warn_scope(cmd: str, cwd: str | None) -> None:
    if not cwd:
        return
    import shlex
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return
    for token in tokens:
        if token.startswith("/") and not token.startswith(cwd):
            print(f"  \033[33m[scope warning]\033[0m path outside task dir: {token!r}")
            break


# ── Approval gate ─────────────────────────────────────────────────────────────

def _gate(tool_name: str, args: dict, auto_approve: bool, cwd: str | None) -> bool:
    if tool_name == "finish":
        return True
    if tool_name in ("read_file", "list_dir", "file_info", "hexdump", "strings", "revshell"):
        return True   # revshell only generates a string; connecting is a separate manual step
    if tool_name == "write_file":
        return approval.check_write(args.get("path", ""), args.get("text", ""))
    if tool_name == "python_exec":
        code = args.get("code", "")
        _warn_scope(code, cwd)
        return approval.check(code, auto_approve=auto_approve)
    cmd = args.get("cmd") or args.get("url") or str(args)
    _warn_scope(cmd, cwd)
    return approval.check(cmd, auto_approve=auto_approve)


# ── Steering ──────────────────────────────────────────────────────────────────

def _poll_steering() -> str | None:
    if not sys.stdin.isatty():
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if ready:
            line = sys.stdin.readline().strip()
            return line or None
    except Exception:
        pass
    return None


# ── No-progress detection ─────────────────────────────────────────────────────

_STALE = frozenset({"(no output)", "(no strings found)", "(empty)", ""})


def _is_stale(obs: str, seen_obs: set[str]) -> bool:
    stripped = obs.strip()
    if stripped in _STALE:
        return True
    h = hashlib.md5(stripped.encode()).hexdigest()
    if h in seen_obs:
        return True
    seen_obs.add(h)
    return False


# ── Soft budget / no-progress prompt ─────────────────────────────────────────

def _pause_prompt(messages: list, label: str) -> tuple[str | None, bool, int]:
    """Returns (hint_to_inject, should_stop, extra_budget)."""
    print(f"\n\033[33m[{label}]\033[0m")
    print("  [c] continue 10 more steps")
    print("  [s] stop")
    print("  [i] inject a steering hint and continue")
    print("  [a] enter final answer manually")
    try:
        ans = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None, True, 0

    if ans == "c":
        return None, False, 10
    if ans == "s":
        return None, True, 0
    if ans == "i":
        try:
            hint = input("  hint > ").strip()
        except (EOFError, KeyboardInterrupt):
            hint = ""
        return hint or None, False, 5
    if ans == "a":
        try:
            final = input("  answer > ").strip()
        except (EOFError, KeyboardInterrupt):
            final = ""
        return final or None, True, 0
    return None, True, 0


# ── Interrupt (Ctrl+C) steering ───────────────────────────────────────────────

def _interrupt_prompt() -> tuple[str | None, bool]:
    """Ctrl+C during a model call. Returns (hint_to_inject, should_abort).

    KeyboardInterrupt is a BaseException, not an Exception, so it escapes the
    loop's `except Exception` — without this the only way to cancel a (streaming,
    up-to-300s) remote call would crash the agent with a traceback. Mirrors the
    standalone agent's interrupt handler: steer, resume, or abort cleanly.
    """
    try:
        note = input(
            "\n\033[33m⏸ paused — Enter to resume · type a hint to steer · "
            "q or Ctrl-C again to QUIT: \033[0m"
        ).strip()
    except (EOFError, KeyboardInterrupt):
        # Second Ctrl-C (or EOF) at the prompt = quit hard and immediately, so a
        # runaway loop always stops on a double Ctrl-C regardless of loop state.
        print("\n\033[31m[aborted]\033[0m")
        raise SystemExit(130)
    if note.lower() in ("q", "quit", "abort", "exit", "stop"):
        return None, True
    return (note or None), False


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(
    task: str,
    model: str = config.BRAIN_MODEL,
    host: str = config.HOST,
    max_steps: int = config.MAX_STEPS,
    auto_approve: bool = False,
    dry_run: bool = False,
    cwd: str | None = None,
    resume_messages: list | None = None,
    verbose: bool = False,
) -> str | None:

    # ── initialise messages ───────────────────────────────────────────────────
    sys_msg = {"role": "system", "content": _build_system()}
    if resume_messages:
        # Rebuild system prompt fresh (catalog may have changed), keep saved history
        if resume_messages and resume_messages[0]["role"] == "system":
            resume_messages[0] = sys_msg   # replace stale system prompt in-place
        messages = resume_messages
        print(f"\033[36m[resuming — {len(messages)} messages loaded]\033[0m")
    else:
        messages = [sys_msg, {"role": "user", "content": task}]

    # ── transcript ────────────────────────────────────────────────────────────
    run_file = transcript.new_run(task, model) if not dry_run else None
    if run_file:
        print(f"\033[2m[transcript] {run_file}\033[0m")

    # ── pinned facts ──────────────────────────────────────────────────────────
    pinned = context.make_pinned(task)

    # ── loop state ────────────────────────────────────────────────────────────
    seen_calls:     set[str] = set()
    seen_obs:       set[str] = set()
    retry_budget     = 3
    stale_streak     = 0
    budget_remaining = max_steps
    step             = 0
    current_model    = model

    while budget_remaining > 0:
        step += 1
        print(f"\n\033[1m── step {step}\033[0m", flush=True)
        t_step = time.monotonic()

        # ── mid-run steering check ────────────────────────────────────────────
        hint = _poll_steering()
        if hint:
            print(f"\n  \033[36m[steering]\033[0m {hint!r}")
            messages.append({"role": "user", "content": f"[user hint] {hint}"})

        # ── context truncation ────────────────────────────────────────────────
        messages = context.maybe_truncate(
            messages, pinned, config.context_char_budget(current_model))

        # ── call model ────────────────────────────────────────────────────────
        try:
            raw = _chat(messages, current_model, host, verbose)
        except KeyboardInterrupt:
            note, stop = _interrupt_prompt()
            if stop:
                print("\n  \033[31m[aborted by user]\033[0m")
                return None
            if note:
                print(f"  \033[36m[steering]\033[0m {note!r}")
                messages.append({"role": "user", "content": f"[user hint] {note}"})
            continue
        except Exception as e:
            # A remote transport failure (HTTP 4xx/5xx, context overflow, unreachable)
            # must not kill the run — degrade to the local model and retry this step.
            if config.is_remote(current_model):
                print(f"\n  \033[33m[remote brain failed]\033[0m {e}"
                      f"\n  falling back to local {config.LOCAL_MODEL}")
                current_model = config.LOCAL_MODEL
                try:
                    messages = context.maybe_truncate(
                        messages, pinned, config.context_char_budget(current_model))
                    raw = _chat(messages, current_model, host, verbose, label="local fallback")
                except Exception as e2:
                    print(f"\n[llm error] local fallback also failed: {e2}")
                    break
            else:
                print(f"\n[llm error] {e}")
                break

        # ── parse ─────────────────────────────────────────────────────────────
        obj = None
        for attempt in range(retry_budget):
            try:
                obj = protocol.extract_json(raw)
                protocol.validate(obj)
                break
            except ValueError as e:
                if attempt + 1 >= retry_budget:
                    # Last resort: classify as refusal before giving up
                    if refusal.is_refusal(raw, current_model, host):
                        fb = refusal.fallback_model()
                        print(f"\n  \033[33m[refusal detected]\033[0m switching to {fb}")
                        current_model = fb
                        try:
                            messages = context.maybe_truncate(
                                messages, pinned, config.context_char_budget(current_model))
                            raw = _chat(messages, current_model, host, verbose)
                            obj = protocol.extract_json(raw)
                            protocol.validate(obj)
                        except Exception:
                            obj = None
                    else:
                        print(f"\n[parse failed after {retry_budget} retries: {e}]")
                    break
                correction = (
                    f"Your last reply could not be parsed as JSON: {e}\n"
                    "Reply with ONE valid JSON object matching the required format."
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": correction})
                messages = context.maybe_truncate(
                    messages, pinned, config.context_char_budget(current_model))
                raw = _chat(messages, current_model, host, verbose)

        if obj is None:
            break

        thought   = obj.get("thought", "")
        tool_name = obj["tool"]
        args      = obj["args"]
        budget_remaining -= 1

        # ── repeat detection ──────────────────────────────────────────────────
        call_key = hashlib.md5(f"{tool_name}:{args}".encode()).hexdigest()
        if call_key in seen_calls and tool_name != "finish":
            print(f"▸ [{thought}] \033[1m{tool_name}\033[0m  \033[33m[DUPLICATE — skipping]\033[0m")
            new_msgs = [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"You already ran {tool_name}({args}) and got that result. Try a different approach."},
            ]
            messages.extend(new_msgs)
            if run_file:
                transcript.append_step(run_file, step, new_msgs)
            stale_streak += 1
        else:
            seen_calls.add(call_key)

            elapsed_model = time.monotonic() - t_step
            cmd_display = (
                args.get("cmd") or args.get("code") or args.get("path") or
                args.get("url") or str(args)
            )
            if tool_name == "write_file":
                tier_str = "  \033[2m[diff+confirm]\033[0m"
            elif tool_name in ("read_file", "list_dir", "file_info", "hexdump", "strings", "finish"):
                tier_str = ""
            else:
                tier = approval.tier_label(cmd_display)
                tier_str = f"  \033[2m[{tier}]\033[0m"
            print(f"▸ \033[2m{elapsed_model:.1f}s\033[0m  [{thought}] \033[1m{tool_name}\033[0m({cmd_display}){tier_str}")

            # ── finish path ───────────────────────────────────────────────────
            if tool_name == "finish":
                answer = args.get("answer", "")
                if dry_run:
                    print(f"  [dry-run] finish → {answer!r}")
                    return answer
                verified = _verify(answer, messages, current_model, host, pinned, verbose)
                if verified:
                    print(f"\033[32m✓ Answer verified:\033[0m {verified}")
                    if run_file:
                        transcript.append_finish(run_file, verified)
                    return verified
                print("  [verification did not confirm — continuing]")
                new_msgs = [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Verification did not confirm the answer. Use a tool to double-check."},
                ]
                messages.extend(new_msgs)
                if run_file:
                    transcript.append_step(run_file, step, new_msgs)
                stale_streak += 1
                continue

            # ── unknown tool ──────────────────────────────────────────────────
            if not tools.known(tool_name):
                print(f"  [unknown tool: {tool_name!r}]")
                new_msgs = [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"Tool {tool_name!r} does not exist. Choose from: {list(tools._registry)}"},
                ]
                messages.extend(new_msgs)
                if run_file:
                    transcript.append_step(run_file, step, new_msgs)
                continue

            # ── dry-run ───────────────────────────────────────────────────────
            if dry_run:
                print(f"  [dry-run] would execute: {tool_name}({args})")
                new_msgs = [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "[dry-run: command not executed]"},
                ]
                messages.extend(new_msgs)
                continue

            # ── approval gate ─────────────────────────────────────────────────
            if not _gate(tool_name, args, auto_approve, cwd):
                new_msgs = [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Command denied. Try a different approach."},
                ]
                messages.extend(new_msgs)
                if run_file:
                    transcript.append_step(run_file, step, new_msgs)
                continue

            # ── execute (with streaming for shell/python) ─────────────────────
            printed_stream = [False]

            def _stream_line(line: str) -> None:
                if not printed_stream[0]:
                    print()   # newline after the ▸ line before stream starts
                    printed_stream[0] = True
                print(f"  {line}", end="", flush=True)

            try:
                result, exec_time = tools.dispatch(
                    tool_name, args,
                    stream_to=_stream_line if tool_name in tools._STREAMING_TOOLS else None,
                )
            except Exception as e:
                result, exec_time = f"[tool error] {e}", 0.0

            result_str = str(result)
            truncated  = result_str[: config.MAX_OBS_CHARS]
            suffix     = (
                f"\n[... truncated to {config.MAX_OBS_CHARS} chars]"
                if len(result_str) > config.MAX_OBS_CHARS else ""
            )

            if printed_stream[0]:
                # Already streamed — just show elapsed
                print(f"\n└ ({exec_time:.1f}s)")
            else:
                preview = truncated[:300] + ("…" if len(truncated) > 300 else "")
                print(f"└ {preview} ({exec_time:.1f}s)")

            new_msgs = [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"[observation]\n{truncated}{suffix}"},
            ]
            messages.extend(new_msgs)
            if run_file:
                transcript.append_step(run_file, step, new_msgs)

            # ── pinned facts + no-progress tracking ───────────────────────────
            context.auto_update(pinned, truncated)
            if _is_stale(truncated, seen_obs):
                stale_streak += 1
                print(f"  \033[2m[stale — streak {stale_streak}/{NO_PROGRESS_LIMIT}]\033[0m")
            else:
                stale_streak = 0

        # ── no-progress pause ─────────────────────────────────────────────────
        if stale_streak >= NO_PROGRESS_LIMIT:
            hint, stop, extra = _pause_prompt(messages, f"no progress for {stale_streak} steps")
            if stop:
                return hint or None
            if hint:
                messages.append({"role": "user", "content": f"[user hint] {hint}"})
            budget_remaining += extra
            stale_streak = 0

        # ── soft budget pause ─────────────────────────────────────────────────
        elif budget_remaining == 0:
            hint, stop, extra = _pause_prompt(messages, f"max steps ({max_steps}) reached")
            if stop:
                return hint or None
            if hint:
                messages.append({"role": "user", "content": f"[user hint] {hint}"})
            budget_remaining += extra

    return None
