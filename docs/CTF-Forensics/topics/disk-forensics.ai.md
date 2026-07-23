# Disk & Filesystem Forensics

You're handed a **disk image** (`.img`, `.dd`, `.raw`, `.E01`) — a byte-for-byte copy of a disk. The flag is a file on it: sometimes hidden in a second partition, sometimes deleted, sometimes in slack space. This is exactly the [[hidden-partition.ai]] challenge, so read this + that writeup together.

## Step 1 — What kind of image is it?

```bash
file disk.img
# "DOS/MBR boot sector; partition 1 ...; partition 2 ..."  → whole disk, multiple partitions
# "Linux rev 1.0 ext4 filesystem data"                     → a single partition already
ls -l disk.img          # size gives a hint (200 MB in the past challenge)
```

## Step 2 — Read the partition table

```bash
mmls disk.img            # sleuthkit — clean partition listing with offsets in SECTORS
fdisk -l disk.img        # alternative
```

Example output structure:
```
      Slot      Start        End          Length       Description
002:  000:000   0000002048   0000204799   0000202752   Win95 FAT32 (0x0c)
003:  000:001   0000204800   0000407551   0000202752   Linux (0x83)      <-- the "hidden" one
```

The **partition type IDs** matter:
- `0x0c` / `0x0b` = FAT32
- `0x07` = NTFS
- `0x83` = Linux (ext2/3/4) ← often where the flag hides
- `0x82` = Linux swap

A second, less-obvious partition (especially a Linux one on an otherwise-Windows disk) is the classic "hidden partition."

## Step 3 — Extract the partition you want

Two ways.

**A) Carve it with `dd`** (offset = start sector × 512):
```bash
# start sector 204800 → byte offset 204800*512
dd if=disk.img of=part2.img bs=512 skip=204800 count=202752
file part2.img          # now identify the filesystem
```

**B) Let sleuthkit read it in place** using the offset (skip the carve):
```bash
fls -o 204800 disk.img          # list files in partition starting at sector 204800
```

## Step 4 — Read the filesystem

**Mount it** (Linux/WSL2 — cleanest if the fs type is supported):
```bash
mkdir mnt
sudo mount -o loop,ro part2.img mnt/    # ro = read-only, never mutate evidence
ls -laR mnt/
```
Then just browse for `secret.txt`, `flag.txt`, hidden dotfiles, and `lost+found/`.

**Or use sleuthkit without mounting** (works even when mount can't, e.g. odd fs):
```bash
fls -r part2.img              # -r = recursive file listing (shows deleted with *)
icat part2.img <inode> > out  # extract a file by inode number
```

## Step 5 — Deleted files & slack space

- Deleted entries show with a `*` in `fls`. Recover with `icat <inode>`.
- Full recovery sweep: `photorec disk.img` (from testdisk) carves everything recoverable.
- `strings disk.img | grep -i flag` still works and sometimes finds it instantly — do this early even on disk images.

## Step 6 — Grep the whole thing

Never underestimate:
```bash
strings -a disk.img | grep -iE 'flag\{|synt\{'   # synt{ = ROT13 of flag{
```

## `lost+found`?

An ext filesystem directory where `fsck` puts orphaned files. If a challenge references it, check `mnt/lost+found/` — recovered flag files sometimes land there.

## Tool cheat sheet

| Task | Command |
|---|---|
| Partition table | `mmls disk.img` |
| Carve partition | `dd if=disk.img of=p.img bs=512 skip=<start> count=<len>` |
| List files (offset) | `fls -o <start> disk.img` |
| Extract by inode | `icat -o <start> disk.img <inode> > out` |
| Mount | `sudo mount -o loop,ro p.img mnt/` |
| Recover deleted | `photorec disk.img` |

→ Full worked example: [[hidden-partition.ai]]
