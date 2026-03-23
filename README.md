# NB2PDF — Jupyter Notebook to PDF Converter

A production-quality desktop application for converting `.ipynb` Jupyter Notebook
files to PDF, built with Python and Tkinter.

---

## Features

| Feature | Details |
|---------|---------|
| **Browser conversion** | Uses headless Chrome / Edge / Brave to render HTML → PDF |
| **LaTeX conversion** | Uses nbconvert + MiKTeX / TeX Live for high-fidelity PDFs |
| **Drag & drop** | Drop `.ipynb` files directly onto the app window |
| **System diagnostics** | Live dependency dashboard with one-click fixes |
| **Live log console** | Color-coded real-time conversion output |
| **Auto-updater** | Checks GitHub releases; downloads & applies updates safely |
| **Single instance lock** | Prevents duplicate instances via portalocker |
| **Temp file cleaner** | Cleans intermediate conversion artefacts |
| **No-console subprocesses** | All child processes run silently with `CREATE_NO_WINDOW` |
| **Window icon** | App icon applied to main window and all dialogs |

---

## Project Structure

```
nb2pdf/
├── main.py                     Entry point
├── nb2pdf_launcher.vbs         Windows launcher (activates venv, no console)
├── requirements.txt
│
├── config/
│   ├── constants.py            App-wide constants
│   └── settings.py             JSON-persisted settings
│
├── core/
│   ├── base_converter.py       Abstract converter interface
│   ├── browser_converter.py    Browser (HTML → PDF) pipeline
│   ├── latex_converter.py      LaTeX pipeline
│   └── converter_factory.py    Factory for converter selection
│
├── services/
│   ├── system_checker.py       Dependency detection & pip install
│   └── updater.py              GitHub release checker & updater
│
├── integrations/
│   ├── instance_lock.py        Single-instance portalocker lock
│   └── memory_cleaner.py       Temp file & GC cleanup
│
├── utils/
│   ├── logger.py               Centralized logging (file + GUI queue)
│   ├── paths.py                Path helpers
│   └── file_utils.py           Validation, file ops, subprocess flags, window icon
│
├── ui/
│   ├── app_window.py           Main window (MVC controller)
│   ├── theme.py                Dark / light theme definitions
│   ├── widgets.py              Reusable styled widget library
│   ├── drop_zone.py            Drag-and-drop file input
│   ├── status_panel.py         Dependency status dashboard
│   ├── log_console.py          Live log output widget
│   ├── settings_dialog.py      Settings modal dialog
│   ├── update_dialog.py        Update check / download dialog
│   └── system_check_dialog.py  Dependency status dialog
│
└── assets/                     Icons, images
```

---

## Installation

### 1. Prerequisites

- Python 3.11 or newer — [download](https://www.python.org/downloads/)
- One of: Google Chrome, Microsoft Edge, or Brave Browser  
  **OR**  
  MiKTeX (Windows) or TeX Live (macOS/Linux)

### 2. Create and populate the virtual environment

```bash
cd nb2pdf
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

### 3. Run the application

Double-click `nb2pdf_launcher.vbs` — it activates the bundled `venv` and launches `main.py` silently (no console window, no system Python required after setup).

Alternatively, from a terminal:

```bash
venv\Scripts\python main.py
```

---

## Configuration

Settings are stored in:

| OS      | Path |
|---------|------|
| Windows | `%APPDATA%\NB2PDF\settings.json` |

Logs are stored in:

| OS      | Path |
|---------|------|
| Windows | `%APPDATA%\NB2PDF\logs\nb2pdf.log` |
---


## Conversion Methods

### Method A — Browser (recommended)

**Pipeline:** `.ipynb` → HTML (nbconvert) → PDF (headless Chrome/Edge/Brave)

**Pros:** Renders exactly like Jupyter; supports interactive outputs.  
**Cons:** Requires a Chromium-based browser.

### Method B — LaTeX

**Pipeline:** `.ipynb` → LaTeX (nbconvert) → PDF (pdflatex / xelatex)

**Pros:** Publication-quality typesetting; no browser required.  
**Cons:** Requires a full LaTeX distribution; some notebooks may need tweaking.

---


## License

Apache 2.0 — see `LICENSE` for details.
