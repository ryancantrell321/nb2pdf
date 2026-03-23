import sys, os

# Ensure the app root is in the path when run as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from integrations.instance_lock import InstanceLocker
from utils.logger import setup_logger
from config.settings import Settings
from ui.app_window import AppWindow


def main() -> None:
    """Application entry point."""
    # Set up logging before anything else
    logger = setup_logger()
    logger.info("NB2PDF starting up")

    # Enforce single instance
    locker = InstanceLocker()
    if not locker.acquire():
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "Already Running",
            "NB2PDF is already running.\n\nPlease check your taskbar or system tray."
        )
        root.destroy()
        logger.warning("Another instance is already running. Exiting.")
        sys.exit(0)

    try:
        settings = Settings.load()
        app = AppWindow(settings)
        app.run()
    except Exception as e:
        logger.critical(f"Fatal error during startup: {e}", exc_info=True)
        raise
    finally:
        locker.release()
        logger.info("NB2PDF shut down cleanly")


if __name__ == "__main__":
    main()
