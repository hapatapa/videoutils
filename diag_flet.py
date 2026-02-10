import flet as ft
import flet_video as ftv
print(f"Flet version: {ft.version.version}")
print(f"flet_video attributes: {dir(ftv)}")
try:
    from flet import Video
    print("Video found in flet")
except ImportError:
    print("Video NOT found in flet")

try:
    from flet_video import Video
    print("Video found in flet_video")
except ImportError:
    print("Video NOT found in flet_video")
