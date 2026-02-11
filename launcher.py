import multiprocessing
import sys
import os
import traceback

"""
Expressive Video Compressor - Secure Entry Point
This launcher handles Windows-specific process spawning issues 
associated with PyInstaller's --onefile mode and Flet's internal server.
"""

def main():
    # 1. Catch child processes immediately
    # Windows child processes for multiprocessing must be caught by freeze_support
    # before any application logic or heavy modules are imported.
    multiprocessing.freeze_support()

    # 2. PyInstaller --onefile Handling
    # On Windows, a frozen executable must explicitly know its own path 
    # to correctly spawn child processes/workers without re-extracting the bundle.
    if getattr(sys, 'frozen', False):
        try:
            multiprocessing.set_executable(sys.executable)
        except AttributeError:
            pass

    # 3. Environment Sanitization
    # Ensure Flet doesn't get confused by previous state or weird paths
    if "FLET_SERVER_PORT" in os.environ:
        # If we are already in a worker process, just exit or continue as Flet expects
        pass

    try:
        # Import GUI logic only after the environment is secured
        import gui
        
        if "--cli" in sys.argv:
            gui.run_cli()
        else:
            import flet as ft
            
            # Flet 0.80.2 (latest) - Launching the main application loop
            # We specify assets_dir here to ensure proper path resolution in frozen state
            assets_path = os.path.join(os.path.dirname(__file__), "assets")
            if not os.path.exists(assets_path):
                # Fallback for some bundle structures
                assets_path = "assets"
                
            ft.app(
                target=gui.main,
                assets_dir=assets_path
            )
            
    except Exception:
        # If the app crashes on launch, log it for debugging
        # In a --windowed build, this is the only way to see what went wrong
        with open("crash_report.log", "w") as f:
            f.write(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
