#!/usr/bin/env python3
"""Simple UI + launcher for ai.py — one-shot Q&A and the ReAct agent.

Usage:
  ai                       # interactive menu
  ai "<question>"          # one-shot passthrough (remote brain by default)
  ai agent "<task>" ...    # agent passthrough (every ai.py flag works)
  ai -h                    # this help

Thin wrapper around the sibling ai.py. Runs in YOUR current directory so the agent
operates on the files you're sitting in; ai.py's own dir is put on PYTHONPATH so the
`agent` package still imports. Bare `ai` opens a menu; any args pass straight through.
"""
import os, sys, signal, subprocess

# realpath so a PATH symlink (e.g. ~/.local/bin/ai -> repo/ai-ui.py) resolves back
# to the repo, where ai.py and the `agent` package live.
HERE = os.path.dirname(os.path.realpath(__file__))
AI   = os.path.join(HERE, "ai.py")
TTY  = sys.stdout.isatty()
sys.path.insert(0, HERE)                       # so `from agent import config` works anywhere

# per-session toggles (reset each launch)
STATE = {"local": False, "approve": "manual", "dry_run": False}


def c(code, s):
    return f"\033[{code}m{s}\033[0m" if TTY else s


def brain_line():
    try:
        from agent import config
        remote = config.REMOTE_ENABLED and bool(config.REMOTE_API_KEY) and not STATE["local"]
        if remote:
            return c("32", f"remote · {config.REMOTE_MODEL}")
        why = ("forced --local" if STATE["local"]
               else "no API key" if not config.REMOTE_API_KEY else "CTF_BRAIN=local")
        return c("33", f"local · {config.LOCAL_MODEL}") + c("2", f"  ({why})")
    except Exception as e:
        return c("31", f"config unavailable ({e})")


def launch(args, shield_sigint=False):
    """Run ai.py in the USER'S current directory so the agent's tools act on the
    files you're in, not the repo. HERE goes on PYTHONPATH so the `agent` package
    still imports.

    When shield_sigint, we must let Ctrl+C reach the agent child (its loop has a
    steer/abort handler) WITHOUT killing this parent menu. The obvious SIG_IGN is
    WRONG: SIG_IGN is inherited across exec, and CPython refuses to install its
    KeyboardInterrupt handler when it starts up with SIGINT already ignored, so the
    child would swallow every Ctrl+C and become uninterruptible. Instead shield the
    parent with a no-op *Python* handler: a function disposition resets to SIG_DFL
    on exec, so the child gets a normal KeyboardInterrupt while this parent just
    ignores the signal in its own process."""
    prev = signal.signal(signal.SIGINT, lambda *a: None) if shield_sigint else None
    env = {**os.environ, "PYTHONPATH": HERE + os.pathsep + os.environ.get("PYTHONPATH", "")}
    try:
        subprocess.run([sys.executable, AI] + args, env=env)
    finally:
        if prev is not None:
            signal.signal(signal.SIGINT, prev)


def _prompt(label):
    try:
        return input(c("36", label)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def do_ask():
    q = _prompt("question> ")
    if q:
        # Honour the session brain toggle for one-shot too (ai.py accepts a leading --local).
        launch((["--local"] if STATE["local"] else []) + [q])


def do_agent():
    task = _prompt("task> ")
    if not task:
        return
    args = ["agent", task]
    if STATE["local"]:             args.append("--local")
    if STATE["approve"] == "auto": args += ["--approve", "auto"]
    if STATE["dry_run"]:           args.append("--dry-run")
    print(c("2", f"  $ ai {' '.join(args)}"))
    launch(args, shield_sigint=True)


def menu():
    while True:
        print()
        print(c("1;36", "  ai — CTF assistant"))
        print(f"  brain   : {brain_line()}")
        print(f"  options : approve={c('33', STATE['approve'])}   "
              f"dry-run={c('33', 'on' if STATE['dry_run'] else 'off')}")
        print()
        print("  [a] ask a question (one-shot)")
        print("  [g] run the agent on a task")
        print("  [r] resume the last agent run")
        print(c("2", "  [l] local/remote brain    [x] approve-auto    [d] dry-run"))
        print("  [q] quit")
        ch = _prompt("  > ").lower()
        if   ch == "a": do_ask()
        elif ch == "g": do_agent()
        elif ch == "r": launch(["agent", "--resume"], shield_sigint=True)
        elif ch == "l": STATE["local"]   = not STATE["local"]
        elif ch == "x": STATE["approve"] = "manual" if STATE["approve"] == "auto" else "auto"
        elif ch == "d": STATE["dry_run"] = not STATE["dry_run"]
        elif ch in ("q", "quit", "exit", ""):
            return


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] in ("-h", "--help"):
            print(__doc__)
            return
        # passthrough; shield Ctrl+C only for the agent subcommand
        launch(sys.argv[1:], shield_sigint=(sys.argv[1] == "agent"))
    else:
        menu()


if __name__ == "__main__":
    main()
