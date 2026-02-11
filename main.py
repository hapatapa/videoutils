import sys
import os
import flet as ft
import gui

def main():
    """
    Official Entry Point for Expressive Video Compressor.
    The Flet native build system handles process isolation on Windows,
    removing the need for many manual PyInstaller hacks.
    """
    if "--cli" in sys.argv:
        gui.run_cli()
    else:
        # Standard Flet Launch
        ft.app(
            target=gui.main,
            assets_dir=os.path.join(os.path.dirname(__file__), "assets")
        )

if __name__ == "__main__":
    main()
