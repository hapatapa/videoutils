"""Persistent settings storage and app runtime paths (config + temp dirs)."""

import json
import os
import tempfile

# --- Settings Management ---
if os.name == 'nt':
    CONFIG_DIR = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'video-utilities')
else:
    CONFIG_DIR = os.path.expanduser('~/.config/video-utilities')

os.makedirs(CONFIG_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'preferences.json')

DEFAULT_SETTINGS = {
    "theme_mode": "dark",
    "accent_color": "INDIGO_ACCENT",
    "auto_open_folder": False,
    "play_ding": True,
    "show_logs": False,
    "use_gpu": True,
    "follow_os_theme": True,
    "comic_sans_unlocked": False,
    "comic_sans_active": False,
    "custom_font_path": "",
    "custom_font_family": ""
}


def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            validated = DEFAULT_SETTINGS.copy()
            for key in DEFAULT_SETTINGS:
                if key in settings and isinstance(settings[key], type(DEFAULT_SETTINGS[key])):
                    validated[key] = settings[key]
            return validated
    except: pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except: pass


def get_app_temp_dir():
    """Return (creating if needed) the per-user cache/temp directory for the app."""
    if os.name == 'nt':
        # Use %LOCALAPPDATA%/Temp if available, otherwise standard temp
        temp_base = os.environ.get('LOCALAPPDATA', '')
        if temp_base:
            temp_dir = os.path.join(temp_base, 'Temp', 'video-utilities')
        else:
            temp_dir = os.path.join(tempfile.gettempdir(), 'video-utilities')
    else:
        # Linux: ~/.cache/video-utilities
        temp_dir = os.path.expanduser('~/.cache/video-utilities')

    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir