# Metadata

The easiest points in any forensics category. Flags hide in the *properties* of a file — where nobody looks because it's too obvious. Always check.

## exiftool — the universal metadata reader

```bash
exiftool file.jpg          # dumps every metadata field
exiftool -a -u -g1 file.jpg   # all tags, including unknown/duplicated, grouped
```

Flags commonly sit in:
- **Comment**, **UserComment**, **ImageDescription**
- **Artist**, **Author**, **Copyright**, **Creator**
- **GPS** coordinates (→ OSINT: plug into a map)
- **Software** / **XPKeywords** (Windows)
- Custom / XMP fields

Works on images, PDFs, Office docs, audio, video, and more.

## Documents

**PDF:**
```bash
exiftool doc.pdf
pdfinfo doc.pdf            # poppler — title/author/producer/dates
strings doc.pdf | grep -i flag
qpdf --qdf --object-streams=disable doc.pdf out.pdf   # decompress streams to read raw
pdfimages -all doc.pdf img/    # extract embedded images
pdfdetach -list doc.pdf        # attached files hidden in the PDF
```

**Office (.docx/.xlsx/.pptx) are ZIPs:**
```bash
unzip doc.docx -d doc/
# then read doc/docProps/core.xml (author, title) and doc/word/document.xml
grep -ri flag doc/
```
Check `docProps/core.xml` and `docProps/app.xml` for author/company, and hunt for hidden text, tracked changes, or embedded objects in `word/embeddings/`.

## Images — beyond EXIF

- **Thumbnails** can differ from the main image (someone cropped a flag out, but the embedded thumbnail still shows it): `exiftool -b -ThumbnailImage img.jpg > thumb.jpg`
- **GPS** → maps to a location for OSINT sub-tasks.

## Filesystem timestamps

On disk-image challenges, MAC times (Modified/Accessed/Created) can hint which file matters or reveal ordering. `fls -l` / `istat` (sleuthkit) show them.

## Rule of thumb

If a challenge hands you a single innocent-looking photo or document, run `exiftool` **before** anything fancy. It's a 2-second check that wins a lot of easy flags. → [[steganography.ai]] for when metadata comes up empty.
