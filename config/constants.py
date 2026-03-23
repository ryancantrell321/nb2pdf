"""
NB2PDF - Application constants.
"""

APP_NAME = "Pandora NB2PDF"
APP_VERSION = "2026.03"
APP_AUTHOR = "Pandora Dynamics"

# Placeholder — replace with your actual GitHub repo URL
UPDATE_REPO_URL = "https://github.com/ryancantrell321/Jupyter"

# Settings file name (stored in user config dir)
SETTINGS_FILENAME = "settings.json"

# Log file name
LOG_FILENAME = "nb2pdf.log"

# Conversion methods
METHOD_BROWSER = "browser"
METHOD_LATEX = "latex"

# Supported notebook extension
NOTEBOOK_EXTENSION = ".ipynb"
PDF_EXTENSION = ".pdf"

# Threading timeouts (seconds)
CONVERSION_TIMEOUT = 300  # 5 minutes
SYSTEM_CHECK_TIMEOUT = 60

# UI refresh interval for progress (ms)
UI_POLL_INTERVAL = 100

# Required Python packages for conversion
REQUIRED_PACKAGES = ["nbconvert", "notebook", "jupyter"]

# Browser names to detect
BROWSER_NAMES = ["chrome", "chromium", "msedge", "brave"]

# LaTeX distributions
LATEX_EXECUTABLES = ["pdflatex", "xelatex", "lualatex"]
