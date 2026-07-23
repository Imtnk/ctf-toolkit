# Steganography

Data hidden *inside* media (images, audio) so the file looks normal. Extremely common in forensics/misc CTF categories. Work through this order.

## Images — the standard sweep

Run all of these; one usually pops:

```bash
file img.png                 # confirm real type
exiftool img.png             # metadata — flags love the Comment/Artist fields
strings -n 6 img.png | grep -i flag
binwalk img.png              # appended/embedded files
pngcheck -v img.png          # broken/extra PNG chunks (hidden data lives here)
zsteg img.png                # LSB stego (PNG/BMP) — try this early for PNGs
zsteg -a img.png             # all methods, all bit-planes
```

For JPEGs specifically:
```bash
steghide info img.jpg        # is there an embedded payload?
steghide extract -sf img.jpg # extract (will prompt for passphrase — try empty, then common words)
```

`steghide` passphrases are often the challenge's theme word, "password", or empty. Brute force:
```bash
stegseek img.jpg /usr/share/wordlists/rockyou.txt   # fast steghide cracker
```

## Visual / bit-plane analysis

- **stegsolve.jar** — step through red/green/blue bit planes; hidden text/QR often appears in one plane. Also does XOR of channels and "Data Extract".
- Look at the image at extreme zoom / brightness — sometimes it's just faint text.

## LSB (Least Significant Bit)

Payload encoded in the lowest bit of each pixel byte — invisible to the eye. `zsteg` (PNG/BMP) automates detection. For custom LSB, write a few lines of Python with PIL to pull bit 0 of each channel and reassemble bytes.

## Audio stego

| Technique | How to find it |
|---|---|
| **Spectrogram text** | Open in **Audacity** or **Sonic Visualiser**, view Spectrogram — the flag is drawn in the frequencies |
| **LSB in WAV** | `steghide` (WAV supported), or custom Python |
| **DTMF / Morse** | Listen; decode tones. Morse via audio → text |
| Metadata | `exiftool audio.wav` |

## Quick decision guide

- PNG/BMP → `zsteg -a` first, then `binwalk`, then stegsolve.
- JPG → `steghide`/`stegseek` first, then `binwalk`, `exiftool`.
- WAV/MP3 → spectrogram in Audacity first.
- Any image with weird size/colors → stegsolve bit planes.

## Don't forget metadata

Half of "stego" easy challenges are just a flag sitting in EXIF. Always `exiftool`. → [[metadata.ai]]
