"""Refusal detection and model fallback — Phase 5.

The plan is explicit: do NOT substring-match tool output.
A strings/hexdump observation can literally contain "I cannot help".
Instead, send the suspicious response to a separate clean-context classification
call where no tool output is present.

Fallback model: dolphin-llama3:8b (uncensored).
"""
import re
from . import config, llm

_SYSTEM = "You are a binary classifier. Answer with ONLY 'yes' or 'no'. No other text."
_USER   = (
    "Is the following text a refusal to assist with a security research task? "
    "Answer 'yes' if it declines, refuses, or says it cannot help. "
    "Answer 'no' if it attempts to help (even if imperfectly).\n\n"
    "Text:\n{text}\n\nAnswer yes or no:"
)


def is_refusal(raw: str, model: str, host: str) -> bool:
    """Classify raw model output as a refusal using a clean-context call.

    Uses the same model that produced the response so we don't need an extra
    model loaded. The classification prompt contains NO tool output.
    """
    # Strip deepseek-r1 think tags before inspecting
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if not cleaned:
        return False

    try:
        reply = llm.chat(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": _USER.format(text=cleaned[:600])},
            ],
            model=model,
            host=host,
            temperature=0,
            num_ctx=512,       # tiny context — this is just a classifier call
            stream_echo=False,  # internal call — don't spray tokens at the terminal
        )
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip().lower()
        return reply.startswith("yes")
    except Exception:
        return False


def fallback_model() -> str:
    return config.FALLBACK
