import flet as ft
import sys

print(f"Python version: {sys.version}")
print(f"Flet version: {getattr(ft, '__version__', 'unknown')}")

import_paths = [
    "from flet import Video",
    "from flet.video import Video",
    "from flet_video import Video",
    "from flet_video.video import Video",
    "import flet_video; fv = flet_video.Video",
]

for path in import_paths:
    try:
        exec(path)
        print(f"SUCCESS: {path}")
    except Exception as e:
        print(f"FAIL: {path} - {e}")

try:
    import flet_video
    print(f"flet_video dir: {dir(flet_video)}")
except Exception as e:
    print(f"flet_video NOT importable: {e}")
