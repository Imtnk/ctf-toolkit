# Writeup — "hidden_partition" (Senior)

> **Category:** Forensics (disk / filesystem)
> **Source file:** `E:\CTF\Senior-hidden_partition.zip`
> **Solved artifacts:** `E:\CTF\Senior-hidden_partition\` (extracted)
> **Flag:** `flag{you_found_hidden_partition}`
> **Skills used:** [[disk-forensics.ai]], [[01-methodology.ai]], encoding (ROT13)

This is a real past challenge from the Senior set, already solved. Here's the full reasoning from zero, the way you'd want to reproduce it live.

---

## 1. What you're given

Unzip `Senior-hidden_partition.zip` → a ~200 MB file `hidden_partition.img`.
(The zip also contains a `__MACOSX/` folder — that's just macOS packaging junk from whoever zipped it, safe to ignore.)

```bash
mkdir hp && cd hp
cp /e/CTF/Senior-hidden_partition/hidden_partition.img ./work.img   # work on a copy
ls -l work.img        # ~209 MB → this is a disk image, not a document
```

Big file + name says "partition" → **disk forensics**. Straight to [[disk-forensics.ai]].

## 2. Identify the image

```bash
file work.img
```
Output:
```
DOS/MBR boot sector;
  partition 1 : ID=0xc, start-CHS ..., startsector 2048,   202752 sectors;
  partition 2 : ID=0x83, start-CHS ..., startsector 204800, 202752 sectors
```

Read this carefully — it's the whole solution in one line:

- It's a **whole-disk image** with an MBR and **two partitions**.
- **Partition 1: ID `0x0c`** = FAT32 (LBA). A normal, visible Windows-ish partition.
- **Partition 2: ID `0x83`** = **Linux** (ext2/3/4), starting at sector **204800**.

That second Linux partition on an otherwise-FAT disk is the **"hidden partition"** the title is talking about. That's our target.

> If you had `mmls` (sleuthkit) installed you'd get the same table more cleanly:
> `mmls work.img` → lists both slots with start sectors 2048 and 204800.

## 3. Extract the hidden (Linux) partition

Byte offset = start sector × 512 = `204800 × 512`. Carve it out with `dd`:

```bash
dd if=work.img of=part2.img bs=512 skip=204800 count=202752
file part2.img          # -> Linux rev 1.0 ext... filesystem data
```

This is exactly what the solved folder shows: the challenge was decomposed into
`0.fat` (partition 1, FAT32, ~104 MB) and `1.img` (partition 2, the ext filesystem, ~104 MB).
`1.img` is our `part2.img`.

## 4. Read the ext filesystem

Mount it read-only (WSL2/Kali), or use sleuthkit if mounting isn't available.

**Mount route:**
```bash
mkdir mnt
sudo mount -o loop,ro part2.img mnt/
ls -laR mnt/
```
You'll find:
```
mnt/lost+found/
mnt/secret.txt
```

**Sleuthkit route (no mount needed):**
```bash
fls part2.img               # lists secret.txt + lost+found
icat part2.img <inode> > secret.txt   # extract by the inode fls shows
```

The interesting file is **`secret.txt`** (the `lost+found` dir is standard ext housekeeping — empty here).

## 5. Read the secret

```bash
cat mnt/secret.txt
```
```
synt{lbh_sbhaq_uvqqra_cnegvgvba}
```

That's **not** the flag yet — but notice it *looks like* a flag with the wrong letters: `synt{...}`. When a "flag" is one substitution away from readable, suspect **ROT13** (`f→s`, `l→y`, `a→n`, `g→t` … i.e. `flag → synt`).

Decode it:
```bash
echo 'synt{lbh_sbhaq_uvqqra_cnegvgvba}' | tr 'A-Za-z' 'N-ZA-Mn-za-m'
```
```
flag{you_found_hidden_partition}
```

(Or paste into **CyberChef** and hit "Magic" / "ROT13" — same result.)

## 6. Flag

```
flag{you_found_hidden_partition}
```

---

## Why this was the intended path

| Clue | What it told you |
|---|---|
| Title "hidden_partition" | Look at the partition table, expect a non-obvious one |
| `file` shows 2 partitions, one `0x83` Linux | The Linux partition is the "hidden" one |
| `secret.txt` reads `synt{...}` | Classic ROT13; `synt` is `flag` shifted 13 |

## Lessons / reusable reflexes

1. **`file` on a disk image gives you the partition map for free** — read it before reaching for heavier tools.
2. **Partition type IDs are signposts:** `0x0c` FAT32, `0x83` Linux, `0x07` NTFS. An out-of-place type = the hidden thing.
3. **`dd skip=<startsector> bs=512`** is the universal "cut this partition out" move.
4. **Mount read-only** (`-o loop,ro`) so you never mutate evidence; or use `fls`/`icat` when you can't mount.
5. **`synt{` == `flag{` in ROT13.** Memorize it — add `synt\{` to your `grep -iE 'flag\{|synt\{'` sweeps ([[disk-forensics.ai]], [[memory-forensics.ai]]).

## Try it yourself, faster

Now redo it targeting under 3 minutes:
```bash
file work.img                                   # note start sector of the 0x83 partition
dd if=work.img of=p.img bs=512 skip=204800 count=202752
sudo mount -o loop,ro p.img mnt && cat mnt/secret.txt | tr 'A-Za-z' 'N-ZA-Mn-za-m'
```
