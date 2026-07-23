# CTF Forensics — Study Folder

> Goal: get ready for an upcoming CTF by learning how to attack **forensics** challenges.
> Everything Claude created here uses the `.ai.md` suffix (per vault `CLAUDE.md`). Files *you* make can be named however you like.

## How to use this folder

1. Read [[01-methodology.ai]] first — it's the "what do I even do when I get a file" workflow.
2. Skim [[00-toolkit.ai]] and install what you're missing (mostly lives in your Kali WSL).
3. Work through the **topics/** notes — each is a mini-lesson with commands you can copy.
4. Do the **examples/** — generate practice files with the script, then solve them without looking.
5. Read the **writeups/** — full solved walkthroughs. Start with [[hidden-partition.ai]] (a real past challenge).

## Map

| Folder | What's in it |
|---|---|
| `01-methodology.ai.md` | The general triage workflow + a decision checklist |
| `00-toolkit.ai.md` | Tool list, what each does, install commands |
| `topics/` | One note per forensics sub-skill (files, stego, disk, memory, pcap, metadata) |
| `writeups/` | Full solved challenges, step by step |
| `examples/` | Practice files + a generator script so you can make your own |

## The forensics sub-categories you'll see in CTFs

- **File analysis / carving** — wrong extensions, appended data, embedded files → [[file-analysis.ai]]
- **Steganography** — data hidden in images/audio → [[steganography.ai]]
- **Disk / filesystem forensics** — disk images, partitions, deleted files → [[disk-forensics.ai]]
- **Memory forensics** — RAM dumps, Volatility → [[memory-forensics.ai]]
- **Network / packet analysis** — pcap files, Wireshark → [[network-pcap.ai]]
- **Metadata / OSINT-ish** — EXIF, document properties → [[metadata.ai]]

## Golden rules

1. **`file` and `strings` first, always.** More CTF forensics flags fall to these two than to any fancy tool.
2. **Look at the bytes.** A hex viewer (`xxd`, `hexdump`, ImHex) tells you what something *really* is, ignoring the extension.
3. **The flag has a format.** Usually `flag{...}` or the event's prefix. `grep -ri 'flag{'` early and often.
4. **Encodings hide in plain sight.** ROT13, base64, hex. The past challenge's flag was literally ROT13 — see [[hidden-partition.ai]].
5. **Work on a copy.** Never modify the original evidence file.
