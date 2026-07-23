# Toolkit — Forensics tools & how to install them

You already have a **Kali WSL2** setup (see the CTF Toolchain memory). Kali ships most of these. Do your forensics work in WSL/Kali, not raw Windows PowerShell — the Unix tooling is far better. A few Windows-native GUIs are worth having too.

## Install everything on Kali/Debian WSL

```bash
sudo apt update && sudo apt install -y \
  file binutils xxd bsdmainutils \    # file, strings, xxd, hexdump
  binwalk foremost scalpel \          # carving / embedded-file extraction
  steghide zsteg outguess pngcheck \  # steganography
  exiftool \                          # metadata
  sleuthkit testdisk \                # disk/partition forensics (mmls, fls, icat, photorec)
  wireshark tshark tcpdump \          # network / pcap
  qpdf poppler-utils \                # pdf tools
  john hashcat                        # cracking (zip/pdf passwords)
```

Some tools are gems/python and install separately:

```bash
sudo gem install zsteg            # PNG/BMP LSB stego scanner
pipx install volatility3          # memory forensics (or: pip install volatility3)
```

## What each tool is for

### Identify & inspect (use these first, every time)
| Tool | Use |
|---|---|
| `file` | Identify type by magic bytes |
| `strings` | Pull printable text out of a binary (`-n` min length, `-e l` for UTF-16) |
| `xxd` / `hexdump -C` | Raw hex view; also `xxd -r` to convert hex back to binary |
| **ImHex** / **HxD** (Windows GUI) | Comfortable hex editor for staring at structure |

### Carving / embedded files
| Tool | Use |
|---|---|
| `binwalk` | Find (and `-e` extract) files embedded inside other files |
| `foremost` / `scalpel` | Signature-based file carving from disk images |
| `photorec` (testdisk) | Recover deleted files from images — very powerful |

### Steganography → [[steganography.ai]]
| Tool | Use |
|---|---|
| `zsteg` | LSB stego in PNG/BMP (best first try for PNGs) |
| `steghide` | Hide/extract in JPG/BMP/WAV (often password-protected) |
| `stegsolve` (Java) | Visual bit-plane / channel browser for images |
| `exiftool` | Metadata, often where lazy flags live |
| `pngcheck` | Validate PNG structure, find appended chunks |
| **Sonic Visualiser / Audacity** | Spectrogram stego in audio |

### Disk / filesystem → [[disk-forensics.ai]]
| Tool | Use |
|---|---|
| `mmls` (sleuthkit) | Show partition table of a disk image |
| `fls` / `icat` | List files / extract by inode from a filesystem image |
| `testdisk` | Repair partition tables, recover partitions |
| `dd` | Slice out a partition by offset |
| mount (`-o loop`) | Mount a filesystem image (needs Linux; WSL2 works) |

### Memory → [[memory-forensics.ai]]
| Tool | Use |
|---|---|
| `volatility3` | The tool for RAM dumps — process lists, files, dumps |

### Network → [[network-pcap.ai]]
| Tool | Use |
|---|---|
| **Wireshark** (GUI) | Inspect packet captures, Follow TCP Stream, export objects |
| `tshark` | CLI Wireshark, great for scripting/grep |
| `tcpflow` | Reassemble TCP streams to files |

### Encoding / decoding (the universal helper)
- **CyberChef** — https://gchq.github.io/CyberChef/ — run it offline too. The **"Magic"** operation auto-detects base64/hex/ROT/XOR. This alone solves a shocking number of forensics steps.

## The one Windows-specific script you already have

`E:\CTF\scripts\extract_strings.ps1` — a pure-PowerShell `strings` replacement for when you're not in WSL:

```powershell
.\extract_strings.ps1 -Path .\evidence.bin -MinLen 6
```

It's the same idea as `strings -n 6`. See [[file-analysis.ai]] for when you'd reach for it.
