import multiprocessing
import sys

# EXTREMELY IMPORTANT: This must be called before ANY other imports
# that might trigger subprocess spawning (like flet or flet-video).
if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # Check if we are a child process. If so, freeze_support handles it and exits.
    # The following code only runs in the main process.
    
    import gui
    if "--cli" in sys.argv:
        gui.run_cli()
    else:
        import flet as ft
        # Use simple entry point
        ft.app(target=gui.main)
