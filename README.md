# nb → pdf  |  Notebook Converter

Convert Jupyter notebooks (`.ipynb`) to PDF — no Python, no terminal, no browser extensions.

---

## Download & Run

1. Download `NotebookToPDF.exe`
2. Double-click to launch — no installation needed

> Windows may show a SmartScreen warning on first run. Click **More info → Run anyway**.

---

## Requirements

You need at least one of the following to convert notebooks:

### Option A — Browser (recommended, easiest)
Any one of these browsers already installed on your PC:
- Google Chrome
- Microsoft Edge *(pre-installed on Windows 10/11)*
- Brave

### Option B — LaTeX (highest quality)
- [MiKTeX](https://miktex.org/download) — recommended for Windows
- or [TeX Live](https://tug.org/texlive/)

> Not sure which you have? Click **System Check** inside the app to find out.

---

## How to Use

1. **Add notebooks** — click **Add Files** to pick `.ipynb` files, or **Add Folder** to scan a folder, or drag-and-drop files directly onto the window
2. **Choose a method** — select **Browser** or **LaTeX** from the left sidebar
3. **Set output folder** — defaults to your `Downloads` folder; click **Change Folder** to pick another
4. **Click Convert All →**
5. PDFs appear in your chosen output folder — click **Open Folder ↗** to go there directly

---

## File Status

Each notebook shows a live status badge:

| Badge | Meaning |
|---|---|
| QUEUED | Waiting to be converted |
| CONVERTING | In progress |
| DONE | PDF saved successfully |
| FAILED | Conversion error — check the log below |

---

## Troubleshooting

**App won't open / closes immediately**
- Make sure you're on Windows 10 or Windows 11

**FAILED status on all files**
- Click **System Check** — if Browser and LaTeX both show "not found", install Chrome, Edge, or Brave

**PDF is blank or missing content**
- Try switching to the **LaTeX** method for better output quality

**SmartScreen blocks the exe**
- Click **More info → Run anyway** — the app is unsigned but safe

**App is already running message**
- Check your taskbar; only one instance is allowed at a time

---

## Output

PDFs are saved to the selected output folder with the same filename as the notebook.

Example: `my_analysis.ipynb` → `my_analysis.pdf`

---

## License

Licensed under the [Apache License 2.0](LICENSE.md).
Copyright (c) 2026 Nadeesha
