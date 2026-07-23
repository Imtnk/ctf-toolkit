"""ReAct agent loop — Phase 5.

Phase 5 additions:
  - Refusal-classification fallback to dolphin (via refusal.py)
  - Pinned-facts context truncation (via context.py)
  - Streaming tool output for run_shell / python_exec
  - .agent/*.jsonl transcript written every step
  - --resume: load a prior transcript and continue
"""
import hashlib, os, select, sys, time
from . import approval, config, context, llm, protocol, refusal, tools, transcript

NO_PROGRESS_LIMIT = 3


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a CTF expert agent. Solve the given challenge step by step.

Each turn output EXACTLY ONE JSON object — nothing before or after it.
Always include the "thought" field (one line explaining your next action).

To call a tool:
{{"thought":"<reason>","tool":"<name>","args":{{<args>}}}}

To finish:
{{"thought":"<summary>","tool":"finish","args":{{"answer":"<flag or full result>"}}}}

Before calling finish, verify your answer is correct (re-read it from output,
check the flag format, grep for it again if unsure).

Available tools:
{catalog}

Rules:
- thought is REQUIRED on every turn
- Output ONE JSON object only — no prose outside it
- Never repeat an identical tool call you already made
- Never decode, decrypt, or compute a value in your head (base64, hex, rot13,
  arithmetic, etc.) — run a tool to do it and read the result
- Keep "thought" to ONE short sentence; never repeat text or loop
- If stuck, explain in thought what you tried and try a different approach
"""


def _build_system() -> str:
    return _SYSTEM.format(catalog=tools.catalog())


# ── Verification ──────────────────────────────────────────────────────────────

_VERIFY_PROMPT = (
    'The agent proposes this answer: "{answer}"\n\n'
    'Is this correct? If it looks like a valid CTF flag or complete result, '
    'confirm with: {{"thought":"verified","tool":"finish","args":{{"answer":"{answer}"}}}}\n'
    'If not, continue with a tool call to double-check.'
)


def _verify(answer: str, messages: list, model: str, host: str,
            pinned: dict | None = None) -> str | None:
    verify_msgs = messages + [
        {"role": "user", "content": _VERIFY_PROMPT.format(answer=answer)},
    ]
    if pinned is not None:
        verify_msgs = context.maybe_truncate(verify_msgs, pinned, config.context_char_budget(model))
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
    if tool_name in ("read_file", "list_dir", "file_info", "hexdump", "strings"):
        return True
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
            "\n\033[33m⏸ interrupted — type a hint to steer the agent "
            "(Enter = resume, q = abort): \033[0m"
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return None, True
    if note.lower() in ("q", "quit", "abort"):
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
        print(f"\n── step {step} ", end="", flush=True)
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
            raw = llm.chat(messages, model=current_model, host=host)
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
                    raw = llm.chat(messages, model=current_model, host=host)
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
                            raw = llm.chat(messages, model=current_model, host=host)
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
                raw = llm.chat(messages, model=current_model, host=host)

        if obj is None:
            break

        thought   = obj.get("thought", "")
        tool_name = obj["tool"]
        args      = obj["args"]
        budget_remaining -= 1

        # ── repeat detection ──────────────────────────────────────────────────
        call_key = hashlib.md5(f"{tool_name}:{args}".encode()).hexdigest()
        if call_key in seen_calls and tool_name != "finish":
            print(f"▸ [{thought}] {tool_name}  [DUPLICATE — skipping]")
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
            print(f"({elapsed_model:.1f}s model)\n▸ [{thought}] {tool_name}({cmd_display}){tier_str}")

            # ── finish path ───────────────────────────────────────────────────
            if tool_name == "finish":
                answer = args.get("answer", "")
                if dry_run:
                    print(f"  [dry-run] finish → {answer!r}")
                    return answer
                print("  [verifying…]", end="", flush=True)
                verified = _verify(answer, messages, current_model, host, pinned)
                if verified:
                    print(f"\n\033[32m✓ Answer verified:\033[0m {verified}")
                    if run_file:
                        transcript.append_finish(run_file, verified)
                    return verified
                print("\n  [verification did not confirm — continuing]")
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
