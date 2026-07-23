"""Three-tier command approval — Phase 2.

Tier 1 (auto):  allowlist of read-only/safe triage patterns — never prompts.
Tier 2 (ask):   everything else — prompts user; "always" option learns a new rule.
Tier 3 (deny):  denylist backstop — hard-blocks even under --approve auto.

The session-learned allowlist grows via the "a(lways)" prompt option.
"""
import re, sys
from typing import Literal

Verdict = Literal["auto", "ask", "deny"]

# ── Denylist — hard-blocked regardless of --approve auto ─────────────────────
# Fail-safe: blocklists have gaps, so this is a backstop only.
_DENYLIST_PATTERNS: list[str] = [
    r"\brm\s+-[a-z]*r",           # rm -r, rm -rf, rm -fr, rm -Rf …
    r"\brmdir\b",
    r":\(\)\s*\{.*\}",            # fork bomb  :(){:|:&};:
    r"\bdd\b.*\bof=/dev/",        # overwrite raw device
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bparted\b",
    r"\bsudo\b",                   # never auto-sudo
    r"\bcurl\b[^|]*\|\s*(ba)?sh", # curl | sh
    r"\bwget\b[^|]*\|\s*(ba)?sh", # wget | sh
    r">\s*/dev/sd[a-z]",          # raw disk write
    r"\bshred\b",
    r"\bpoweroff\b|\breboot\b|\bshutdown\b",
]

# ── Allowlist — auto-approve: read-only triage and safe helpers ───────────────
# Matched against the full command string (stripped).
_ALLOWLIST_PATTERNS: list[str] = [
    # Binary triage
    r"^file\s+",
    r"^strings\s+",
    r"^hexdump\b",
    r"^xxd\b",
    r"^objdump\b",
    r"^readelf\b",
    r"^nm\b",
    r"^checksec\b",
    r"^binwalk\b(?!.*\s-e)",      # binwalk without -e (extract)
    # Filesystem / navigation
    r"^ls\b",
    r"^cat\s+\S",                 # cat <file> (not cat with no args or pipes)
    r"^head\b",
    r"^tail\b",
    r"^wc\b",
    r"^find\b(?!.*-exec\s+(?!ls|file|strings|wc|cat))",  # find without dangerous -exec
    r"^pwd$",
    r"^echo\b",
    # Search / hashing
    r"^grep\b",
    r"^md5sum\b|^sha\d*sum\b",
    r"^which\b|^type\b",
    r"^env$|^printenv\b",
    # System info (read-only)
    r"^id$|^whoami$",
    r"^uname\b|^hostname$",
    r"^lsof\b(?!.*-i)",           # lsof without network opts
    # Network recon (active but non-destructive)
    r"^nmap\b",
    # Crypto / encoding inspection
    r"^base64\b",
    r"^openssl\s+(x509|rsa|ec|dhparam|prime|asn1parse|dgst|enc\s+-d)\b",
    # Safe python one-liners (print/decode only)
    r'^python3?\s+-c\s+["\']?\s*(?:print|import\s+base64|import\s+binascii|import\s+struct)',
]

_denylist  = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _DENYLIST_PATTERNS]
_allowlist = [re.compile(p, re.IGNORECASE) for p in _ALLOWLIST_PATTERNS]
_learned:  list[re.Pattern] = []   # session-learned entries


# ── Core logic ────────────────────────────────────────────────────────────────

def verdict(cmd: str) -> Verdict:
    c = cmd.strip()
    if any(p.search(c) for p in _denylist):
        return "deny"
    if any(p.search(c) for p in _allowlist) or any(p.search(c) for p in _learned):
        return "auto"
    return "ask"


def check(cmd: str, auto_approve: bool = False) -> bool:
    """Return True if the command should run, False if blocked or denied by user.

    Denylist always wins. Allowlist (incl. learned) auto-approves.
    Tier 2 (ask): prompts unless auto_approve=True.
    """
    v = verdict(cmd)

    if v == "deny":
        _print_deny(cmd)
        return False

    if v == "auto":
        return True

    # Tier 2
    if auto_approve:
        return True

    return _prompt(cmd)


def _print_deny(cmd: str) -> None:
    print(f"\n  \033[31m[BLOCKED]\033[0m denylist match — will not run: {cmd!r}", file=sys.stderr)


def _prompt(cmd: str) -> bool:
    print(f"\n  \033[33m[approval]\033[0m {cmd!r}")
    print("  [y] run once   [a] always allow commands like this   [N] deny")
    try:
        ans = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if ans == "y":
        return True
    if ans == "a":
        _learn(cmd)
        return True
    return False


def _learn(cmd: str) -> None:
    """Append a prefix rule for cmd's leading binary to the session allowlist."""
    token = cmd.strip().split()[0]
    # Escape the binary name; match it at the start of any future command
    pattern = re.compile(r"^" + re.escape(token) + r"\b", re.IGNORECASE)
    _learned.append(pattern)
    print(f"  \033[32m[allowlist]\033[0m commands starting with \033[1m{token!r}\033[0m are now auto-approved for this session.")


# ── write_file special gate ───────────────────────────────────────────────────

def check_write(path: str, new_text: str) -> bool:
    """Always prompt for write_file — show a diff first. Ignores auto_approve."""
    import difflib, os as _os
    print(f"\n  \033[33m[write_file]\033[0m {path!r}")
    if _os.path.exists(path):
        with open(path, "r", errors="replace") as f:
            old_lines = f.readlines()
        new_lines = new_text.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=path, tofile=path + " (new)"))
        if not diff:
            print("  (no changes — skipping write)")
            return False
        print("".join(diff[:60]) + ("  [... diff truncated]\n" if len(diff) > 60 else ""))
    else:
        preview = new_text[:500] + ("…" if len(new_text) > 500 else "")
        print(f"  [new file, {len(new_text)} chars]\n{preview}")

    print("  [y] write   [N] cancel")
    try:
        ans = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans == "y"


# ── Introspection helpers ─────────────────────────────────────────────────────

def tier_label(cmd: str) -> str:
    return {"auto": "auto", "ask": "needs-approval", "deny": "BLOCKED"}[verdict(cmd)]
