import multiprocessing
import sys
import os

def start_app():
    """
    Official Entry Point for Video Utilities.
    Using delayed imports ensures that child processes (worker threads/pids)
    do not accidentally re-initialize the entire GUI, preventing fork bombs.
    """
    # CRITICAL: Required for PyInstaller/bundled apps using multiprocessing
    multiprocessing.freeze_support()

    # Delayed imports to avoid import-time side effects in sub-processes
    import flet as ft
    import gui

    if "--cli" in sys.argv:
        gui.run_cli()
    else:
        # Modern Flet Launch
        assets_path = os.path.join(os.path.dirname(__file__), "assets")
        if not os.path.exists(assets_path):
            assets_path = "assets" # Fallback
            
        # Official Flet Launch
        ft.run(
            gui.main,
            assets_dir=assets_path
        )



if __name__ == "__main__":
    start_app()
