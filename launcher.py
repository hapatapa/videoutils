import multiprocessing
import sys
import os

# LAYER 1: Immediate Catch
# This must happen before any other code runs.
if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # LAYER 2: Path Binding
    # Forces child processes to use the bundled executable as the runner.
    if getattr(sys, 'frozen', False):
        multiprocessing.set_executable(sys.executable)
        
    # Catch weird sub-process flags that occasionally bypass freeze_support
    if len(sys.argv) > 1 and ("--multiprocessing-fork" in sys.argv[1] or "--uvicorn-worker" in sys.argv[1]):
        sys.exit(0)

    # LAYER 3: Isolated Import
    # We only import the GUI once we know we are in the 'main' process.
    import gui
    if "--cli" in sys.argv:
        gui.run_cli()
    else:
        import flet as ft
        # Use the explicit app launcher
        ft.app(target=gui.main)
