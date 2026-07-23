"""Context management — Phase 5.

Keeps message history from growing unboundedly by truncating old observations
while preserving a pinned-facts block the model always sees.

Pinned facts: target description, flag format, confirmed findings, current plan.
These are extracted automatically from the task and observations, and can be
updated by the model's `thought` field when it records intent.
"""
import re

MAX_MESSAGES = 40   # soft cap before truncation kicks in
KEEP_RECENT  = 12   # how many trailing messages to preserve post-truncation

# Flag-like pattern: WORD{content}
_FLAG_RE = re.compile(r"[A-Za-z0-9_]{2,10}\{[^}]{1,80}\}")
# Flag format hint in task text: "flag format: FLAG{...}"
_FORMAT_RE = re.compile(r"flag\s+format[:\s]+([A-Za-z0-9_]+\{[^}]*\})", re.IGNORECASE)


def make_pinned(task: str) -> dict:
    """Initialise a pinned-facts dict from the task description."""
    pinned: dict = {"target": "", "flag_format": "", "findings": [], "plan": ""}
    # Try to extract a flag format hint from the task
    m = _FORMAT_RE.search(task)
    if m:
        pinned["flag_format"] = m.group(1)
    # Use the task itself as the initial target description (first sentence)
    first_sentence = task.split(".")[0].strip()
    pinned["target"] = first_sentence[:200]
    return pinned


def auto_update(pinned: dict, observation: str) -> None:
    """Scan an observation for flag-like strings and add them to findings."""
    for flag in _FLAG_RE.findall(observation):
        if flag not in pinned["findings"]:
            pinned["findings"].append(flag)


def format_pinned(pinned: dict) -> str:
    parts = []
    if pinned.get("target"):
        parts.append(f"Task: {pinned['target']}")
    if pinned.get("flag_format"):
        parts.append(f"Flag format: {pinned['flag_format']}")
    if pinned.get("findings"):
        parts.append("Confirmed findings:")
        for f in pinned["findings"]:
            parts.append(f"  • {f}")
    if pinned.get("plan"):
        parts.append(f"Current plan: {pinned['plan']}")
    return "\n".join(parts) if parts else "(none yet)"


def _chars(msgs: list) -> int:
    return sum(len(m.get("content", "")) for m in msgs)


def maybe_truncate(messages: list, pinned: dict, max_chars: int | None = None) -> list:
    """Return a pruned copy of messages when it grows too large.

    Triggers when either the message COUNT exceeds MAX_MESSAGES or (when
    max_chars is given) the total content length exceeds that char budget —
    the latter is what actually keeps the prompt within the active model's
    context window (see config.context_char_budget). A fixed message count is
    not a real bound: ~12 recent observations at MAX_OBS_CHARS each can dwarf a
    small local window while fitting comfortably in a large remote one.

    Preserved structure:
      [0] system prompt
      [1] initial user task
      [pinned facts block]
      [truncation notice]
      [...as many trailing messages as fit, capped at KEEP_RECENT]
    """
    over_count = len(messages) > MAX_MESSAGES
    over_chars = max_chars is not None and _chars(messages) > max_chars
    if not over_count and not over_chars:
        return messages

    system_msg   = messages[0]
    initial_task = messages[1] if len(messages) > 1 else None

    head = [system_msg]
    if initial_task:
        head.append(initial_task)
    head.append({
        "role": "user",
        "content": f"[pinned context — earlier steps truncated]\n{format_pinned(pinned)}",
    })
    head.append({
        "role": "user",
        "content": "[earlier observations truncated to reduce context length]",
    })

    recent = messages[-KEEP_RECENT:]
    # If a char budget applies, drop the oldest of the recent window until the
    # whole prompt fits — but always keep at least the latest message.
    if max_chars is not None:
        budget = max_chars - _chars(head)
        while len(recent) > 1 and _chars(recent) > budget:
            recent = recent[1:]

    return head + recent
