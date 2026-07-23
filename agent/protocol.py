"""Extract the first valid JSON object from model output.

Handles:
  - deepseek-r1 <think>...</think> blocks (stripped before parsing)
  - ```json ... ``` fences
  - Leading prose before the first {
  - Nested braces
"""
import json, re


def extract_json(text: str) -> dict:
    # deepseek-r1 wraps reasoning in <think> tags — strip before parsing
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Try ```json fence first (most explicit)
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Walk from the first { to its matching } (handles nested objects)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON object found in model output:\n{text[:300]}")

    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as e:
                    raise ValueError(f"JSON parse error: {e}\nraw slice: {text[start:i+1][:300]}")

    raise ValueError(f"unmatched braces in model output:\n{text[:300]}")


def validate(obj: dict) -> None:
    """Raise ValueError if the parsed call is missing required fields."""
    if "thought" not in obj:
        raise ValueError('missing required field "thought"')
    if "tool" not in obj:
        raise ValueError('missing required field "tool"')
    if "args" not in obj:
        raise ValueError('missing required field "args"')
    if not isinstance(obj["args"], dict):
        raise ValueError('"args" must be a JSON object')
