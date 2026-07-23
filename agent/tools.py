"""Tool registry — Phase 5: full CTF tool set with streaming support.

Each entry: {"fn": callable, "description": str, "schema": str}
The schema is injected verbatim into the system prompt tool catalog.

Execution model
---------------
- run_shell / python_exec  : arbitrary execution — go through the approval gate in loop.py
- write_file               : always shows diff + prompts, even under --approve auto
- read_file / list_dir / file_info / hexdump / strings : read-only, auto-approved
- http_request             : network I/O, goes through the gate
- finish                   : terminal action, no gate
"""
import binascii, hashlib, os, subprocess, sys, threading, time, urllib.request, urllib.error
from typing import Any, Callable

_registry: dict[str, dict] = {}


def _tool(name: str, description: str, schema: str):
    def decorator(fn):
        _registry[name] = {"fn": fn, "description": description, "schema": schema}
        return fn
    return decorator


# ── Execution tools ────────────────────────────────────────────────────────────

@_tool(
    "run_shell",
    "Run a shell command; returns stdout+stderr.",
    '{"thought":"<reason>","tool":"run_shell","args":{"cmd":"<shell command>"}}',
)
def run_shell(cmd: str, timeout: int = 30, cwd: str | None = None,
              _stream_to: Callable[[str], None] | None = None):
    t0    = time.monotonic()
    lines: list[str] = []

    try:
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd,
        )

        def _reader():
            for line in iter(proc.stdout.readline, ""):
                lines.append(line)
                if _stream_to:
                    _stream_to(line)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            proc.kill()
            t.join(1)
            return f"[timed out after {timeout}s]\n" + "".join(lines), float(timeout)

        proc.wait()
        return "".join(lines).strip() or "(no output)", time.monotonic() - t0

    except Exception as e:
        return f"[run_shell error] {e}", time.monotonic() - t0


@_tool(
    "python_exec",
    "Run a Python 3 snippet; ideal for pwntools/pycryptodome/sympy/z3 one-liners.",
    '{"thought":"<reason>","tool":"python_exec","args":{"code":"import base64; print(base64.b64decode(\'aGVsbG8=\'))"}}',
)
def python_exec(code: str, timeout: int = 30,
                _stream_to: Callable[[str], None] | None = None):
    t0    = time.monotonic()
    lines: list[str] = []

    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True,
        )

        def _reader():
            for line in iter(proc.stdout.readline, ""):
                lines.append(line)
                if _stream_to:
                    _stream_to(line)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            proc.kill()
            t.join(1)
            return f"[timed out after {timeout}s]\n" + "".join(lines), float(timeout)

        proc.wait()
        return "".join(lines).strip() or "(no output)", time.monotonic() - t0

    except Exception as e:
        return f"[python_exec error] {e}", time.monotonic() - t0


# ── File I/O ───────────────────────────────────────────────────────────────────

_READ_LIMIT = 8 * 1024   # 8 KB


@_tool(
    "read_file",
    f"Read a text file (up to {_READ_LIMIT // 1024} KB). Use hexdump for binaries.",
    '{"thought":"<reason>","tool":"read_file","args":{"path":"./flag.txt"}}',
)
def read_file(path: str):
    t0 = time.monotonic()
    try:
        size = os.path.getsize(path)
        with open(path, "r", errors="replace") as f:
            content = f.read(_READ_LIMIT)
        suffix = f"\n[... file is {size} bytes; truncated to {_READ_LIMIT} bytes]" if size > _READ_LIMIT else ""
        return content + suffix, time.monotonic() - t0
    except OSError as e:
        return f"[read_file error] {e}", 0.0


@_tool(
    "write_file",
    "Write text to a file. Always shows a diff and asks for confirmation.",
    '{"thought":"<reason>","tool":"write_file","args":{"path":"./exploit.py","text":"#!/usr/bin/env python3\\n..."}}',
)
def write_file(path: str, text: str):
    # Approval (diff + prompt) is handled by loop._gate before this runs.
    t0 = time.monotonic()
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return f"[wrote {len(text)} bytes to {path}]", time.monotonic() - t0
    except OSError as e:
        return f"[write_file error] {e}", 0.0


# ── Directory listing ──────────────────────────────────────────────────────────

@_tool(
    "list_dir",
    "List a directory (name, type, size).",
    '{"thought":"<reason>","tool":"list_dir","args":{"path":"."}}',
)
def list_dir(path: str = "."):
    t0 = time.monotonic()
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name))
        lines = []
        for e in entries:
            try:
                size = e.stat().st_size
                kind = "DIR" if e.is_dir() else f"{size:>10} B"
            except OSError:
                kind = "?"
            lines.append(f"{'d' if e.is_dir() else '-'}  {kind:>12}  {e.name}")
        return "\n".join(lines) or "(empty)", time.monotonic() - t0
    except OSError as e:
        return f"[list_dir error] {e}", 0.0


