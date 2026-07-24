#!/usr/bin/env python3
"""CTF AI helper — remote gateway brain by default, local Ollama fallback.

One-shot (brain: remote gateway by default, else local Ollama; --local forces local):
    echo "solve this RSA: n=... e=... c=..." | python3 ai.py
    cat challenge.py | python3 ai.py "find the vulnerability"
    python3 ai.py --local "quick question"        # force the local Ollama brain

Agentic loop (ReAct, multi-step):
    python3 ai.py agent "what type is ./chal and what are its strings?"
    python3 ai.py agent --approve auto "exploit ./chal"
    python3 ai.py agent --dry-run "what would you do with ./chal?"
    python3 ai.py agent -m dolphin "..."
"""
import sys, os, urllib.request, argparse

# Ollama host. Defaults to localhost (the Mac runs the model server locally);
# remote clients (e.g. Kali over LAN) export CTF_AI_HOST=192.168.1.11
HOST  = os.environ.get("CTF_AI_HOST", "localhost")

ONESHOT_SYSTEM = "You are a CTF expert. Be direct and provide working solutions."


def server_up(timeout=4):
    """Fast preflight so an unreachable/asleep Mac fails in ~4 s instead of a ~2-min OS connect
    timeout. Local Kali stopgap re-added 2026-07-22 — pending upstream into the repo (see §11 T5
    in local-ai-ctf-setup). Kept separate from the request call, which must have no read timeout."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:11434", timeout=timeout):
            return True
    except Exception:
        return False


def cmd_agent(args):
    from agent import loop, config, transcript as tr

    # Brain selection: explicit -m wins; --local forces the local Ollama model;
    # otherwise the configured default brain (remote unless CTF_BRAIN=local).
    if args.model:
        model = args.model
    elif getattr(args, "local", False):
        model = config.LOCAL_MODEL
    else:
        model = config.BRAIN_MODEL

    # Preflight: if the brain is remote but no key is configured, degrade to local
    # up front (llm.chat() would otherwise warn+fallback on the first call).
    if config.is_remote(model) and not config.REMOTE_API_KEY:
        print(f"[ai.py] remote brain '{model}' selected but CTF_REMOTE_API_KEY is unset — "
              f"using local {config.LOCAL_MODEL} instead", file=sys.stderr)
        model = config.LOCAL_MODEL
    elif config.is_remote(model):
        print(f"[ai.py] brain: {model} (remote)")

    # ── resume path ───────────────────────────────────────────────────────────
    resume_messages = None
    if args.resume is not None:
        path = args.resume if args.resume else tr.latest_run()
        if not path:
            sys.exit("no transcript found to resume — run a task first")
        saved_task, saved_model, resume_messages = tr.load_resume(path)
        print(f"[resuming] {path}")
        print(f"[task]     {saved_task}")
        task  = args.task or saved_task
        model = args.model or saved_model or model
        # Prepend system prompt (will be rebuilt by loop.run)
        from agent.loop import _build_system
        if not resume_messages or resume_messages[0].get("role") != "system":
            resume_messages.insert(0, {"role": "system", "content": _build_system()})
    else:
        task = args.task
        if not task:
            sys.exit('usage: ai.py agent [options] "<task>"')

    try:
        result = loop.run(
            task=task,
            model=model,
            host=config.HOST,
            max_steps=args.max_steps,
            auto_approve=(args.approve == "auto"),
            dry_run=args.dry_run,
            resume_messages=resume_messages,
        )
    except KeyboardInterrupt:
        # Belt-and-suspenders: the loop handles Ctrl+C during the main model call
        # (steer/resume/abort); this catches it anywhere else so we exit cleanly
        # with no traceback.
        print("\n[interrupted — agent stopped]")
        return
    if result:
        print(f"\n{'═'*60}\nResult: {result}\n{'═'*60}")
    else:
        print("\n[agent exited without a result]")


def cmd_oneshot(prompt, force_local=False):
    """One-shot Q&A. Same brain policy as the agent: the remote gateway by default
    (when a key is set and not --local/CTF_BRAIN=local), else local Ollama; a remote
    failure degrades to local. The final answer prints to stdout (pipe-friendly)."""
    if not prompt:
        sys.exit("usage: ai.py [--local] [prompt]   (and/or pipe content on stdin)")
    from agent import config, llm

    model = config.LOCAL_MODEL if force_local else config.BRAIN_MODEL
    if config.is_remote(model) and not config.REMOTE_API_KEY:
        model = config.LOCAL_MODEL   # no key → local (llm.chat would warn+fallback anyway)

    messages = [{"role": "system", "content": ONESHOT_SYSTEM},
                {"role": "user",   "content": prompt}]

    if config.is_remote(model):
        try:
            # stream_echo=False keeps stdout clean for piping; the final answer is printed below.
            print(llm.chat(messages, model=model, temperature=0.15, stream_echo=False))
            return
        except Exception as e:
            print(f"[ai.py] remote brain failed ({e}) — falling back to local", file=sys.stderr)
            model = config.LOCAL_MODEL

    # Local Ollama path (default fallback / --local).
    if not server_up():
        sys.exit(f"[ai.py] Ollama not reachable at {HOST}:11434 — is it running and reachable? "
                 f"(export CTF_AI_HOST=<ip> if its LAN address changed)")
    print(llm.chat(messages, model=model, host=config.HOST, num_ctx=8192, temperature=0.15))


def main():
    # Detect 'agent' subcommand before argparse so that positional prompts
    # like `ai.py "question"` still work without any subcommand.
    if len(sys.argv) > 1 and sys.argv[1] == "agent":
        p = argparse.ArgumentParser(
            prog="ai.py agent",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=(
                "Brain: defaults to the remote gateway (CTF_REMOTE_MODEL) when\n"
                "CTF_REMOTE_API_KEY is set and CTF_BRAIN != local; else local Ollama\n"
                "(CTF_AI_HOST). A remote error falls back to local automatically;\n"
                "local dolphin is the refusal fallback. Ctrl+C mid-run to steer/abort.\n"
                "Key lives in ~/.config/ctf-toolchain/secrets.env (never committed)."
            ),
        )
        p.add_argument("task", nargs="?", default="", help="Task description")
        p.add_argument("-m", "--model", default="", help="Model override (local Ollama model id)")
        p.add_argument("--local", action="store_true",
                       help="Force the local Ollama brain instead of the remote gateway")
        p.add_argument("--approve", choices=["auto", "manual"], default="manual",
                       help="auto = skip prompts for non-allowlisted commands (default: manual)")
        p.add_argument("--dry-run", action="store_true",
                       help="Show planned commands; execute nothing")
        p.add_argument("--max-steps", type=int, default=15,
                       help="Steps before the soft-budget pause (default: 15)")
        p.add_argument(
            "--resume", nargs="?", const="",
            metavar="FILE",
            help="Resume the latest run (or a specific .agent/*.jsonl file)",
        )
        args = p.parse_args(sys.argv[2:])
        cmd_agent(args)
    else:
        # One-shot: a leading --local/--remote toggles the brain; the rest is the prompt.
        argv = sys.argv[1:]
        force_local = False
        while argv and argv[0] in ("--local", "--remote"):
            force_local = argv.pop(0) == "--local"
        stdin  = "" if sys.stdin.isatty() else sys.stdin.read()
        cli    = " ".join(argv)
        prompt = f"{cli}\n\n{stdin}".strip() if stdin and cli else (stdin or cli)
        cmd_oneshot(prompt, force_local=force_local)


if __name__ == "__main__":
    main()
