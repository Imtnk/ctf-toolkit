# Methodology — What to do when you get a forensics file

The single most important skill in forensics CTF isn't knowing tools — it's having a **reflex order** so you never freeze staring at a file. Follow this every time.

## Step 0 — Set up

```bash
mkdir chall && cd chall
cp /path/to/original ./work.bin   # ALWAYS work on a copy
```

Note the filename, the challenge description, and the point value. The description is a hint — "we intercepted this transmission" screams pcap; "the image looks normal" screams stego.

## Step 1 — Identify what it actually is

```bash
file work.bin          # magic-byte based type — ignores the extension
xxd work.bin | head     # look at the first bytes (the "magic")
ls -l work.bin          # size — huge? probably a disk/memory image
```

Extensions lie. `file` reads the *magic bytes* at the start. Learn the common ones — see [[file-analysis.ai]].

## Step 2 — The two-command reflex

```bash
strings -n 6 work.bin | less           # printable text inside the binary
strings -n 6 work.bin | grep -i flag   # go straight for the flag format
```

Also try wider-charset strings (flags are sometimes UTF-16 in Windows artifacts):

```bash
strings -e l work.bin | grep -i flag   # little-endian 16-bit
```

## Step 3 — Look for hidden / appended / embedded data

```bash
binwalk work.bin           # scans for embedded file signatures
binwalk -e work.bin        # ...and extracts them (careful, can be noisy)
foremost -i work.bin -o out/   # file carving by signature
```

A classic trick: a valid PNG with a ZIP glued on the end. `binwalk` finds it; `unzip work.bin` sometimes just works.

## Step 4 — Branch by type

Now you know what it is, jump to the right note:

| `file` says... | Go to |
|---|---|
| PNG / JPEG / BMP / GIF | [[steganography.ai]] + [[metadata.ai]] |
| DOS/MBR boot sector, partition, filesystem | [[disk-forensics.ai]] |
| ELF core dump / "data" + several GB | [[memory-forensics.ai]] |
| pcap / pcapng / tcpdump capture | [[network-pcap.ai]] |
| Zip / gzip / tar | extract, then re-run Step 1 on the contents |
| ASCII text / "data" | it's probably an **encoding** — see Step 5 |

## Step 5 — Decode encodings

If you find a blob of text that looks scrambled, run it through decoders:

- **ROT13** — letters shifted 13. `tr 'A-Za-z' 'N-ZA-Mn-za-m'`
- **Base64** — ends in `=`, alphabet `A-Za-z0-9+/`. `base64 -d`
- **Hex** — only `0-9a-f`. `xxd -r -p`
- **Everything at once** — paste into **CyberChef** ("Magic" recipe auto-detects).

> The real past challenge's flag was `synt{...}` — pure ROT13 for `flag{...}`. Don't overthink it. See [[hidden-partition.ai]].

## Step 6 — Iterate

Forensics is recursive: you carve a zip out of an image, inside is a disk image, inside that is a deleted file, inside that is base64. Keep re-applying Steps 1–5 to whatever you extract until you hit `flag{...}`.

## Quick checklist (print this in your head)

- [ ] Made a copy?
- [ ] Ran `file`?
- [ ] Ran `strings | grep -i flag`?
- [ ] Looked at the hex header?
- [ ] Ran `binwalk`?
- [ ] Checked metadata (`exiftool`)?
- [ ] Tried CyberChef Magic on any odd text?
- [ ] Re-ran all of the above on anything I extracted?
