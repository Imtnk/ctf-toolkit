# Memory Forensics

You're given a **RAM dump** (`.raw`, `.mem`, `.vmem`, `.dmp`, often several GB). The flag lives in a running process, a command history, a clipboard, a browser tab, or a file that was open. **Volatility 3** is the tool.

## Recognise a memory dump

- Multi-GB file, `file` says `data` or `ELF core dump`.
- Challenge text mentions "memory", "RAM", "dump", "we captured the machine's state".

## Volatility 3 basics

No profile needed (unlike Vol2 — it auto-detects). Syntax:
```bash
vol -f dump.raw <plugin>
```

### Windows triage playbook
```bash
vol -f dump.raw windows.info               # confirm OS/build
vol -f dump.raw windows.pslist             # running processes
vol -f dump.raw windows.pstree             # process parent/child tree
vol -f dump.raw windows.cmdline            # command lines (flags hide here!)
vol -f dump.raw windows.filescan | grep -i flag    # files in memory
vol -f dump.raw windows.dumpfiles --viraddr <addr>  # extract a file
vol -f dump.raw windows.hashdump           # user password hashes
vol -f dump.raw windows.netscan            # network connections
```

### Common flag locations
| Where | Plugin |
|---|---|
| A command that was typed | `windows.cmdline`, `windows.consoles` |
| An open Notepad / editor | `windows.memmap` + dump, or `windows.filescan` then `dumpfiles` |
| Clipboard | `windows.clipboard` (may need extended plugins) |
| Browser / process memory | dump the process with `windows.memmap --dump --pid <pid>` then `strings | grep flag` |
| Environment variables | `windows.envars` |
| Registry | `windows.registry.printkey` |

### Linux dumps
```bash
vol -f dump.raw linux.bash        # bash history — very common flag spot
vol -f dump.raw linux.pslist
vol -f dump.raw linux.psaux
```

## The lazy-but-effective first move

Before deep analysis, just:
```bash
strings -a dump.raw | grep -iE 'flag\{|password|synt\{' | sort -u | less
strings -e l dump.raw | grep -i flag    # UTF-16 (Windows strings)
```
It often finds the flag in seconds. Then use Volatility to understand *context* if the flag is fragmented.

## Workflow

1. `strings | grep flag` (both ASCII and UTF-16) — quick win check.
2. `windows.info` / `linux.*` to confirm OS.
3. `pstree` + `cmdline` — what was running and what was typed.
4. Suspicious process? Dump it and `strings` it.
5. `filescan` → `dumpfiles` for interesting files (e.g. `flag.txt`, `.docx`).
