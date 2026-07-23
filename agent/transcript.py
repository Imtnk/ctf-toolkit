"""Persist agent runs to .agent/run-<ts>.jsonl for audit and --resume.

File format: one JSON object per line.
  {"type":"start",  "task":..., "model":..., "ts":...}
  {"type":"step",   "step":N, "messages":[...new messages...], "ts":...}
  {"type":"finish", "answer":..., "ts":...}

Resume: replay all "step" messages to reconstruct conversation state.
"""
import json, os, time
from datetime import datetime

AGENT_DIR = ".agent"


def new_run(task: str, model: str) -> str:
    """Open a new transcript file and write the header. Returns the file path."""
    os.makedirs(AGENT_DIR, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(AGENT_DIR, f"run-{ts}.jsonl")
    _append(path, {"type": "start", "task": task, "model": model, "ts": time.time()})
    return path


def append_step(path: str, step: int, new_messages: list) -> None:
    _append(path, {"type": "step", "step": step, "messages": new_messages, "ts": time.time()})


def append_finish(path: str, answer: str) -> None:
    _append(path, {"type": "finish", "answer": answer, "ts": time.time()})


def _append(path: str, obj: dict) -> None:
    try:
        with open(path, "a") as f:
            f.write(json.dumps(obj) + "\n")
    except OSError:
        pass   # never crash the agent over transcript I/O


def latest_run() -> str | None:
    """Return the most recent run file path, or None."""
    if not os.path.isdir(AGENT_DIR):
        return None
    files = sorted(
        (f for f in os.listdir(AGENT_DIR) if f.startswith("run-") and f.endswith(".jsonl")),
        reverse=True,
    )
    return os.path.join(AGENT_DIR, files[0]) if files else None


def load_resume(path: str) -> tuple[str, str, list]:
    """Reconstruct (task, model, messages) from a transcript file.

    The system prompt is NOT included in the saved messages — it is rebuilt
    fresh at resume time by loop.run() so changes to the catalog take effect.
    The saved conversation starts from the initial user task onward.
    """
    task     = ""
    model    = ""
    messages: list = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = obj.get("type")
            if t == "start":
                task  = obj.get("task", "")
                model = obj.get("model", "")
            elif t == "step":
                messages.extend(obj.get("messages", []))

    return task, model, messages