# ── Binary triage ──────────────────────────────────────────────────────────────

@_tool(
    "file_info",
    "Report file type (via `file`), size, and SHA-256 hash.",
    '{"thought":"<reason>","tool":"file_info","args":{"path":"./chal"}}',
)
def file_info(path: str):
    t0 = time.monotonic()
    try:
        stat  = os.stat(path)
        sha   = hashlib.sha256(open(path, "rb").read()).hexdigest()
        ftype = subprocess.run(
            ["file", path], capture_output=True, text=True
        ).stdout.strip()
        result = f"{ftype}\nsize:   {stat.st_size} bytes\nsha256: {sha}"
        return result, time.monotonic() - t0
    except OSError as e:
        return f"[file_info error] {e}", 0.0


@_tool(
    "hexdump",
    "Hex+ASCII dump of the first n bytes of a file (default 256).",
    '{"thought":"<reason>","tool":"hexdump","args":{"path":"./chal","n":256}}',
)
def hexdump(path: str, n: int = 256):
    t0 = time.monotonic()
    try:
        raw = open(path, "rb").read(n)
        lines = []
        for i in range(0, len(raw), 16):
            chunk = raw[i : i + 16]
            hex_  = " ".join(f"{b:02x}" for b in chunk)
            asc   = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{i:08x}  {hex_:<47}  |{asc}|")
        out = "\n".join(lines) or "(empty file)"
        suffix = f"\n[showing first {n} of {os.path.getsize(path)} bytes]" if os.path.getsize(path) > n else ""
        return out + suffix, time.monotonic() - t0
    except OSError as e:
        return f"[hexdump error] {e}", 0.0


@_tool(
    "strings",
    "Extract printable strings from a file (default min length 4).",
    '{"thought":"<reason>","tool":"strings","args":{"path":"./chal","min_len":4}}',
)
def strings(path: str, min_len: int = 4):
    t0 = time.monotonic()
    import re as _re

    def _py_strings(data: bytes) -> str:
        found = _re.findall(rb"[ -~]{" + str(min_len).encode() + rb",}", data)
        return b"\n".join(found).decode(errors="replace")

    try:
        proc = subprocess.run(
            ["strings", f"-n{min_len}", path],
            capture_output=True, text=True, timeout=30,
        )
        out = proc.stdout.strip()
        if out:
            return out, time.monotonic() - t0
        # macOS strings only scans Mach-O segments — fall back to pure Python
        raw = open(path, "rb").read()
        return _py_strings(raw) or "(no strings found)", time.monotonic() - t0
    except FileNotFoundError:
        raw = open(path, "rb").read()
        return _py_strings(raw) or "(no strings found)", time.monotonic() - t0
    except subprocess.TimeoutExpired:
        return "[timed out]", 30.0


# ── Network ────────────────────────────────────────────────────────────────────

@_tool(
    "http_request",
    "Make an HTTP request. Useful for web challenges.",
    '{"thought":"<reason>","tool":"http_request","args":{"method":"GET","url":"http://10.10.10.10/flag","headers":{},"body":null}}',
)
def http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout: int = 15,
):
    t0 = time.monotonic()
    try:
        data = body.encode() if body else None
        req  = urllib.request.Request(url, data=data, headers=headers or {}, method=method.upper())
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status  = r.status
            rbody   = r.read(8192).decode(errors="replace")
            rhdrs   = dict(r.headers)
        out = f"HTTP {status}\n"
        out += "\n".join(f"{k}: {v}" for k, v in rhdrs.items()) + "\n\n"
        out += rbody
        return out, time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} {e.reason}\n{e.read(2048).decode(errors='replace')}", time.monotonic() - t0
    except Exception as e:
        return f"[http_request error] {e}", 0.0


# ── Terminal ───────────────────────────────────────────────────────────────────

@_tool(
    "finish",
    "End the loop with a final answer or flag.",
    '{"thought":"<summary>","tool":"finish","args":{"answer":"<flag or result>"}}',
)
def finish(answer: str):
    return answer, 0.0


# ── Registry helpers ───────────────────────────────────────────────────────────

def catalog() -> str:
    lines = []
    for name, meta in _registry.items():
        lines.append(f"  {name}: {meta['description']}")
        lines.append(f"    example: {meta['schema']}")
    return "\n".join(lines)


_STREAMING_TOOLS = frozenset({"run_shell", "python_exec"})


def dispatch(
    name: str,
    args: dict,
    stream_to: Callable[[str], None] | None = None,
) -> tuple[Any, float]:
    if name not in _registry:
        raise KeyError(f"unknown tool: {name!r}")
    fn = _registry[name]["fn"]
    if stream_to and name in _STREAMING_TOOLS:
        return fn(**args, _stream_to=stream_to)
    return fn(**args)


def known(name: str) -> bool:
    return name in _registry
