"""Cross-platform helpers: font discovery, OS theme detection, folder openers,
and subprocess flags used to suppress console windows on Windows."""

import os
import subprocess
import sys


def get_system_fonts():
    # Common fallback fonts
    fonts = ["System Default", "Roboto Flex"]
    try:
        import platform as _platform
        import subprocess as _subprocess
        sys_type = _platform.system()

        if sys_type == "Linux":
            # Use fc-list on Linux
            res = _subprocess.run(["fc-list", ":lang=en", "family"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    # fc-list output when family is requested is usually "Family Name"
                    # or "Family1,Family2"
                    family = line.strip().split(",")[0]
                    if family and len(family) < 40 and not family.startswith("."):
                        fonts.append(family)
        elif sys_type == "Windows":
            # Registry query for fonts on Windows
            cmd = ["reg", "query", "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts"]
            res = _subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if "(TrueType)" in line or "(OpenType)" in line:
                        family = line.split("  ")[0].strip()
                        # Clean up suffixes
                        for suffix in [" (TrueType)", " (OpenType)", " & ", " Regular"]:
                            if suffix in family: family = family.split(suffix)[0]
                        if family and len(family) < 40:
                            fonts.append(family)
    except: pass

    # Deduplicate
    seen = set()
    unique_fonts = [x for x in fonts if not (x in seen or seen.add(x))]

    # Sort the list after the first two items (System Default, Roboto Flex)
    # and filter out some technical fonts (starting with dot or having many non-alphanumeric chars)
    header = unique_fonts[:2]
    body = [f for f in unique_fonts[2:] if not f.startswith(".") and "." not in f]

    return header + sorted(body)


def is_system_dark_mode():
    try:
        import platform
        system = platform.system()
        if system == "Windows":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return value == 0
            except: pass
        elif system == "Linux":
            # 1. Check XDG Portal (Fastest & Modern Standard)
            try:
                res = subprocess.run([
                    "dbus-send", "--print-reply", "--dest=org.freedesktop.portal.Desktop",
                    "/org/freedesktop/portal/desktop", "org.freedesktop.portal.Settings.Read",
                    "string:org.freedesktop.appearance", "string:color-scheme"
                ], capture_output=True, text=True, timeout=0.5)
                if res.returncode == 0:
                    if "uint32 1" in res.stdout: return True
                    if "uint32 2" in res.stdout: return False
            except: pass

            # 2. Check environment variable (Instant)
            gtk_env = os.environ.get('GTK_THEME', '').lower()
            if 'dark' in gtk_env: return True
            if 'light' in gtk_env: return False

            # 3. Check GNOME/GTK via gsettings
            try:
                res = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"], capture_output=True, text=True, timeout=0.5)
                if 'prefer-dark' in res.stdout: return True
                if 'prefer-light' in res.stdout: return False

                res = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"], capture_output=True, text=True, timeout=0.5)
                if 'dark' in res.stdout.lower(): return True
                if 'light' in res.stdout.lower(): return False
            except: pass

            # 4. Check KDE/Plasma
            try:
                res = subprocess.run(["kreadconfig5", "--group", "General", "--key", "ColorScheme"], capture_output=True, text=True, timeout=0.5)
                if 'dark' in res.stdout.lower(): return True
                if 'light' in res.stdout.lower(): return False
            except: pass
    except: pass
    return True # Default to dark if detection fails or is uncertain


def open_folder(path):
    try:
        if not path: return
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        if not os.path.exists(folder): return
        if os.name == 'nt': os.startfile(folder)
        elif sys.platform == 'darwin': subprocess.Popen(['open', folder])
        else: subprocess.Popen(['xdg-open', folder])
    except: pass


# Logic to prevent console windows from popping up on Windows
SUBPROCESS_FLAGS = 0
if os.name == 'nt':
    SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW

# Define for cross-platform safety (only used on Windows)
CREATE_NEW_CONSOLE = 16