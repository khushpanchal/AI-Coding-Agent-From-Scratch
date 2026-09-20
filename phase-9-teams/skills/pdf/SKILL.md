---
name: pdf
description: Read, create, merge, and manipulate PDF files.
---

# PDF Skill

## Reading PDFs

Preferred tools (try in order):
1. `pdftotext` (poppler-utils) — best for text extraction
   ```bash
   pdftotext input.pdf -        # to stdout
   pdftotext -layout input.pdf - # preserve layout
   ```
2. `python -c "import fitz; ..."` (PyMuPDF) — for programmatic access
3. `strings input.pdf | head -200` — last resort for corrupted files

## Creating PDFs

1. **From Markdown** (recommended):
   ```bash
   pandoc input.md -o output.pdf
   ```

2. **From Python** (ReportLab):
   ```python
   from reportlab.lib.pagesizes import letter
   from reportlab.pdfgen import canvas
   c = canvas.Canvas("output.pdf", pagesize=letter)
   c.drawString(72, 720, "Hello, World!")
   c.save()
   ```

## Merging / Splitting

```bash
# Merge
pdftk file1.pdf file2.pdf cat output merged.pdf

# Extract pages 1-5
pdftk input.pdf cat 1-5 output pages1to5.pdf

# With PyMuPDF
python -c "
import fitz
doc = fitz.open('input.pdf')
doc.select([0, 1, 2])  # keep first 3 pages
doc.save('output.pdf')
"
```

## Tips

- Always check if tools are installed before using them (`which pdftotext`)
- For scanned PDFs, you need OCR (`tesseract`)
- Large PDFs: process page-by-page to avoid memory issues
