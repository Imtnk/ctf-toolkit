import json, sys, urllib.request, urllib.error
from . import config

# Warn only once if the remote brain is selected but no key is configured.
_warned_no_key = False


def _errbody(e):
    """Read up to 300 chars of an HTTPError body — never the key/headers."""
    try:
        return e.read().decode("utf-8", "replace")[:300]
    except Exception:
        return ""


def _chat_remote(messages, model, temperature, echo=True):
    """OpenAI-compatible chat completion (the remote 'brain'), STREAMING via SSE.

    Sends "stream": true and reads the server-sent-event chunks as they arrive,
    echoing deltas to stderr (when `echo` and it's a TTY) so the user SEES the
    brain produce output in real time — and so a Ctrl+C lands between chunks and
    cancels promptly instead of blocking for up to REMOTE_TIMEOUT. Accumulates
    and returns the full content. Falls back to a non-streaming request if the
    gateway rejects streaming. stdlib urllib only; the API key is NEVER echoed.

    `echo` is set False for internal calls (refusal classifier, answer
    verification) so their tokens don't spray the terminal.
    """
    echo = echo and sys.stderr.isatty()

    def _open(stream):
        payload = json.dumps({
            "model": model,
            "temperature": temperature,
            "max_tokens": config.REMOTE_MAX_TOKENS,
            "stream": stream,
            "messages": messages,
        }).encode()
        req = urllib.request.Request(
            f"{config.REMOTE_BASE_URL}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.REMOTE_API_KEY}",
                # Cloudflare 403s (error 1010) the default Python-urllib UA;
                # present a browser UA so the request reaches the API.
                "User-Agent": config.REMOTE_USER_AGENT,
            },
        )
        return urllib.request.urlopen(req, timeout=config.REMOTE_TIMEOUT)

    def _stream():
        parts = []
        with _open(True) as r:
            for raw_line in r:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta", {}) or {}
                think = delta.get("reasoning_content") or ""
                piece = delta.get("content") or ""
                if think and echo:
                    sys.stderr.write(f"\033[90m{think}\033[0m"); sys.stderr.flush()
                if piece:
                    parts.append(piece)
                    if echo:
                        sys.stderr.write(piece); sys.stderr.flush()
            if echo:
                sys.stderr.write("\n"); sys.stderr.flush()
        return "".join(parts)

    def _nonstream():
        with _open(False) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"]

    try:
        return _stream()
    except urllib.error.HTTPError as e:
        if e.code in (400, 404, 405):        # gateway may not support streaming
            try:
                return _nonstream()
            except urllib.error.HTTPError as e2:
                raise RuntimeError(f"remote brain HTTP {e2.code} ({model}): {_errbody(e2)}") from None
            except urllib.error.URLError as e2:
                raise RuntimeError(f"remote brain unreachable ({config.REMOTE_BASE_URL}): {e2.reason}") from None
        raise RuntimeError(f"remote brain HTTP {e.code} ({model}): {_errbody(e)}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"remote brain unreachable ({config.REMOTE_BASE_URL}): {e.reason}") from None


def _chat_ollama(messages, model, host, num_ctx, temperature):
    payload = json.dumps({
        "model": model,
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": temperature},
        "messages": messages,
    }).encode()

    req = urllib.request.Request(
        f"http://{host}:{config.PORT}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["message"]["content"]


def chat(messages, model=None, host=None, num_ctx=None, temperature=None, stream_echo=True):
    """`stream_echo=False` suppresses live token echo — used for internal calls
    (refusal classification, answer verification) so they don't spam the terminal.
    Only affects the remote streaming path; the Ollama path is non-streaming."""
    global _warned_no_key
    model       = model       or config.BRAIN_MODEL
    host        = host        or config.HOST
    num_ctx     = num_ctx     or config.NUM_CTX
    temperature = temperature if temperature is not None else config.TEMPERATURE

    if config.is_remote(model):
        if not config.REMOTE_API_KEY:
            # Graceful degrade: no key → fall back to the local model, warn once.
            if not _warned_no_key:
                print("\033[33m[llm] remote brain selected but CTF_REMOTE_API_KEY is unset — "
                      f"falling back to local {config.LOCAL_MODEL}\033[0m", file=sys.stderr)
                _warned_no_key = True
            return _chat_ollama(messages, config.LOCAL_MODEL, host, num_ctx, temperature)
        return _chat_remote(messages, model, temperature, echo=stream_echo)

    return _chat_ollama(messages, model, host, num_ctx, temperature)
