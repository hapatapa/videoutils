import sys
import os
import threading
import time
import base64
import subprocess
import tempfile
import asyncio
import atexit
import signal
import flet as ft
from flet_video import Video, VideoMedia, PlaylistMode
import shutil
import compressor_logic as logic
import json
from playsound import playsound

APP_VERSION = "Dev Build"

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
    "play_ding": True
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

async def main(page: ft.Page):
    # Set assets_dir to the assets folder directly
    # Set assets_dir to the assets folder directly
    page.assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    
    # --- Temp/Cache Directory Setup ---
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
    
    # Load settings
    user_settings = load_settings()
    
    # Trace log setup
    log_path = os.path.join(temp_dir, "trace.log")
    try:
        with open(log_path, "w") as f: f.write("Main started\n"); f.flush()
    except Exception as e:
        print(f"Failed to write log: {e}")

    current_tab = ""
    page.title = "Video Utilities"
    
    # Set Theme Mode
    page.theme_mode = ft.ThemeMode.DARK if user_settings.get("theme_mode") == "dark" else ft.ThemeMode.LIGHT
    
    page.fonts = {
        "Roboto Flex": "https://raw.githubusercontent.com/google/fonts/main/ofl/robotoflex/RobotoFlex%5BGRAD%2COops%2CYOPQ%2CYTLC%2CYTAS%2CYTDE%2CYTFI%2CYTUC%2Copsz%2Cslnt%2Cwdth%2Cwght%5D.ttf"
    }
    
    # Set Accent Color
    accent_name = user_settings.get("accent_color", "INDIGO_ACCENT")
    page.theme = ft.Theme(
        font_family="Roboto Flex",
        color_scheme_seed=getattr(ft.Colors, accent_name, ft.Colors.INDIGO_ACCENT)
    )
    
    # Audio for Notification
    def play_complete_ding():
        if user_settings.get("play_ding", True):
            sound_path = os.path.join(page.assets_dir, "success.ogg")
            if os.path.exists(sound_path):
                try:
                    # Run in thread to not block UI
                    threading.Thread(target=lambda: playsound(sound_path), daemon=True).start()
                except: pass

    # Window Initialization (Flet 0.80.2 Compatible)
    try:
        # Modern Style (introduced around 0.80.2)
        page.window.title_bar_hidden = True
        page.window.title_bar_buttons_hidden = True
        # On Windows, title_bar_hidden sometimes needs frameless for the custom ones to work
        if sys.platform == "win32":
            page.window.frameless = True
    except:
        # Legacy Style 
        try:
            page.window_title_bar_hidden = True
            page.window_title_bar_buttons_hidden = True
        except: pass

    page.padding = 0
    page.window.min_width = 1143
    page.window.min_height = 841
    page.window.resizable = True
    page.window.icon = "Icon.png"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # --- Cleanup Logic ---
    def cleanup_temp():
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Cleanup error: {e}")

    # Register for script exit (covers Ctrl+C and normal exit)
    atexit.register(cleanup_temp)
    
    def signal_handler(sig, frame):
        cleanup_temp()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def window_minimize(e):
        try:
            res = page.window.minimize()
            # Flet async check
            import inspect
            if inspect.iscoroutine(res): await res
        except: 
            page.window.minimized = True
        page.update()

    async def window_toggle_maximize(e):
        try:
            if hasattr(page, "window") and hasattr(page.window, "maximized"):
                page.window.maximized = not page.window.maximized
            elif hasattr(page, "window_maximized"):
                page.window_maximized = not page.window_maximized
            else:
                res = page.window_maximize()
                import inspect
                if inspect.iscoroutine(res): await res
        except:
            try: page.window_maximize()
            except: pass
        page.update()

    async def window_close(e=None):
        # Manually trigger cleanup before destruction to be safe
        try: cleanup_temp()
        except: pass
        
        # Try different ways to close, awaiting if necessary
        try:
            import inspect
            # Try window.destroy() first
            try:
                res = page.window.destroy()
                if inspect.iscoroutine(res): await res
            except:
                # Fallback to window_destroy()
                res = page.window_destroy()
                if inspect.iscoroutine(res): await res
        except: 
            import os
            # Note: sys is imported at top level
            os._exit(0)



    # --- FFmpeg Installation Logic (Reusable) ---
    def show_ffmpeg_modal():
        # Check if already open
        for control in page.overlay:
            if isinstance(control, ft.AlertDialog) and \
               isinstance(control.title, ft.Text) and \
               control.title.value == "FFmpeg Not Found":
                control.open = True
                page.update()
                return control

        installing = False
        status_msg = ft.Text("This app requires FFmpeg to function.", color=ft.Colors.ON_SURFACE_VARIANT)
        progress_ring = ft.ProgressRing(visible=False, width=16, height=16, stroke_width=2)
        
        async def do_install(e):
            nonlocal installing
            if installing: return
            installing = True
            e.control.disabled = True
            progress_ring.visible = True
            status_msg.value = "Installing FFmpeg, please wait..."
            page.update()
            
            # Run install in thread to keep UI alive
            def run_install():
                success = logic.install_ffmpeg(print)
                return success

            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, run_install)
            
            if success:
                ff_modal.open = False
                page.update()
                
                success_modal = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Installation Complete"),
                    content=ft.Text("FFmpeg has been successfully installed.\n\nPlease restart the application for changes to take effect."),
                    actions=[
                        ft.TextButton("OK, Close App", on_click=window_close),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                page.overlay.append(success_modal)
                success_modal.open = True
                page.update()
            else:
                installing = False
                e.control.disabled = False
                progress_ring.visible = False
                status_msg.value = "Installation failed. Please install FFmpeg manually."
                page.update()

        ff_modal = ft.AlertDialog(
            modal=True,
            title=ft.Text("FFmpeg Not Found"),
            content=ft.Column([
                ft.Text("FFmpeg is missing from your system. It's the engine that powers all video processing in this app."),
                ft.Row([progress_ring, status_msg], spacing=10),
            ], tight=True, spacing=20),
            actions=[
                ft.ElevatedButton("Install FFmpeg Automatically", on_click=do_install, icon=ft.Icons.DOWNLOAD),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(ff_modal)
        ff_modal.open = True
        page.update()
        return ff_modal

    # --- Initial Check ---
    if not logic.is_ffmpeg_installed():
        ff_modal = show_ffmpeg_modal()
        # Wait until it's installed (modal closed)
        # Note: We can't block easily here without blocking the whole UI setup, 
        # so we let the UI load behind it but disabled (modal=True does the trick visually)

    # --- Konami Code Debug Trigger ---
    konami_code = ["Arrow Up", "Arrow Up", "Arrow Down", "Arrow Down", "Arrow Left", "Arrow Right", "Arrow Left", "Arrow Right", "B", "A"]
    key_buffer = []

    def on_keyboard(e: ft.KeyboardEvent):
        nonlocal key_buffer
        key = e.key
        
        # Add to buffer
        key_buffer.append(key)
        
        # Keep buffer size manageable
        if len(key_buffer) > len(konami_code):
            key_buffer.pop(0)
            
        # Check match
        if key_buffer == konami_code:
            print("👾 Konami Code Activated! Opening FFmpeg Installer...")
            show_ffmpeg_modal()
            key_buffer = [] # Reset

    page.on_keyboard_event = on_keyboard

    # State
    input_display_field = ft.Ref[ft.TextField]()
    output_display_field = ft.Ref[ft.TextField]()
    target_size_slider = ft.Ref[ft.Slider]()
    target_size_input = ft.Ref[ft.TextField]()
    codec_dropdown = ft.Ref[ft.Dropdown]()
    container_dropdown = ft.Ref[ft.Dropdown]()
    gpu_switch = ft.Ref[ft.Switch]()
    preview_switch = ft.Ref[ft.Switch]()
    
    preview_container = ft.Ref[ft.Container]()
    preview_image = ft.Ref[ft.Image]()
    placeholder_img_control = ft.Ref[ft.Image]()
    status_overlay = ft.Ref[ft.Container]()
    status_text = ft.Ref[ft.Text]()
    
    # Advanced State Refs
    two_pass_switch = ft.Ref[ft.Switch]()
    ten_bit_switch = ft.Ref[ft.Switch]()
    denoise_switch = ft.Ref[ft.Switch]()
    aq_switch = ft.Ref[ft.Switch]()
    cpu_used_slider = ft.Ref[ft.Slider]()
    
    # Custom progress bar helper
    def update_progress_bar(pct):
        if not progress_fill.current or not page.window.width: return
        
        prev_w = preview_container.current.width if preview_container.current and preview_container.current.width else 0
        
        # Math: Page padding (40) + Log horizontal padding (30)
        available_w = page.window.width - 40
        if prev_w > 0:
            available_w -= (20 + prev_w) # Spacing + Preview
        
        bar_max_w = available_w - 30
        if bar_max_w < 0: bar_max_w = 0
        
        progress_fill.current.width = bar_max_w * pct
        progress_fill.current.update()


    def update_conv_progress_bar(pct):
        if not conv_progress_fill.current or not page.window.width: return
        prev_w = conv_preview_container.current.width if conv_preview_container.current and conv_preview_container.current.width else 0
        available_w = page.window.width - 40
        if prev_w > 0: available_w -= (20 + prev_w)
        bar_max_w = available_w - 30
        if bar_max_w < 0: bar_max_w = 0
        conv_progress_fill.current.width = bar_max_w * pct
        conv_progress_fill.current.update()
            
        bar_max_w = available_w - 30
        if bar_max_w < 0: bar_max_w = 0
        
        conv_progress_fill.current.width = bar_max_w * pct
        conv_progress_fill.current.update()

    def update_merger_progress_bar(pct):
        if not merger_progress_fill.current or not page.window.width: return
        prev_w = 400 # Fixed width for merger preview side
        available_w = page.window.width - 40
        if prev_w > 0: available_w -= (20 + prev_w)
        bar_max_w = available_w - 30
        if bar_max_w < 0: bar_max_w = 0
        merger_progress_fill.current.width = bar_max_w * pct
        merger_progress_fill.current.update()


    keyframe_input = ft.Ref[ft.TextField]()
    
    log_side_container = ft.Ref[ft.Container]()
    res_text = ft.Ref[ft.Text]()
    rem_time_text = ft.Ref[ft.Text]()
    fps_text = ft.Ref[ft.Text]()
    pct_text = ft.Ref[ft.Text]()
    files_processed_text = ft.Ref[ft.Text]()
    error_log_text = ft.Ref[ft.Text]()
    progress_fill = ft.Ref[ft.Container]()
    progress_container = ft.Ref[ft.Container]()
    
    compress_btn = ft.Ref[ft.FilledButton]()
    stop_btn = ft.Ref[ft.OutlinedButton]()
    btn_text = ft.Ref[ft.Text]()
    
    # Merger Refs
    merger_segments_list = ft.Ref[ft.Column]()
    merger_player_container = ft.Ref[ft.Container]()
    merger_placeholder_img = ft.Ref[ft.Image]()
    merger_preview_container = ft.Ref[ft.Container]()
    merger_output_field = ft.Ref[ft.TextField]()
    merger_video_player = ft.Ref()
    merger_status_text = ft.Ref[ft.Text]()
    merger_progress_fill = ft.Ref[ft.Container]()
    merger_progress_container = ft.Ref[ft.Container]()
    merger_stop_btn = ft.Ref[ft.FilledButton]()
    merger_pct_text = ft.Ref[ft.Text]()
    
    merger_progress_wrapper = ft.Ref[ft.Container]()
    
    trim_stop_btn = ft.Ref[ft.FilledButton]()
    trim_stop_event = threading.Event()
    
    selected_file_paths = []  # List of input file paths for batch processing
    target_output_path = None  # Can be a folder (for batch) or file (for single)
    preview_file_path = os.path.join(temp_dir, "preview_frame.jpg")
    stop_event = threading.Event()
    is_compressing = False
    easter_egg_clicks = 0
    obscure_revealed = False
    all_codecs_revealed = False
    
    last_set_by_slider = 0.0
    is_updating_ui = False

    def log(message, replace_last=False):
        # We'll use this for status updates or fallback logging
        print(message)

    def on_progress(data):
        if res_text.current: res_text.current.value = f"{data['res']}p"
        if rem_time_text.current: rem_time_text.current.value = data['rem_time']
        if fps_text.current: fps_text.current.value = f"{data['fps']} fps"
        if pct_text.current: pct_text.current.value = f"{int(data['pct'] * 100)}%"
        
        # Update Custom Progress Bar
        update_progress_bar(data['pct'])
        
        page.update()

    def update_preview_loop():
        # Force cleanup of old preview file
        if os.path.exists(preview_file_path):
            try: os.remove(preview_file_path)
            except: pass
            
        # Small delay to allow ffmpeg to write first frame
        time.sleep(2)  # Increased delay to give ffmpeg more time
        log(f"🔍 Preview loop started. Looking for: {preview_file_path}")
        
        last_modified = 0  # Track when file was last modified
        first_frame_shown = False
        
        while is_compressing:
            if preview_switch.current.value:
                if os.path.exists(preview_file_path):
                    try:
                        # Check if file has been modified since last check
                        current_modified = os.path.getmtime(preview_file_path)
                        
                        if current_modified > last_modified:
                            last_modified = current_modified
                            
                            # Clear file handle quickly
                            with open(preview_file_path, "rb") as f:
                                img_bytes = f.read()
                            
                            if len(img_bytes) > 1000: # Ensure we didn't catch a tiny/partial file
                                encoded = base64.b64encode(img_bytes).decode("utf-8")
                                # Use data URI format with src instead of src_base64
                                preview_image.current.src = f"data:image/jpeg;base64,{encoded}"
                                
                                # Detect image dimensions and update container width
                                try:
                                    from PIL import Image
                                    import io
                                    img = Image.open(io.BytesIO(img_bytes))
                                    img_width = img.width
                                    # Add padding for container (30 total for padding)
                                    preview_container.current.width = img_width + 30
                                except:
                                    pass
                                
                                # Smooth transition from placeholder to frames (only on first NEW frame)
                                if not first_frame_shown:
                                    first_frame_shown = True
                                    preview_image.current.opacity = 1
                                    placeholder_img_control.current.opacity = 0
                                    placeholder_img_control.current.update()
                                    log("✅ Preview image displayed!")
                                
                                preview_image.current.update()
                                preview_container.current.update()
                                page.update()  # Force UI refresh
                            else:
                                log(f"⚠️ Preview file too small: {len(img_bytes)} bytes")
                    except Exception as e:
                        log(f"⚠️ Preview read error: {e}")
                else:
                    # Only log this once per second to avoid spam
                    pass
            time.sleep(1)

    def on_preview_toggle(e):
        if e.control.value:
            # Start with a reasonable default width (will adjust when image loads)
            preview_container.current.width = 480
            preview_container.current.opacity = 1
        else:
            # Collapse back to 0
            preview_container.current.width = 0
            preview_container.current.opacity = 0
        page.update()

    def on_page_resize(e):
        # No longer needed since width is based on image dimensions
        pass

    page.on_resize = on_page_resize

    def file_picker_result(files=None, path=None):
        nonlocal selected_file_paths, target_output_path
        if files:
            selected_file_paths = [f.path for f in files]
            
            # Update input display
            if len(selected_file_paths) == 1:
                input_display_field.current.value = os.path.basename(selected_file_paths[0])
            else:
                input_display_field.current.value = f"{len(selected_file_paths)} files selected"
            input_display_field.current.update()
            
            # Auto-set output based on batch vs single
            if len(selected_file_paths) == 1:
                base, _ = os.path.splitext(selected_file_paths[0])
                ext = container_dropdown.current.value if container_dropdown.current else "mp4"
                if not ext.startswith("."): ext = "." + ext
                target_output_path = f"{base}_compressed{ext}"
                output_display_field.current.value = os.path.basename(target_output_path)
            else:
                # For batch, suggest the parent directory
                target_output_path = os.path.dirname(selected_file_paths[0])
                output_display_field.current.value = "Same folder as input"
            output_display_field.current.update()
            
            # Reset progress bar calculation
            update_progress_bar(0)
            check_can_start()
        elif path:
            # Directory selected - find all video files
            folder_path = path
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv']
            video_files = []
            
            for file in os.listdir(folder_path):
                if any(file.lower().endswith(ext) for ext in video_extensions):
                    video_files.append(os.path.join(folder_path, file))
            
            if video_files:
                selected_file_paths = sorted(video_files)
                input_display_field.current.value = f"{len(selected_file_paths)} files from folder"
                input_display_field.current.update()
                
                target_output_path = folder_path
                output_display_field.current.value = "Same folder as input"
                output_display_field.current.update()
                check_can_start()
            else:
                input_display_field.current.value = "No video files found in folder"
                input_display_field.current.update()

    def output_file_picker_result(path):
        nonlocal target_output_path
        if path:
            target_output_path = path
            output_display_field.current.value = os.path.basename(target_output_path)
            output_display_field.current.update()
            check_can_start()

    def output_folder_picker_result(path):
        nonlocal target_output_path
        if path:
            target_output_path = path
            output_display_field.current.value = os.path.basename(target_output_path)
            output_display_field.current.update()
            check_can_start()

    async def pick_files_click(e):
        file_picker_result(files=await file_picker.pick_files(allow_multiple=True))

    async def pick_folder_click(e):
        file_picker_result(path=await file_picker.get_directory_path())

    async def pick_output_click(e):
        if len(selected_file_paths) > 1:
            output_folder_picker_result(await output_folder_picker.get_directory_path())
        else:
            output_file_picker_result(await output_file_picker.save_file(file_name="compressed.mp4"))

    file_picker = ft.FilePicker()
    output_file_picker = ft.FilePicker()
    output_folder_picker = ft.FilePicker()

    # --- Converter State & Pickers ---
    conv_file_paths = []
    conv_target_path = None
    conv_is_running = False
    
    conv_input_field = ft.Ref[ft.TextField]()
    conv_output_field = ft.Ref[ft.TextField]()
    conv_fmt_dropdown = ft.Ref[ft.Dropdown]()
    conv_vcodec_dropdown = ft.Ref[ft.Dropdown]()
    conv_acodec_dropdown = ft.Ref[ft.Dropdown]()
    conv_status_text = ft.Ref[ft.Text]()
    conv_start_btn = ft.Ref[ft.FilledButton]()
    conv_stop_btn = ft.Ref[ft.OutlinedButton]()
    
    # Converter Progress/Preview Refs
    conv_files_proc_text = ft.Ref[ft.Text]()
    conv_progress_fill = ft.Ref[ft.Container]()
    conv_time_text = ft.Ref[ft.Text]()
    conv_fps_text = ft.Ref[ft.Text]()
    conv_pct_text = ft.Ref[ft.Text]()
    
    conv_preview_img = ft.Ref[ft.Image]()
    conv_status_overlay = ft.Ref[ft.Container]()
    conv_status_text = ft.Ref[ft.Text]()
    conv_preview_container = ft.Ref[ft.Container]()
    conv_placeholder_img = ft.Ref[ft.Image]()
    
    def check_conv_start():
        if conv_start_btn.current:
            can_start = bool(conv_file_paths) and bool(conv_target_path) and not conv_is_running
            conv_start_btn.current.disabled = not can_start
            conv_start_btn.current.update()

    def generate_waveform(input_path):
        try:
            outfile = os.path.join(temp_dir, "waveform_temp.png")
            # Use cyan color matching the theme
            # split_channels=1 looks cool but maybe messy for mono. 
            # simple: colors=cyan
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-filter_complex", "showwavespic=s=640x360:colors=#00BCD4",
                "-frames:v", "1",
                outfile
            ]
            subprocess.run(cmd, capture_output=True, creationflags=SUBPROCESS_FLAGS)
            return outfile
        except: return None

    def generate_thumbnail(input_path):
        try:
            outfile = os.path.join(temp_dir, "thumbnail_temp.jpg")
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-ss", "00:00:01",
                "-vframes", "1",
                outfile
            ]
            subprocess.run(cmd, capture_output=True, creationflags=SUBPROCESS_FLAGS)
            return outfile
        except: return None

    def update_converter_preview():
        if not conv_file_paths: return
        
        # Determine mode based on Output Format
        fmt = conv_fmt_dropdown.current.value if conv_fmt_dropdown.current else "mp4"
        is_audio_output = fmt in ["mp3", "wav", "flac", "aac", "opus", "ogg", "m4a"]
        
        input_path = conv_file_paths[0]
        
        def run_gen():
            if conv_status_text.current:
                conv_status_text.current.value = "Generating Preview..."
                conv_status_overlay.current.opacity = 1
                conv_status_overlay.current.update()
                conv_status_text.current.update()
            
            img_path = None
            if is_audio_output:
                img_path = generate_waveform(input_path)
            else:
                img_path = generate_thumbnail(input_path)
                
            if img_path and os.path.exists(img_path):
                # Update Image
                with open(img_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                
                if conv_preview_img.current:
                    conv_preview_img.current.src_base64 = b64
                    conv_preview_img.current.opacity = 1
                    conv_preview_img.current.update()
                    
                if conv_placeholder_img.current:
                    conv_placeholder_img.current.opacity = 0
                    conv_placeholder_img.current.update()
            
            if conv_status_overlay.current:
                conv_status_overlay.current.opacity = 0
                conv_status_overlay.current.update()
                
        threading.Thread(target=run_gen, daemon=True).start()

    def on_conv_files_picked(files):
        nonlocal conv_file_paths, conv_target_path
        if files:
            conv_file_paths = [f.path for f in files]
            if len(conv_file_paths) == 1:
                conv_input_field.current.value = os.path.basename(conv_file_paths[0])
                base, _ = os.path.splitext(conv_file_paths[0])
                ext = conv_fmt_dropdown.current.value if conv_fmt_dropdown.current else ""
                if ext and not ext.startswith("."): ext = "." + ext
                if not ext: ext = ".mp4"
                conv_target_path = f"{base}_converted{ext}"
                conv_output_field.current.value = os.path.basename(conv_target_path)
                update_converter_preview() # Update Preview!
            else:
                conv_input_field.current.value = f"{len(conv_file_paths)} files selected"
                conv_target_path = os.path.dirname(conv_file_paths[0])
                conv_output_field.current.value = "Same folder as input"
            conv_input_field.current.update()
            conv_output_field.current.update()
            check_conv_start()
            
    def on_conv_folder_picked(path):
        nonlocal conv_file_paths, conv_target_path
        if path:
            folder_path = path
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.mp3', '.wav', '.flac']
            files = []
            try:
                for f in os.listdir(folder_path):
                     if any(f.lower().endswith(ext) for ext in video_extensions):
                         files.append(os.path.join(folder_path, f))
            except: pass
            
            if files:
                conv_file_paths = sorted(files)
                conv_input_field.current.value = f"{len(conv_file_paths)} files from folder"
                conv_target_path = folder_path
                conv_output_field.current.value = "Same folder as input"
                conv_input_field.current.update()
                conv_output_field.current.update()
                check_conv_start()
                if conv_file_paths: update_converter_preview() # Update Preview for first file

    def on_conv_save_picked(path):
        nonlocal conv_target_path
        if path:
            conv_target_path = path
            conv_output_field.current.value = os.path.basename(conv_target_path)
            conv_output_field.current.update()
            check_conv_start()
            
    def on_conv_out_folder_picked(path):
        nonlocal conv_target_path
        if path:
            conv_target_path = path
            conv_output_field.current.value = os.path.basename(conv_target_path)
            conv_output_field.current.update()
            check_conv_start()

    def on_conv_format_change(e):
        # Update extension if single file
        nonlocal conv_target_path
        if conv_file_paths and len(conv_file_paths) == 1 and conv_target_path:
             try:
                 base = os.path.splitext(conv_target_path)[0]
                 new_ext = e.control.value
                 if not new_ext.startswith("."): new_ext = "." + new_ext
                 conv_target_path = f"{base}{new_ext}"
                 conv_output_field.current.value = os.path.basename(conv_target_path)
                 conv_output_field.current.update()
                 update_converter_preview() # Update Preview on format change!
             except: pass

    conv_picker = ft.FilePicker()
    conv_dir_picker = ft.FilePicker()
    conv_save_picker = ft.FilePicker()
    conv_out_dir_picker = ft.FilePicker()


    def check_can_start():
        if compress_btn.current:
            compress_btn.current.disabled = not bool(selected_file_paths)
            compress_btn.current.update()

    
    
    def on_slider_change_end(e):
        nonlocal last_set_by_slider
        try:
            val = float(e.control.value)
            last_set_by_slider = val
            target_size_input.current.value = f"{val:.1f}"
            target_size_input.current.update()
        except: pass

    def on_text_change(e):
        nonlocal last_set_by_slider
        try:
            if not e.control.value: return
            val = float(e.control.value)
            
            # If this value matches what the slider just set, ignore it to prevent loop
            if abs(val - last_set_by_slider) < 0.1:
                return

            if 1 <= val <= 1000:
                if target_size_slider.current:
                     target_size_slider.current.value = min(val, 100)
                     target_size_slider.current.update()
        except: pass

    def on_size_input_change(e):
        on_text_change(e)

    def on_codec_change(e):
        if not gpu_switch.current: return
        gpu_switch.current.disabled = (e.control.value == "h266")
        if gpu_switch.current.disabled: gpu_switch.current.value = False
        gpu_switch.current.update()

    def on_container_change(e):
        nonlocal target_output_path
        # If single file is selected, update the extension in real-time
        if selected_file_paths and len(selected_file_paths) == 1:
            try:
                base = os.path.splitext(target_output_path)[0]
                new_ext = e.control.value
                if not new_ext.startswith("."): new_ext = "." + new_ext
                
                # Check if we should update
                target_output_path = f"{base}{new_ext}"
                output_display_field.current.value = os.path.basename(target_output_path)
                output_display_field.current.update()
            except: pass

    def reset_preview_ui():
        if status_overlay.current: status_overlay.current.opacity = 0
        if preview_image.current: preview_image.current.opacity = 0
        if placeholder_img_control.current: placeholder_img_control.current.opacity = 1
        page.update()

    async def on_advanced_title_click(e):
        nonlocal easter_egg_clicks, obscure_revealed, all_codecs_revealed
        
        easter_egg_clicks += 1
        
        # Stage 1: Obscure Encoders
        if not obscure_revealed and easter_egg_clicks >= 10:
            obscure_revealed = True
            new_options = [
                ft.DropdownOption("libxvid"),
                ft.DropdownOption("msmpeg4v2"),
                ft.DropdownOption("flv1"),
                ft.DropdownOption("h261"),
                ft.DropdownOption("h263"),
                ft.DropdownOption("snow"),
                ft.DropdownOption("cinepak"),
                ft.DropdownOption("roq"),
                ft.DropdownOption("smc"),
                ft.DropdownOption("vc1")
            ]
            if codec_dropdown.current:
                codec_dropdown.current.options.extend(new_options)
                codec_dropdown.current.update()
            
            advanced_dialog.open = False
            page.show_dialog(ft.SnackBar(ft.Text("Wow, you clicked some text 10 times and now encoders magically appeared... that's kinda stupid but whatever")))
            page.update()

        # Stage 2: THE APOCALYPSE
        elif obscure_revealed and not all_codecs_revealed and easter_egg_clicks >= 20:
            all_codecs_revealed = True
            
            # Fetch literally everything FFmpeg has to offer
            all_ffmpeg_encoders = logic.get_all_encoders()
            if all_ffmpeg_encoders and codec_dropdown.current:
                existing = [o.key for o in codec_dropdown.current.options]
                new_obs = [ft.DropdownOption(enc) for enc in all_ffmpeg_encoders if enc not in existing]
                codec_dropdown.current.options.extend(new_obs)
                codec_dropdown.current.update()
            
            advanced_dialog.open = False
            page.show_dialog(ft.SnackBar(ft.Text("Oh god, why would you do that again???? now its even worse we're gonna die!!! TOO MUCH ENCODERS AHHHHHHHHHHHHHHHHHH")))
            page.update()

    # --- Advanced Settings Dialog ---
    advanced_dialog = ft.AlertDialog(
        title=ft.GestureDetector(
            content=ft.Container(
                content=ft.Text("Advanced Settings", weight=ft.FontWeight.W_900),
                padding=10
            ),
            on_tap=on_advanced_title_click
        ),
        content=ft.Container(
            content=ft.Column([
                ft.Text("Fine-tune your encoding parameters for maximum quality:", color=ft.Colors.ON_SURFACE_VARIANT, size=13),
                ft.Divider(),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("Two-Pass Encoding", weight=ft.FontWeight.W_900, size=14),
                            ft.Text("Higher quality, 2x encoding time", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ], expand=True),
                        ft.Switch(ref=two_pass_switch, value=False, active_color=ft.Colors.PRIMARY)
                    ]),
                    tooltip="Analyzes video once before encoding to optimize bitrate distribution, doubling the encoding time but maximizing quality."
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("10-Bit Color (HDR/High Fidelity)", weight=ft.FontWeight.W_900, size=14),
                            ft.Text("Uses yuv420p10le pixel format", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ], expand=True),
                        ft.Switch(ref=ten_bit_switch, value=False, active_color=ft.Colors.PRIMARY)
                    ]),
                    tooltip="Increases color depth to prevent banding in gradients and improve HDR fidelity using the yuv420p10le format."
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("Video Denoising", weight=ft.FontWeight.W_900, size=14),
                            ft.Text("HQDN3D spatio-temporal filter", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ], expand=True),
                        ft.Switch(ref=denoise_switch, value=False, active_color=ft.Colors.PRIMARY)
                    ]),
                    tooltip="Removes grain and sensor noise using the hqdn3d filter, which helps the encoder focus on real details."
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("Adaptive Quantization (AQ)", weight=ft.FontWeight.W_900, size=14),
                            ft.Text("Prioritize bits for moving objects/faces", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ], expand=True),
                        ft.Switch(ref=aq_switch, value=False, active_color=ft.Colors.PRIMARY)
                    ]),
                    tooltip="Detects moving objects and complex textures to prioritize them for higher quality while compressing static areas more aggressively."
                ),
                ft.Divider(),
                ft.Text("Performance Preset (cpu-used)", size=14, weight=ft.FontWeight.W_900),
                ft.Container(
                    content=ft.Slider(
                        ref=cpu_used_slider, 
                        min=0, max=8, divisions=8, value=6, label="{value}"
                    ),
                    tooltip="Controls encoding speed vs. quality. Lower values are slower but higher quality."
                ),
                ft.Row([
                    ft.Container(
                        content=ft.TextField(
                            ref=keyframe_input, label="GOP (Keyframes)", value="300", expand=True, border_radius=10
                        ),
                        expand=True,
                        tooltip="Distance between full keyframes. Higher improves compression; Lower improves seeking."
                    ),
                ], spacing=10),
            ], tight=True, spacing=15),
            width=500,
            padding=10
        ),
        actions=[
            ft.TextButton("Close", on_click=lambda _: (setattr(advanced_dialog, "open", False), page.update()))
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(advanced_dialog)

    # --- Error Dialog ---
    error_dialog = ft.AlertDialog(
        title=ft.Row([
            ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR, size=32),
            ft.Text("Compression Error", weight=ft.FontWeight.W_900, color=ft.Colors.ERROR)
        ], spacing=10),
        content=ft.Container(
            content=ft.Column([
                ft.Text("An error occurred during compression:", size=14),
                ft.Divider(),
                ft.Container(
                    content=ft.Text(
                        ref=error_log_text,
                        value="",
                        size=12,
                        selectable=True,
                        color=ft.Colors.ON_SURFACE_VARIANT
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    padding=15,
                    border_radius=10,
                    height=300,
                    width=500
                )
            ], tight=True, spacing=10, scroll=ft.ScrollMode.AUTO),
            width=550,
            padding=10
        ),
        actions=[
            ft.TextButton("Close", on_click=lambda _: (setattr(error_dialog, "open", False), page.update()))
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(error_dialog)

    def show_error(error_message, detailed_log=""):
        """Display error in modal dialog"""
        if error_log_text.current:
            full_message = f"{error_message}\n\n{detailed_log}" if detailed_log else error_message
            error_log_text.current.value = full_message
        error_dialog.open = True
        page.update()

    def show_success(message):
        """Display success snackbar"""
        snack = ft.SnackBar(
            content=ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN), ft.Text(message)]),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            action="OK"
        )
        page.snack_bar = snack
        snack.open = True
        page.update()

    def run_compression():
        nonlocal selected_file_paths, target_output_path, is_compressing
        if not selected_file_paths: return
        
        try: target_mb = float(target_size_input.current.value)
        except:
            log("\n❌ Invalid Target Size.")
            return

        stop_event.clear()
        is_compressing = True
        
        # Reset visual state for new run
        status_overlay.current.opacity = 0
        preview_image.current.opacity = 0
        placeholder_img_control.current.opacity = 1
        
        codec = codec_dropdown.current.value
        use_gpu = gpu_switch.current.value
        show_preview = preview_switch.current.value
        
        # Advanced Params
        adv_params = {
            "two_pass": two_pass_switch.current.value,
            "ten_bit": ten_bit_switch.current.value,
            "denoise": denoise_switch.current.value,
            "aq": aq_switch.current.value,
            "cpu_used": int(cpu_used_slider.current.value),

            "keyframe": keyframe_input.current.value
        }

        if compress_btn.current: compress_btn.current.disabled = True
        if stop_btn.current: stop_btn.current.disabled = False
        if btn_text.current: btn_text.current.value = f"Compressing... (0/{len(selected_file_paths)})"
        
        # Reset Progress UI
        if res_text.current: res_text.current.value = "---"
        if rem_time_text.current: rem_time_text.current.value = "---"
        if fps_text.current: fps_text.current.value = "---"
        if pct_text.current: pct_text.current.value = "0%"
        update_progress_bar(0)
        
        # Files processed label visibility removed per request
        if files_processed_text.current:
            files_processed_text.current.visible = False
        
        # Reset preview to show placeholder until first frame is ready
        if show_preview and preview_image.current and placeholder_img_control.current:
            preview_image.current.opacity = 0
            placeholder_img_control.current.opacity = 1
            preview_image.current.update()
            placeholder_img_control.current.update()
        
        page.update()
        
        if show_preview:
            threading.Thread(target=update_preview_loop, daemon=True).start()

        log(f"\n🚀 STARTING COMPRESSION... ({len(selected_file_paths)} file(s))")

        try:
            total_files = len(selected_file_paths)
            successful_count = 0
            
            for idx, input_file in enumerate(selected_file_paths):
                if stop_event.is_set():
                    break
                    
                # Determine output path for this file
                if total_files == 1:
                    output_file = target_output_path
                else:
                    # Batch mode: save to output folder with _compressed suffix
                    base_name = os.path.basename(input_file)
                    name = os.path.splitext(base_name)[0]
                    output_folder = target_output_path if target_output_path else os.path.dirname(input_file)
                    
                    # Use selected container
                    ext = container_dropdown.current.value
                    if not ext.startswith("."): ext = "." + ext
                    
                    output_file = os.path.join(output_folder, f"{name}_compressed{ext}")
                
                btn_text.current.value = f"Compressing... ({idx + 1}/{total_files})"
                page.update()
                
                log(f"\n📹 Processing: {os.path.basename(input_file)}")
                
                success, final_output = logic.auto_compress(
                    input_file, 
                    target_mb, 
                    codec, 
                    use_gpu, 
                    output_file=output_file,
                    log_func=log,
                    stop_event=stop_event,
                    preview_path=preview_file_path if show_preview else None,
                    progress_callback=on_progress,
                    advanced_params=adv_params
                )
                
                if success:
                    successful_count += 1
                    log(f"✅ Saved: {os.path.basename(final_output)}")
                else:
                    log(f"❌ Failed: {os.path.basename(input_file)}")
                
                # Update files processed counter removed per request
                pass
            
            # Final status
            update_progress_bar(1.0)
            if pct_text.current: pct_text.current.value = "100%"
            page.update()
            if stop_event.is_set():
                msg = "🛑 STOPPED"
                log(f"\n🛑 Compression cancelled. ({successful_count}/{total_files} completed)")
            elif successful_count == total_files:
                msg = "✨ SUCCESS!"
                log(f"\n✨ ALL DONE! {successful_count}/{total_files} files compressed successfully!")
                play_complete_ding()
                if user_settings.get("auto_open_folder") and target_output_path:
                    open_folder(target_output_path)
            elif successful_count > 0:
                msg = f"⚠️ PARTIAL ({successful_count}/{total_files})"
                log(f"\n⚠️ Completed {successful_count}/{total_files} files.")
            else:
                msg = "❌ FAILED"
                log(f"\n❌ All compressions failed.")
            
            # Overlay effect
            status_text.current.value = msg
            status_overlay.current.opacity = 1
            page.update()
            
            time.sleep(3)
            reset_preview_ui()

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log(f"\n❌ Error: {e}")
            show_error(f"Compression failed: {str(e)}", error_details)
        finally:
            is_compressing = False
            reset_ui()
            page.update()

    def on_conv_format_change(e):
        # Update extension if single file
        nonlocal conv_target_path
        fmt = e.control.value
        
        # Show/hide Remove Black BG toggle based on format
        is_webp = (fmt == "webp")
        if conv_remove_bg_icon.current:
            conv_remove_bg_icon.current.visible = is_webp
            conv_remove_bg_icon.current.update()
        if conv_remove_bg_text.current:
            conv_remove_bg_text.current.visible = is_webp
            conv_remove_bg_text.current.update()
        if conv_remove_bg_switch.current:
            conv_remove_bg_switch.current.visible = is_webp
            conv_remove_bg_switch.current.update()
        
        # Smart Codec Selection
        if conv_acodec_dropdown.current:
            if fmt == "mp4":
                conv_acodec_dropdown.current.value = "aac"
                if conv_vcodec_dropdown.current: conv_vcodec_dropdown.current.disabled = False
            elif fmt == "mp3":
                conv_acodec_dropdown.current.value = "libmp3lame"
                if conv_vcodec_dropdown.current: conv_vcodec_dropdown.current.disabled = True
            elif fmt == "wav":
                conv_acodec_dropdown.current.value = "pcm_s16le"
                if conv_vcodec_dropdown.current: conv_vcodec_dropdown.current.disabled = True
            elif fmt == "flac":
                conv_acodec_dropdown.current.value = "flac"
                if conv_vcodec_dropdown.current: conv_vcodec_dropdown.current.disabled = True
            elif fmt == "mkv":
                # MKV supports almost anything, leave as is or default to copy
                if conv_vcodec_dropdown.current: conv_vcodec_dropdown.current.disabled = False
                
            conv_acodec_dropdown.current.update()
            if conv_vcodec_dropdown.current: conv_vcodec_dropdown.current.update()

        if conv_file_paths and len(conv_file_paths) == 1 and conv_target_path:
             try:
                 base = os.path.splitext(conv_target_path)[0]
                 new_ext = fmt
                 if not new_ext.startswith("."): new_ext = "." + new_ext
                 conv_target_path = f"{base}{new_ext}"
                 conv_output_field.current.value = os.path.basename(conv_target_path)
                 conv_output_field.current.update()
                 update_converter_preview() # Update Preview on format change!
             except: pass

    async def conv_files_click(e):
        on_conv_files_picked(await conv_picker.pick_files(allow_multiple=True))

    async def conv_folder_click(e):
        on_conv_folder_picked(await conv_dir_picker.get_directory_path())

    async def conv_output_click(e):
        if len(conv_file_paths) > 1:
            on_conv_out_folder_picked(await conv_out_dir_picker.get_directory_path())
        else:
            on_conv_save_picked(await conv_save_picker.save_file(file_name="converted.mp4"))


    def check_can_start():
        if compress_btn.current:
            can_start = bool(selected_file_paths) and bool(target_output_path) and not is_compressing
            compress_btn.current.disabled = not can_start
            compress_btn.current.update()

    def reset_ui():
        if compress_btn.current: compress_btn.current.disabled = False
        if stop_btn.current: stop_btn.current.disabled = True
        if btn_text.current: btn_text.current.value = "Start Compression"
        if compress_btn.current: compress_btn.current.update()
        if stop_btn.current: stop_btn.current.update()

    def stop_compression(e):
        stop_event.set()
        stop_btn.current.disabled = True
        stop_btn.current.update()
        log("⌛ Stopping...")

    # --- UI Components ---
    
    header = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.VIDEO_LIBRARY_ROUNDED, size=30, color=ft.Colors.PRIMARY),
            ft.Text("Video Utilities", size=24, weight=ft.FontWeight.W_900, color=ft.Colors.PRIMARY),
        ], alignment=ft.MainAxisAlignment.CENTER),
        margin=ft.Margin.only(bottom=10)
    )

    # 1. File Selection
    file_section = ft.Container(
        content=ft.Column([
            # Top row with File/Files, Folder, and Choose buttons
            ft.Row([
                ft.FilledButton(
                    "File/Files", 
                    icon=ft.Icons.ATTACH_FILE_ROUNDED, 
                    on_click=pick_files_click, 
                    style=ft.ButtonStyle(
                        padding=10, 
                        shape=ft.RoundedRectangleBorder(radius=30), 
                        bgcolor=ft.Colors.PRIMARY, 
                        color=ft.Colors.ON_PRIMARY
                    )
                ),
                ft.FilledButton(
                    "Folder", 
                    icon=ft.Icons.FOLDER_ROUNDED, 
                    on_click=pick_folder_click, 
                    style=ft.ButtonStyle(
                        padding=10, 
                        shape=ft.RoundedRectangleBorder(radius=30), 
                        bgcolor=ft.Colors.PRIMARY, 
                        color=ft.Colors.ON_PRIMARY
                    )
                ),
                ft.Container(expand=True),
                ft.FilledButton(
                    "Choose", 
                    icon=ft.Icons.DOWNLOAD_ROUNDED, 
                    on_click=pick_output_click, 
                    style=ft.ButtonStyle(
                        padding=10,
                        shape=ft.RoundedRectangleBorder(radius=30),
                        bgcolor=ft.Colors.PRIMARY,
                        color=ft.Colors.ON_PRIMARY
                    )
                )
            ], spacing=5),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            # Input and Output fields
            ft.Row([
                ft.Container(
                    content=ft.TextField(
                        ref=input_display_field,
                        label="Input",
                        read_only=True,
                        border_color=ft.Colors.OUTLINE,
                        border_radius=12,
                        text_size=14,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        height=40,
                        content_padding=10
                    ),
                    expand=True
                ),
                ft.Container(
                    content=ft.TextField(
                        ref=output_display_field,
                        label="Output",
                        read_only=True,
                        border_color=ft.Colors.OUTLINE,
                        border_radius=12,
                        text_size=14,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        height=40,
                        content_padding=10
                    ),
                    expand=True
                )
            ], spacing=10)
        ]),
        padding=0,
        margin=ft.Margin.only(bottom=5)
    )

    # 2. Main Settings Card
    settings_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.SETTINGS_OUTLINED, color=ft.Colors.PRIMARY, size=20),
                ft.Text("Compression Settings", size=16, weight=ft.FontWeight.W_900),
            ], spacing=5),
            ft.Divider(color=ft.Colors.OUTLINE_VARIANT, height=5),
            ft.Row([
                ft.Text("Target Size:", size=14),
                ft.TextField(
                    ref=target_size_input, 
                    value="10.0", 
                    width=90, 
                    height=35, 
                    content_padding=5, 
                    text_align=ft.TextAlign.RIGHT, 
                    suffix=" MB", 
                    on_change=on_text_change, 
                    border_color=ft.Colors.OUTLINE,
                    border_radius=10,
                    text_size=13,
                    focused_border_color=ft.Colors.PRIMARY
                )
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Slider(
                ref=target_size_slider, 
                min=1, 
                max=100, 
                divisions=99, 
                value=9, 
                label="{value}",
                on_change_end=on_slider_change_end,
                active_color=ft.Colors.PRIMARY,
                inactive_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            ),
            ft.Row([
                ft.Row([
                    ft.Dropdown(
                        ref=codec_dropdown, 
                        label="Codec", 
                        width=120, 
                        options=[
                            ft.DropdownOption("av1"), 
                            ft.DropdownOption("h264"), 
                            ft.DropdownOption("h265"), 
                            ft.DropdownOption("h266"),
                            ft.DropdownOption("vp9"),
                            ft.DropdownOption("vp8"),
                            ft.DropdownOption("mpeg4"),
                            ft.DropdownOption("mpeg2"),
                            ft.DropdownOption("theora"),
                            ft.DropdownOption("wmv")
                        ], 
                        value="av1", 
                        on_select=on_codec_change,
                        border_radius=10,
                        text_size=13,
                        content_padding=5,
                        height=40,
                        menu_height=300
                    ),
                    ft.Dropdown(
                        ref=container_dropdown,
                        label="Container",
                        width=110, 
                        options=[
                            ft.DropdownOption("mp4"), 
                            ft.DropdownOption("mkv"), 
                            ft.DropdownOption("webm"), 
                            ft.DropdownOption("mov"),
                            ft.DropdownOption("avi"),
                            ft.DropdownOption("flv"),
                            ft.DropdownOption("wmv"),
                            ft.DropdownOption("ogg")
                        ],
                        value="mp4",
                        on_select=on_container_change,
                        border_radius=10,
                        text_size=13,
                        content_padding=5,
                        height=40,
                        menu_height=300
                    ),
                ], spacing=10),
                
                ft.Row([
                    ft.Icon(ft.Icons.SPEED, size=18, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text("GPU", color=ft.Colors.ON_SURFACE_VARIANT, size=13),
                    ft.Switch(ref=gpu_switch, value=True, active_color=ft.Colors.PRIMARY, scale=0.8)
                ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                
                ft.Row([
                    ft.Icon(ft.Icons.REMOVE_RED_EYE_OUTLINED, size=18, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text("Preview", color=ft.Colors.ON_SURFACE_VARIANT, size=13),
                    ft.Switch(ref=preview_switch, value=False, on_change=on_preview_toggle, active_color=ft.Colors.PRIMARY, scale=0.8)
                ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER),

                ft.Container(expand=True, bgcolor=ft.Colors.TRANSPARENT), # Invisible spacer
                ft.TextButton(
                    "Advanced", 
                    icon=ft.Icons.TUNE_ROUNDED,
                    on_click=lambda _: (setattr(advanced_dialog, "open", True), page.update()),
                    style=ft.ButtonStyle(color=ft.Colors.PRIMARY, padding=5)
                )
            ], alignment=ft.MainAxisAlignment.START, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=False)
        ], spacing=5), 
        padding=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=15,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
    )

    log_side = ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=15,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        padding=15,
        expand=True,
        content=ft.Column([
            ft.Text(
                "0/0 files processed",
                ref=files_processed_text,
                size=14,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.ON_SURFACE_VARIANT,
                visible=False
            ),
            ft.Text("Progress", size=48, weight=ft.FontWeight.W_900, color=ft.Colors.ON_SURFACE),
            ft.Row([
                ft.Text("Resolution : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("---", ref=res_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                ft.VerticalDivider(width=20, color=ft.Colors.TRANSPARENT),
                ft.Text("Time remaining : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("---", ref=rem_time_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                ft.VerticalDivider(width=20, color=ft.Colors.TRANSPARENT),
                ft.Text("Frame rate : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("---", ref=fps_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                ft.VerticalDivider(width=20, color=ft.Colors.TRANSPARENT),
                ft.Text("Percentage : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("0%", ref=pct_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
            ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(
                ref=progress_container,
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                height=6,
                border_radius=3,
                alignment=ft.Alignment.CENTER_LEFT,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                content=ft.Container(
                    ref=progress_fill,
                    width=0,
                    bgcolor=ft.Colors.PRIMARY,
                    height=6,
                    animate=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
                )
            )
        ], spacing=15, alignment=ft.MainAxisAlignment.CENTER) 
    )

    preview_side = ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=20,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        padding=15,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, size=20, color=ft.Colors.PRIMARY),
                ft.Text("Preview:", size=16, weight=ft.FontWeight.W_900),
            ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(
                content=ft.Stack([
                    # 1. Project Placeholder
                    ft.Container(
                        content=ft.Image(
                            ref=placeholder_img_control,
                            src="placeholder.png",
                            fit=ft.BoxFit.COVER, 
                            animate_opacity=400,
                            opacity=1,
                            expand=True
                        ),
                        alignment=ft.Alignment.CENTER,
                        expand=True
                    ),
                    # 2. Live Dynamic Frame
                    ft.Container(
                        content=ft.Image(
                            ref=preview_image,
                            src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",  # 1x1 transparent pixel
                            fit=ft.BoxFit.CONTAIN, 
                            opacity=0,
                            animate_opacity=400,
                            gapless_playback=True,
                            expand=True
                        ),
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                    ),
                    # 3. Dynamic Status Overlay
                    ft.Container(
                        ref=status_overlay,
                        bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.SURFACE_CONTAINER_HIGHEST),
                        blur=50,
                        border_radius=10,
                        opacity=0,
                        visible=True,
                        animate_opacity=400,
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                        content=ft.Text(ref=status_text, value="", size=28, weight=ft.FontWeight.W_900, color=ft.Colors.ON_SURFACE)
                    )
                ], expand=True),
                alignment=ft.Alignment.CENTER,
                expand=True,
                bgcolor=ft.Colors.TRANSPARENT,
                border_radius=12,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS
            )
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
    )

    content_row = ft.Row([
        ft.Container(content=log_side, expand=True), 
        ft.Container(
            ref=preview_container,
            content=preview_side,
            width=0,
            opacity=0,
            visible=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            animate=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO),
            animate_opacity=ft.Animation(400, ft.AnimationCurve.EASE_OUT)
        )
    ], spacing=20, expand=True)

    controls_row = ft.Row([
        ft.FilledButton(
            ref=compress_btn, 
            content=ft.Row([
                ft.Icon(ft.Icons.BOLT_ROUNDED), 
                ft.Text("Start Compression", ref=btn_text, size=16, weight=ft.FontWeight.W_900)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10), 
            style=ft.ButtonStyle(
                padding=15, 
                shape=ft.RoundedRectangleBorder(radius=10),
                bgcolor={ft.ControlState.DEFAULT: ft.Colors.PRIMARY},
                color={ft.ControlState.DEFAULT: ft.Colors.ON_PRIMARY}
            ), 
            on_click=lambda _: threading.Thread(target=run_compression, daemon=True).start(), 
            disabled=True, 
            expand=True
        ),
        ft.OutlinedButton(
            ref=stop_btn, 
            content="Stop", 
            icon=ft.Icons.STOP_CIRCLE_OUTLINED, 
            style=ft.ButtonStyle(
                padding=15, 
                color={ft.ControlState.DEFAULT: ft.Colors.RED_400},
                shape=ft.RoundedRectangleBorder(radius=10),
                side={ft.ControlState.DEFAULT: ft.BorderSide(1, ft.Colors.RED_400)}
            ), 
            on_click=stop_compression, 
            disabled=True
        )
    ], spacing=15)

    # --- Tab System & Views ---
    # current_tab assigned at start of main
    
    tab_indicator = ft.Ref[ft.Container]()
    tab_compressor_text = ft.Ref[ft.Text]()
    tab_converter_text = ft.Ref[ft.Text]()
    tab_trimmer_text = ft.Ref[ft.Text]()
    tab_merger_text = ft.Ref[ft.Text]()
    tab_more_text = ft.Ref[ft.Text]()
    tab_more_text = ft.Ref[ft.Text]()
    tab_compressor_icon = ft.Ref[ft.Icon]()
    tab_converter_icon = ft.Ref[ft.Icon]()
    tab_trimmer_icon = ft.Ref[ft.Icon]()
    tab_merger_icon = ft.Ref[ft.Icon]()
    tab_more_icon = ft.Ref[ft.Icon]()
    setting_theme_switch = ft.Ref[ft.Switch]()
    view_switcher = ft.Ref[ft.AnimatedSwitcher]()
    
    # --- Animated Views ---
    
    # --- Views ---
    
    compressor_view_col = ft.Column([
        file_section,
        settings_card,
        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
        content_row,
        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
        controls_row
    ], 
    visible=True, 
    expand=True,
    offset=ft.Offset(0, 0),
    animate_offset=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
)

    # --- Converter UI Components ---
    
    conv_file_section = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.FilledButton(
                    "File/Files", 
                    icon=ft.Icons.ATTACH_FILE_ROUNDED, 
                    on_click=conv_files_click, 
                    style=ft.ButtonStyle(
                        padding=10, 
                        shape=ft.RoundedRectangleBorder(radius=30), 
                        bgcolor=ft.Colors.PRIMARY, 
                        color=ft.Colors.ON_PRIMARY
                    )
                ),
                ft.FilledButton(
                    "Folder", 
                    icon=ft.Icons.FOLDER_ROUNDED, 
                    on_click=conv_folder_click, 
                    style=ft.ButtonStyle(
                        padding=10, 
                        shape=ft.RoundedRectangleBorder(radius=30), 
                        bgcolor=ft.Colors.PRIMARY, 
                        color=ft.Colors.ON_PRIMARY
                    )
                ),
                ft.Container(expand=True),
                ft.FilledButton(
                    "Choose", 
                    icon=ft.Icons.DOWNLOAD_ROUNDED, 
                    on_click=conv_output_click, 
                    style=ft.ButtonStyle(
                        padding=10, 
                        shape=ft.RoundedRectangleBorder(radius=30), 
                        bgcolor=ft.Colors.PRIMARY, 
                        color=ft.Colors.ON_PRIMARY
                    )
                )
            ], spacing=5),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.Row([
                ft.Container(
                    content=ft.TextField(
                        ref=conv_input_field, 
                        label="Input", 
                        read_only=True, 
                        border_color=ft.Colors.OUTLINE, 
                        border_radius=12, 
                        text_size=14, 
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        height=40,
                        content_padding=10
                    ), 
                    expand=True
                ),
                ft.Container(
                    content=ft.TextField(
                        ref=conv_output_field, 
                        label="Output", 
                        read_only=True, 
                        border_color=ft.Colors.OUTLINE, 
                        border_radius=12, 
                        text_size=14, 
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        height=40,
                        content_padding=10
                    ), 
                    expand=True
                )
            ], spacing=10)
        ]),
        padding=0, 
        margin=ft.Margin.only(bottom=5)
    )

    conv_preview_switch = ft.Ref[ft.Switch]()
    conv_remove_bg_switch = ft.Ref[ft.Switch]()
    conv_remove_bg_icon = ft.Ref[ft.Icon]()
    conv_remove_bg_text = ft.Ref[ft.Text]()
    
    def run_conversion():
        if not conv_file_paths or not conv_target_path: return
        
        nonlocal conv_is_running
        conv_is_running = True
        conv_start_btn.current.disabled = True
        conv_stop_btn.current.disabled = False
        conv_start_btn.current.update()
        conv_stop_btn.current.update()
        
        # Reset UI
        if conv_progress_fill.current: conv_progress_fill.current.width = 0
        if conv_pct_text.current: conv_pct_text.current.value = "0%"
        if conv_time_text.current: conv_time_text.current.value = "---"
        
        # Reset Overlay
        if conv_status_overlay.current:
            conv_status_overlay.current.opacity = 0
            conv_status_overlay.current.update()
        
        page.update()

        input_path = conv_file_paths[0]
        output_path = conv_target_path
        
        # Parameters
        fmt = conv_fmt_dropdown.current.value if conv_fmt_dropdown.current else "mp4"
        vcodec = conv_vcodec_dropdown.current.value if conv_vcodec_dropdown.current else "libx264"
        acodec = conv_acodec_dropdown.current.value if conv_acodec_dropdown.current else "aac"
        
        # Validation Fixes
        if fmt == "wav" and "opus" in acodec:
            acodec = "pcm_s16le"
            if conv_acodec_dropdown.current:
                 conv_acodec_dropdown.current.value = "pcm_s16le"
                 conv_acodec_dropdown.current.update()
        elif fmt == "mp3" and "opus" in acodec:
            acodec = "libmp3lame"
            if conv_acodec_dropdown.current:
                 conv_acodec_dropdown.current.value = "libmp3lame" 
                 conv_acodec_dropdown.current.update()
        
        is_audio = fmt in ["mp3", "wav", "flac", "aac", "opus", "ogg", "m4a"]
        
        if fmt == "gif" or fmt == "webp":
            # Detect source FPS
            input_fps = 30 # fallback
            try:
                fps_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", input_path]
                fps_res = subprocess.run(fps_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
                fps_str = fps_res.stdout.strip()
                if "/" in fps_str:
                    n, d = map(float, fps_str.split("/"))
                    input_fps = n / d if d != 0 else 30
                else:
                    input_fps = float(fps_str)
            except: pass
            
            if fmt == "gif":
                # Cap at 50fps: high-FPS GIFs (like 60) often trigger "slow motion" fallback in browsers (delay 1 -> 10)
                gif_fps = min(input_fps, 50)
                cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"fps={gif_fps:.2f},scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse", output_path]
            else:
                # Animated WebP — matches: ffmpeg -i input -vf "fps=60,scale=w=-1:h=720" -vcodec libwebp -lossless 0 -q:v 80 -loop 0 -preset default -an output.webp
                remove_bg = conv_remove_bg_switch.current and conv_remove_bg_switch.current.value
                if remove_bg:
                    vf = f"fps={int(input_fps)},scale=w=-1:h=720,colorkey=black:0.1:0.2,format=rgba"
                else:
                    vf = f"fps={int(input_fps)},scale=w=-1:h=720"
                cmd = [
                    "ffmpeg", "-y", "-i", input_path,
                    "-vf", vf,
                    "-vcodec", "libwebp", "-lossless", "0",
                    "-q:v", "80", "-loop", "0",
                    "-preset", "default", "-an",
                    output_path
                ]
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path]
            if is_audio:
                cmd.extend(["-vn", "-c:a", acodec if acodec != "copy" else "copy"])
            else:
                cmd.extend(["-c:v", vcodec, "-c:a", acodec])
            cmd.append(output_path)

        def encoding_thread():
             nonlocal conv_is_running
             try:
                 log(f"\n🚀 CONVERTING: {os.path.basename(input_path)}")
                 # Ensure all cmd parts are strings
                 safe_cmd = [str(x) for x in cmd if x is not None]
                 process = subprocess.Popen(safe_cmd, stderr=subprocess.PIPE, universal_newlines=True, creationflags=SUBPROCESS_FLAGS)
                 
                 # Get total duration
                 total_duration = 0
                 try:
                     dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_path]
                     dur_res = subprocess.run(dur_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
                     total_duration = float(dur_res.stdout.strip())
                 except: pass
                 
                 import re
                 start_time = time.time()
                 lines = []
                 while True:
                     line = process.stderr.readline()
                     if not line and process.poll() is not None: break
                     if line:
                         lines.append(line)
                         time_match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", line)
                         if time_match and total_duration > 0:
                             t_str = time_match.group(1)
                             h, m, s = map(float, t_str.split(':'))
                             current_seconds = h*3600 + m*60 + s
                             pct = min(current_seconds / total_duration, 1.0)
                             
                             elapsed = time.time() - start_time
                             speed = current_seconds / elapsed if elapsed > 0 else 0
                             rem_time = (total_duration - current_seconds) / speed if speed > 0 else 0
                             
                             if conv_pct_text.current: conv_pct_text.current.value = f"{int(pct*100)}%"
                             update_conv_progress_bar(pct)
                             if conv_time_text.current: conv_time_text.current.value = f"{int(rem_time)}s"
                             if conv_fps_text.current: conv_fps_text.current.value = f"{speed:.1f}x"
                             
                             conv_pct_text.current.update()
                             conv_time_text.current.update()
                             conv_fps_text.current.update()

                 return_code = process.poll()
                 if return_code == 0:
                     update_conv_progress_bar(1.0)
                     if conv_pct_text.current: conv_pct_text.current.value = "100%"; conv_pct_text.current.update()
                     if conv_status_text.current:
                         conv_status_text.current.value = "Done!"
                         conv_status_overlay.current.opacity = 1
                         conv_status_overlay.current.update()
                         play_complete_ding()
                         if user_settings.get("auto_open_folder") and conv_target_path:
                             open_folder(conv_target_path)
                 else:
                     log(f"❌ FFmpeg Error: {''.join(lines[-5:])}")
                     if conv_status_text.current:
                         conv_status_text.current.value = "Error!"
                         conv_status_overlay.current.opacity = 1
                         conv_status_overlay.current.update()
             except Exception as e:
                 log(f"❌ Exception: {e}")
             finally:
                 conv_is_running = False
                 if conv_start_btn.current: conv_start_btn.current.disabled = False; conv_start_btn.current.update()
                 if conv_stop_btn.current: conv_stop_btn.current.disabled = True; conv_stop_btn.current.update()

        threading.Thread(target=encoding_thread, daemon=True).start()

    conv_settings_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.SETTINGS_OUTLINED, color=ft.Colors.PRIMARY, size=20), 
                ft.Text("Conversion Settings", size=16, weight=ft.FontWeight.W_900)
            ], spacing=5),
            ft.Divider(color=ft.Colors.OUTLINE_VARIANT, height=10),
            ft.Row([
                ft.Dropdown(
                    ref=conv_fmt_dropdown, 
                    label="Format", 
                    width=110, 
                    options=[
                        ft.DropdownOption("mp4"), ft.DropdownOption("mkv"), 
                        ft.DropdownOption("mp3"), ft.DropdownOption("wav"), 
                        ft.DropdownOption("flac"), ft.DropdownOption("gif"),
                        ft.DropdownOption("webp")
                    ], 
                    value="mp4", 
                    on_select=on_conv_format_change, 
                    border_radius=10, 
                    text_size=13,
                    content_padding=5,
                    height=40,
                    menu_height=300
                ),
                ft.Dropdown(
                    ref=conv_vcodec_dropdown, 
                    label="Video Codec", 
                    width=120, 
                    options=[
                        ft.DropdownOption("copy"), ft.DropdownOption("libx264"), 
                        ft.DropdownOption("libx265"), ft.DropdownOption("libsvtav1")
                    ], 
                    value="libx264", 
                    border_radius=10, 
                    text_size=13,
                    content_padding=5,
                    height=40,
                    menu_height=300
                ),
                ft.Dropdown(
                    ref=conv_acodec_dropdown, 
                    label="Audio Codec", 
                    width=120, 
                    options=[
                        ft.DropdownOption("copy"), ft.DropdownOption("aac"), 
                        ft.DropdownOption("libmp3lame"), ft.DropdownOption("libopus"), 
                        ft.DropdownOption("pcm_s16le"), ft.DropdownOption("flac")
                    ], 
                    value="aac", 
                    border_radius=10, 
                    text_size=13,
                    content_padding=5,
                    height=40,
                    menu_height=300
                ),
                ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT),
                ft.Icon(ft.Icons.REMOVE_RED_EYE_OUTLINED, size=18, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("Preview", color=ft.Colors.ON_SURFACE_VARIANT, size=13),
                ft.Switch(ref=conv_preview_switch, value=True, active_color=ft.Colors.PRIMARY, scale=0.8),
                ft.Icon(ref=conv_remove_bg_icon, icon=ft.Icons.FORMAT_COLOR_RESET_OUTLINED, size=18, color=ft.Colors.ON_SURFACE_VARIANT, visible=False),
                ft.Text(ref=conv_remove_bg_text, value="Remove Black BG", color=ft.Colors.ON_SURFACE_VARIANT, size=13, visible=False),
                ft.Switch(ref=conv_remove_bg_switch, value=False, active_color=ft.Colors.PRIMARY, scale=0.8, visible=False),
            ], alignment=ft.MainAxisAlignment.START, spacing=10, wrap=False, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=5),
        padding=10, 
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, 
        border_radius=15, 
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
    )

    conv_controls_row = ft.Row([
        ft.FilledButton(
            ref=conv_start_btn, 
            content=ft.Row([
                ft.Icon(ft.Icons.BOLT_ROUNDED), 
                ft.Text("Start Conversion", size=16, weight=ft.FontWeight.W_900)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10), 
            style=ft.ButtonStyle(
                padding=15, 
                shape=ft.RoundedRectangleBorder(radius=10), 
                bgcolor={ft.ControlState.DEFAULT: ft.Colors.PRIMARY}, 
                color={ft.ControlState.DEFAULT: ft.Colors.ON_PRIMARY}
            ), 
            on_click=lambda _: run_conversion(), 
            disabled=True, 
            expand=True
        ),
        ft.OutlinedButton(
            ref=conv_stop_btn, 
            content="Stop", 
            icon=ft.Icons.STOP_CIRCLE_OUTLINED, 
            style=ft.ButtonStyle(
                padding=15, 
                color={ft.ControlState.DEFAULT: ft.Colors.RED_400}, 
                shape=ft.RoundedRectangleBorder(radius=10), 
                side={ft.ControlState.DEFAULT: ft.BorderSide(1, ft.Colors.RED_400)}
            ), 
            on_click=lambda _: log("Stop Conversion Requested"), 
            disabled=True
        )
    ], spacing=15)

    # Converter Log & Preview
    conv_log_side = ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=15,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        padding=15,
        expand=True,
        content=ft.Column([
            ft.Text("0/0 converted", ref=conv_files_proc_text, size=14, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE_VARIANT, visible=False),
            ft.Text("Progress", size=48, weight=ft.FontWeight.W_900, color=ft.Colors.ON_SURFACE),
            ft.Row([
                ft.Text("Time remaining : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("---", ref=conv_time_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                ft.VerticalDivider(width=20, color=ft.Colors.TRANSPARENT),
                ft.Text("Speed : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("---", ref=conv_fps_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                ft.VerticalDivider(width=20, color=ft.Colors.TRANSPARENT),
                ft.Text("Percentage : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("0%", ref=conv_pct_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
            ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                height=6,
                border_radius=3,
                alignment=ft.Alignment.CENTER_LEFT,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                content=ft.Container(
                    ref=conv_progress_fill,
                    width=0,
                    bgcolor=ft.Colors.PRIMARY,
                    height=6,
                    animate=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
                )
            )
        ], spacing=15, alignment=ft.MainAxisAlignment.CENTER) 
    )

    conv_preview_side = ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=15,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        padding=15,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.REMOVE_RED_EYE_OUTLINED, size=20, color=ft.Colors.PRIMARY),
                ft.Text("Preview / Waveform", size=18, weight=ft.FontWeight.W_600),
            ], spacing=10),
            ft.Divider(color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                content=ft.Stack([
                    ft.Container(
                        content=ft.Image(ref=conv_placeholder_img, src="placeholder.png", fit=ft.BoxFit.COVER, opacity=1, expand=True),
                        alignment=ft.Alignment.CENTER, expand=True
                    ),
                    ft.Container(
                        content=ft.Image(ref=conv_preview_img, fit=ft.BoxFit.CONTAIN, border_radius=10, opacity=0, src="https://via.placeholder.com/480x270/111111/FFFFFF?text=Audio+Waveform", expand=True),
                        alignment=ft.Alignment.CENTER, expand=True
                    ),
                    ft.Container(
                        ref=conv_status_overlay,
                        bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.SURFACE_CONTAINER_HIGHEST),
                        blur=50,
                        border_radius=10,
                        opacity=0,
                        visible=True,
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                        content=ft.Text(ref=conv_status_text, value="", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE)
                    )
                ], expand=True),
                alignment=ft.Alignment.CENTER, expand=True, bgcolor=ft.Colors.TRANSPARENT, border_radius=12, clip_behavior=ft.ClipBehavior.ANTI_ALIAS
            )
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
    )

    conv_content_row = ft.Row([
        ft.Container(content=conv_log_side, expand=True), 
        ft.Container(
            ref=conv_preview_container,
            content=conv_preview_side,
            width=0,
            opacity=0,
            visible=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            animate=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
        )
    ], spacing=20, expand=True)


    # --- Trimmer UI ---
    trim_input_field = ft.Ref[ft.TextField]()
    trim_output_field = ft.Ref[ft.TextField]()
    trim_placeholder_img = ft.Ref[ft.Image]()
    trim_processing_overlay = ft.Ref[ft.Container]()
    trim_processing_gif = ft.Ref[ft.Image]()

    # Use file-based pathing instead of Base64
    gif_filename = "processing_transparent.gif"
    
    trim_file_paths = []
    trim_target_path = None
    trim_is_running = False
    trim_video_duration = 0  # Total duration in seconds
    
    # Trim segments data structure: list of dicts with start, end
    trim_segments = []
    trim_segments_list = ft.Ref[ft.Column]()
    trim_preview_container = ft.Ref[ft.Container]()
    trim_player_container = ft.Ref[ft.Container]()
    trim_video_player = ft.Ref()

    def duration_to_sec(d):
        """Convert Flet Duration or timedelta to seconds"""
        if d is None: return 0
        if hasattr(d, "total_seconds"):
            return d.total_seconds()
        try:
            h = getattr(d, "hours", 0)
            m = getattr(d, "minutes", 0)
            s = getattr(d, "seconds", 0)
            ms = getattr(d, "milliseconds", 0)
            mic = getattr(d, "microseconds", 0)
            return float(h * 3600 + m * 60 + s + ms / 1000.0 + mic / 1000000.0)
        except:
            return 0

    def format_time(seconds):
        """Convert seconds to HH:MM:SS.mmm format"""
        try:
            seconds = float(seconds)
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = seconds % 60
            return f"{h:02d}:{m:02d}:{s:06.3f}"
        except:
            return "00:00:00.000"

    def time_to_sec(t):
        """Convert time string (HH:MM:SS or MM:SS or seconds) to seconds"""
        try:
            if not t: return 0.0
            t = str(t).strip()
            parts = t.split(":")
            if len(parts) == 3: 
                return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
            if len(parts) == 2: 
                return float(parts[0])*60 + float(parts[1])
            return float(t)
        except: 
            return 0.0

    def build_segment_card(seg_idx):
        """Build a single segment card UI"""
        seg = trim_segments[seg_idx]
        
        start_field = ft.TextField(
            value=seg.get("start", ""),
            label="Trim Start",
            hint_text="00:00:00",
            width=120,
            text_size=13,
            border_radius=8,
            content_padding=8,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
            on_blur=lambda e, idx=seg_idx: on_segment_time_change(idx, "start", e.control.value)
        )
        
        end_field = ft.TextField(
            value=seg.get("end", ""),
            label="Trim End",
            hint_text="00:00:00",
            width=120,
            text_size=13,
            border_radius=8,
            content_padding=8,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
            on_blur=lambda e, idx=seg_idx: on_segment_time_change(idx, "end", e.control.value)
        )
        
        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_ROUNDED,
            icon_color=ft.Colors.RED_400,
            icon_size=20,
            tooltip="Delete segment",
            on_click=lambda _, idx=seg_idx: delete_segment(idx)
        )
        
        async def grab_time(field_name):
            if trim_video_player.current:
                try:
                    res = trim_video_player.current.get_current_position()
                    if asyncio.iscoroutine(res):
                        pos = await res
                    else:
                        pos = res
                    
                    sec = duration_to_sec(pos)
                    trim_segments[seg_idx][field_name] = format_time(sec)
                    rebuild_segments_list()
                    check_and_generate_preview()
                except:
                    pass

        # Main content row with number, fields, and delete
        content_row = ft.Row([
            # Segment number
            ft.Container(
                content=ft.Text(str(seg_idx + 1), size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                width=30,
                alignment=ft.Alignment.CENTER,
            ),
            # Time fields
            ft.Column([
                ft.Row([
                    start_field,
                    ft.IconButton(ft.Icons.ACCESS_TIME_ROUNDED, icon_size=16, tooltip="Set to current position", 
                                  on_click=lambda _: page.run_task(grab_time, "start")),
                ], spacing=0),
            ], spacing=0),
            ft.Column([
                ft.Row([
                    end_field,
                    ft.IconButton(ft.Icons.ACCESS_TIME_ROUNDED, icon_size=16, tooltip="Set to current position", 
                                  on_click=lambda _: page.run_task(grab_time, "end")),
                ], spacing=0),
            ], spacing=0),
            ft.Container(expand=True),
            delete_btn
        ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=5)
        
        return ft.Container(
            content=content_row,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            padding=15,
            margin=ft.Margin.only(bottom=10),
            animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT)
        )

    def rebuild_segments_list():
        """Rebuild the entire segments list UI"""
        if not trim_segments_list.current:
            return
        
        controls = []
        for idx in range(len(trim_segments)):
            controls.append(build_segment_card(idx))
        
        # Show placeholder if empty
        if len(trim_segments) == 0:
            controls.append(
                ft.Container(
                    content=ft.Text("Click + to add trim segments", size=14, color=ft.Colors.ON_SURFACE_VARIANT, italic=True),
                    alignment=ft.Alignment.CENTER,
                    padding=30
                )
            )
        
        trim_segments_list.current.controls = controls
        trim_segments_list.current.update()

    def add_segment(_=None):
        """Add a new trim segment"""
        new_seg = {
            "start": "",
            "end": ""
        }
        trim_segments.append(new_seg)
        rebuild_segments_list()

    def delete_segment(idx):
        """Delete a segment by index"""
        if 0 <= idx < len(trim_segments):
            trim_segments.pop(idx)
            rebuild_segments_list()
            # Check if we should update preview after deletion
            check_and_generate_preview()

    def on_segment_time_change(idx, field, value):
        """Handle time field changes on blur - safe to rebuild since user finished editing"""
        if 0 <= idx < len(trim_segments):
            trim_segments[idx][field] = value
            rebuild_segments_list()
            # Check if all fields are filled and generate preview
            check_and_generate_preview()



    def are_all_segments_filled():
        """Check if all segments have both start and end times filled"""
        if not trim_segments or not trim_file_paths:
            return False
        for seg in trim_segments:
            start = seg.get("start", "").strip()
            end = seg.get("end", "").strip()
            if not start or not end:
                return False
        return True

    def check_and_generate_preview():
        """No longer generates a preview - just a placeholder for the old function"""
        pass  # Preview now works by monitoring playback position

    # --- Smart Preview System ---
    # Instead of generating a preview video, we:
    # 1. Load the original video in the player
    # 2. Monitor playback position
    # 3. When playback enters a trim segment (to be removed), skip to the segment's end
    
    trim_preview_monitoring = False  # Flag for the monitoring thread
    trim_last_skip_time = 0  # Prevent rapid repeated skips
    
    def is_position_in_trim_segment(position_seconds):
        """Check if the current position is within a trim segment (to be cut)"""
        for seg in trim_segments:
            start_str = seg.get("start", "").strip()
            end_str = seg.get("end", "").strip()
            if not start_str or not end_str:
                continue
            
            start_sec = time_to_sec(start_str)
            end_sec = time_to_sec(end_str)
            
            if start_sec <= position_seconds < end_sec:
                return True, end_sec  # Return True and the end position to skip to
        
        return False, 0
    async def monitor_preview_loop():
        """Polls video position to handle smart skipping"""
        nonlocal trim_last_skip_time
        last_log_time = 0
        
        while True:
            await asyncio.sleep(0.05)
            try:
                # Stop monitoring if not on Trimmer tab
                if current_tab != "trimmer":
                    await asyncio.sleep(1)
                    continue

                if not trim_video_player.current:
                    await asyncio.sleep(1)
                    continue
                
                # Check known property names for different flet_video versions
                player = trim_video_player.current
                position_raw = None
                
                if hasattr(player, "get_current_position"):
                    # Method is likely async if player is async-compatible
                    res = player.get_current_position()
                    if asyncio.iscoroutine(res):
                        position_raw = await res
                    else:
                        position_raw = res
                elif hasattr(player, "position"):
                    position_raw = player.position
                elif hasattr(player, "current_position"):
                    position_raw = player.current_position
                    
                if position_raw is None:
                    continue
                
                # Convert to seconds handling various types
                current_sec = 0.0
                try:
                    if hasattr(position_raw, "total_seconds"): # datetime.timedelta
                        current_sec = position_raw.total_seconds()
                    elif type(position_raw).__name__ == "Duration": # Flet Duration
                         # Calculate manually from attributes
                         h = getattr(position_raw, "hours", 0)
                         m = getattr(position_raw, "minutes", 0)
                         s = getattr(position_raw, "seconds", 0)
                         ms = getattr(position_raw, "milliseconds", 0)
                         mic = getattr(position_raw, "microseconds", 0)
                         current_sec = (h * 3600) + (m * 60) + s + (ms / 1000.0) + (mic / 1000000.0)
                    elif isinstance(position_raw, (int, float)):
                        current_sec = position_raw / 1000.0 # user provided ms
                    elif isinstance(position_raw, str):
                        if ":" in position_raw:
                            current_sec = time_to_sec(position_raw)
                        else:
                            current_sec = float(position_raw) / 1000.0
                except:
                    pass
                




                # Check segment
                in_segment, skip_to_sec = is_position_in_trim_segment(current_sec)
                
                if in_segment:
                    now = time.time()
                    if now - trim_last_skip_time < 0.5: continue
                    trim_last_skip_time = now
                    
                    log(f"⏭️ Skipping trim segment: {current_sec:.1f}s -> {skip_to_sec:.1f}s")

                    # Seek
                    skip_to_ms = int(skip_to_sec * 1000)
                    if hasattr(player, "seek"):
                        res = player.seek(skip_to_ms)
                        if asyncio.iscoroutine(res): await res
                    elif hasattr(player, "jump_to"):
                        res = player.jump_to(skip_to_ms)
                        if asyncio.iscoroutine(res): await res
                        
            except Exception as e:
                # print(f"Monitor error: {e}")
                pass



    def on_trim_video_position_change(e):
        """Fallback callback if on_position_changed works in future"""
        try:
            # Re-use logic if event data provides position
            pass 
        except: pass
    
    async def load_video_for_preview():
        """Load the input video into the preview player"""
        if not trim_file_paths or not trim_player_container.current:
            return
        
        input_path = trim_file_paths[0]
        log(f"📽️ Loading video for preview: {os.path.basename(input_path)}")
        
        # Create VideoMedia and load into player
        try:
             # Create new video control
            media = VideoMedia(input_path)
            
            # Hide placeholder with fade
            if trim_placeholder_img.current:
                trim_placeholder_img.current.opacity = 0
                trim_placeholder_img.current.update()

            # Replace the Video control in the stack
            if trim_player_container.current and isinstance(trim_player_container.current.content, ft.Stack):
                stack = trim_player_container.current.content
                
                # The video player container is the 2nd element in our stack
                new_player = Video(
                    ref=trim_video_player,
                    expand=True,
                    autoplay=False,
                    playlist=[media],
                    playlist_mode=PlaylistMode.SINGLE,
                    aspect_ratio=16/9,
                    volume=100,
                    filter_quality=ft.FilterQuality.HIGH,
                )
                
                # Wrap in container for alignment and fade
                video_container = ft.Container(
                    content=new_player,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                    opacity=0,
                    animate_opacity=400
                )
                
                # Replace the middle layer (index 1)
                stack.controls[1] = video_container
                trim_player_container.current.update()
                
                # Small wait to ensure Flet registers the 0 opacity state
                await asyncio.sleep(0.05)
                
                # Fade in video
                video_container.opacity = 1
                video_container.update()
            
        except Exception as ex:
            log(f"Error loading video: {ex}")

    def stop_trimming(e):
        nonlocal trim_is_running
        trim_stop_event.set()
        trim_is_running = False
        if trim_stop_btn.current:
            trim_stop_btn.current.disabled = True
            trim_stop_btn.current.update()
        log("🛑 Stopping trim...")

    async def run_trimming():
        nonlocal trim_is_running
        trim_stop_event.clear()
        
        if not trim_file_paths or not trim_target_path:
            return
        if len(trim_segments) == 0:
            show_error("No segments", "Please add at least one segment to remove.")
            return
        
        trim_is_running = True
        if trim_stop_btn.current:
            trim_stop_btn.current.disabled = False
            trim_stop_btn.current.update()
        input_path = trim_file_paths[0]
        output_path = trim_target_path
        
        # Show processing overlay with fade
        if trim_processing_overlay.current:
            trim_processing_overlay.current.visible = True
            trim_processing_overlay.current.opacity = 0
            trim_processing_overlay.current.update()
            
            # small delay to ensure visibility is registered before opacity change
            await asyncio.sleep(0.05) 
            trim_processing_overlay.current.opacity = 1
            trim_processing_overlay.current.update()
        
        # Pause Video
        if trim_video_player.current:
            async def pause_p():
                if trim_video_player.current:
                    await trim_video_player.current.pause()
            page.run_task(pause_p)

        def trim_thread():
            nonlocal trim_is_running
            try:
                log(f"\n✂️ Removing segments from: {os.path.basename(input_path)}")
                
                # Get video duration
                duration = trim_video_duration if trim_video_duration else get_video_duration(input_path)
                if not duration:
                    show_error("Error", "Could not determine video duration")
                    return
                
                # Sort segments by start time numerically
                sorted_segments = sorted(trim_segments, key=lambda s: time_to_sec(s.get("start", "0")))
                
                # Build list of segments to KEEP (inverse of segments to remove)
                keep_segments = []
                current_time_sec = 0.0
                
                for seg in sorted_segments:
                    seg_start_sec = time_to_sec(seg.get("start", "0"))
                    seg_end_sec = time_to_sec(seg.get("end", ""))
                    
                    if not seg_end_sec: continue
                    
                    # If there's a gap before this segment, keep it
                    if seg_start_sec > current_time_sec:
                        keep_segments.append({"start": format_time(current_time_sec), "end": format_time(seg_start_sec)})
                    
                    # Move current time to end of removed segment
                    if seg_end_sec > current_time_sec:
                        current_time_sec = seg_end_sec
                
                # Keep everything from last removed segment to end of video
                if current_time_sec < duration:
                    keep_segments.append({"start": format_time(current_time_sec), "end": format_time(duration)})
                
                if len(keep_segments) == 0:
                    show_error("Error", "All segments would be removed. Nothing to output.")
                    return
                
                log(f"  Keeping {len(keep_segments)} segment(s), removing {len(sorted_segments)} segment(s)")
                
                # Extract segments to keep
                temp_files = []
                base_dir = os.path.dirname(output_path) if output_path else os.getcwd()
                
                for idx, seg in enumerate(keep_segments):
                    if trim_stop_event.is_set():
                        log("🛑 Trim cancelled.")
                        # Clean up
                        for tf in temp_files:
                            try: os.remove(tf)
                            except: pass
                        return

                    start_time = seg["start"]
                    end_time = seg["end"]
                    temp_out = os.path.join(base_dir, f"_keep_temp_{idx}.mp4")
                    temp_files.append(temp_out)
                    
                    # Use stream copy for speed (no re-encoding)
                    cmd = ["ffmpeg", "-y", "-ss", start_time, "-to", end_time, "-i", input_path, 
                           "-c", "copy", "-avoid_negative_ts", "make_zero", temp_out]
                    
                    log(f"  Extracting segment {idx + 1}/{len(keep_segments)}...")
                    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
                    if result.returncode != 0:
                        log(f"  Warning: Segment {idx + 1} extraction had issues")
                
                # Concatenate kept segments
                if len(temp_files) == 1:
                    # Only one segment, just rename it
                    import shutil
                    shutil.move(temp_files[0], output_path)
                    log(f"✅ Success! Saved to: {os.path.basename(output_path)}")
                    show_success(f"Removed {len(sorted_segments)} segment(s) successfully!")
                    play_complete_ding()
                    if user_settings.get("auto_open_folder"):
                        open_folder(output_path)
                else:
                    # Multiple segments, concatenate them
                    concat_file = os.path.join(base_dir, "_concat_list.txt")
                    with open(concat_file, "w") as f:
                        for tf in temp_files:
                            f.write(f"file '{os.path.basename(tf)}'\n")
                    
                    log(f"  Concatenating {len(temp_files)} segments...")
                    concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, 
                                  "-c", "copy", output_path]
                    result = subprocess.run(concat_cmd, capture_output=True, text=True, cwd=base_dir, creationflags=SUBPROCESS_FLAGS)
                    
                    # Cleanup
                    for tf in temp_files:
                        try: os.remove(tf)
                        except: pass
                    try: os.remove(concat_file)
                    except: pass
                    
                    if result.returncode == 0:
                        log(f"✅ Success! Saved to: {os.path.basename(output_path)}")
                        show_success(f"Removed {len(sorted_segments)} segment(s) successfully!")
                        play_complete_ding()
                        if user_settings.get("auto_open_folder"):
                            open_folder(output_path)
                    else:
                        show_error("Concat failed", result.stderr)
                        log(f"❌ Failed: {result.stderr}")
                        
            except Exception as ex:
                import traceback
                show_error("Error", f"{str(ex)}\n\n{traceback.format_exc()}")
                log(f"❌ Error: {ex}")
            finally:
                trim_is_running = False
                if trim_stop_btn.current:
                    trim_stop_btn.current.disabled = True
                    trim_stop_btn.current.update()
                
                # Hide processing overlay with fade
                if trim_processing_overlay.current:
                    trim_processing_overlay.current.opacity = 0
                    trim_processing_overlay.current.update()
                    # Wait for fade then hide to allow clicks through
                    def hide_overlay():
                        time.sleep(0.4)
                        if trim_processing_overlay.current:
                            trim_processing_overlay.current.visible = False
                            trim_processing_overlay.current.update()
                    threading.Thread(target=hide_overlay, daemon=True).start()
                
                # Show placeholder with fade
                if trim_placeholder_img.current:
                    trim_placeholder_img.current.opacity = 1
                    trim_placeholder_img.current.update()
                
                # Hide video player area with fade
                if trim_player_container.current and isinstance(trim_player_container.current.content, ft.Stack):
                    stack = trim_player_container.current.content
                    # Hide the video layer (index 1)
                    if len(stack.controls) > 1:
                        stack.controls[1].opacity = 0
                        stack.controls[1].update()
                
                # Direct fallback for the player control
                if trim_video_player.current:
                    trim_video_player.current.opacity = 0
                    trim_video_player.current.update()
                
                page.update()
        
        threading.Thread(target=trim_thread, daemon=True).start()

    def get_video_duration(path):
        """Get video duration using ffprobe"""
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
                   "-of", "default=noprint_wrappers=1:nokey=1", path]
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
            return float(result.stdout.strip())
        except:
            return 0.0

    async def on_trim_pick(files):
        nonlocal trim_file_paths, trim_video_duration, trim_target_path
        if files and len(files) > 0:
            # Only take the first file
            trim_file_paths = [files[0].path]
            trim_input_field.current.value = os.path.basename(trim_file_paths[0])
            trim_input_field.current.update()
            
            # Auto-set output
            base, ext = os.path.splitext(trim_file_paths[0])
            trim_target_path = f"{base}_trimmed{ext}"
            trim_output_field.current.value = os.path.basename(trim_target_path)
            trim_output_field.current.update()
            
            # Get duration
            trim_video_duration = get_video_duration(trim_file_paths[0])
            await load_video_for_preview()
            page.update()

    async def trim_pick_click(e):
        await on_trim_pick(await trim_picker.pick_files(allow_multiple=False))

    async def trim_output_click(e):
        nonlocal trim_target_path
        path = await trim_save_picker.save_file(file_name="trimmed.mp4")
        if path:
            trim_target_path = path
            trim_output_field.current.value = os.path.basename(path)
            page.update()

    trim_picker = ft.FilePicker()
    trim_save_picker = ft.FilePicker()
    # page.overlay.extend([
    #     file_picker, output_file_picker, output_folder_picker,
    #     conv_picker, conv_dir_picker, conv_save_picker, conv_out_dir_picker,
    #     trim_picker, trim_save_picker
    # ])

    trim_file_section = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.FilledButton(
                    "File", 
                    icon=ft.Icons.ATTACH_FILE_ROUNDED, 
                    on_click=trim_pick_click,
                    style=ft.ButtonStyle(
                        padding=10, 
                        shape=ft.RoundedRectangleBorder(radius=30),
                        bgcolor=ft.Colors.PRIMARY, 
                        color=ft.Colors.ON_PRIMARY
                    )
                ),
                ft.Container(expand=True),
                ft.FilledButton(
                    "Choose", 
                    icon=ft.Icons.DOWNLOAD_ROUNDED, 
                    on_click=trim_output_click, 
                    style=ft.ButtonStyle(
                        padding=10, 
                        shape=ft.RoundedRectangleBorder(radius=30),
                        bgcolor=ft.Colors.PRIMARY, 
                        color=ft.Colors.ON_PRIMARY
                    )
                )
            ], spacing=5),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.Row([
                ft.Container(
                    content=ft.TextField(
                        ref=trim_input_field, 
                        label="Input", 
                        read_only=True, 
                        border_color=ft.Colors.OUTLINE, 
                        border_radius=12, 
                        text_size=14, 
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        height=40,
                        content_padding=10
                    ), 
                    expand=True
                ),
                ft.Container(
                    content=ft.TextField(
                        ref=trim_output_field, 
                        label="Output", 
                        read_only=True, 
                        border_color=ft.Colors.OUTLINE, 
                        border_radius=12, 
                        text_size=14, 
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        height=40,
                        content_padding=10
                    ), 
                    expand=True
                )
            ], spacing=10)
        ]),
        padding=0, 
        margin=ft.Margin.only(bottom=5)
    )

    # Trim Segments Section
    trim_segments_header = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.CONTENT_CUT_ROUNDED, color=ft.Colors.PRIMARY, size=20),
            ft.Text("Trim Segments", size=16, weight=ft.FontWeight.W_900),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_ROUNDED,
                icon_color=ft.Colors.PRIMARY,
                icon_size=24,
                tooltip="Add new segment",
                on_click=add_segment
            )
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(bottom=5)
    )

    trim_segments_scrollable = ft.Container(
        content=ft.Column(
            ref=trim_segments_list,
            controls=[
                ft.Container(
                    content=ft.Text("Click + to add trim segments", size=14, color=ft.Colors.ON_SURFACE_VARIANT, italic=True),
                    alignment=ft.Alignment.CENTER,
                    padding=30
                )
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        ),
        expand=True,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=15,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        padding=15,
    )

    trim_left_side = ft.Container(
        content=ft.Column([
            trim_segments_header,
            trim_segments_scrollable
        ], expand=True),
        expand=True
    )

    # Preview side - uses Video player for trimmed preview

    trim_preview_side = ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=15,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        padding=15,
        width=400,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, size=20, color=ft.Colors.PRIMARY),
                ft.Text("Preview", size=18, weight=ft.FontWeight.W_900),

            ], spacing=10),
            ft.Divider(color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                ref=trim_player_container,
                content=ft.Stack([
                    # Placeholder layer
                    ft.Container(
                        ref=trim_placeholder_img,
                        content=ft.Image(
                            src="placeholder.png",
                            fit=ft.BoxFit.COVER,
                            expand=True,
                        ),
                        opacity=1,
                        animate_opacity=400,
                        alignment=ft.Alignment.CENTER,
                        expand=True
                    ),
                    # Video Player layer
                    ft.Container(
                        content=Video(
                            ref=trim_video_player,
                            expand=True,
                            autoplay=False,
                            playlist=[], # Start empty
                            playlist_mode=PlaylistMode.SINGLE,
                            aspect_ratio=16/9,
                            volume=100,
                            filter_quality=ft.FilterQuality.HIGH,
                            opacity=0 # Hidden initially
                        ),
                        alignment=ft.Alignment.CENTER,
                        expand=True
                    ),
                    # Processing Overlay layer
                    ft.Container(
                        ref=trim_processing_overlay,
                        bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.SURFACE_CONTAINER_HIGHEST),
                        blur=15,
                        border_radius=10,
                        opacity=0,
                        visible=False,
                        animate_opacity=400,
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                        content=ft.Image(
                            ref=trim_processing_gif,
                            src=gif_filename,
                            width=70,
                            height=70,
                            fit=ft.BoxFit.CONTAIN
                        )
                    )
                ], expand=True, alignment=ft.Alignment.CENTER),
                alignment=ft.Alignment.CENTER, 
                expand=True, 
                bgcolor=ft.Colors.TRANSPARENT,
                border_radius=12,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS
            )
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
    )

    trim_content_row = ft.Row([
        trim_left_side,
        ft.Container(
            ref=trim_preview_container,
            content=trim_preview_side,
            width=400,
            visible=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
    ], spacing=20, expand=True)

    trim_save_btn = ft.Ref[ft.FilledButton]()

    trim_controls_row = ft.Row([
        ft.FilledButton(
            ref=trim_save_btn,
            content=ft.Row([
                ft.Icon(ft.Icons.SAVE_ROUNDED), 
                ft.Text("Save Trimmed Video", size=16, weight=ft.FontWeight.W_900)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10), 
            on_click=lambda _: page.run_task(run_trimming), 
            expand=True, 
            style=ft.ButtonStyle(
                padding=15, 
                shape=ft.RoundedRectangleBorder(radius=10),
                bgcolor={ft.ControlState.DEFAULT: ft.Colors.PRIMARY}, 
                color={ft.ControlState.DEFAULT: ft.Colors.ON_PRIMARY}
            )
        ),
        ft.OutlinedButton(
            ref=trim_stop_btn,
            content="Stop",
            icon=ft.Icons.STOP_CIRCLE_OUTLINED,
            style=ft.ButtonStyle(
                padding=15,
                color={ft.ControlState.DEFAULT: ft.Colors.RED_400},
                shape=ft.RoundedRectangleBorder(radius=10),
                side={ft.ControlState.DEFAULT: ft.BorderSide(1, ft.Colors.RED_400)}
            ), 
            on_click=stop_trimming, 
            disabled=True
        )
    ], spacing=15)

    converter_view_col = ft.Column([
        conv_file_section,
        conv_settings_card,
        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
        conv_content_row,
        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
        conv_controls_row
    ], 
    visible=True, 
    expand=True,
    offset=ft.Offset(1, 0),
    animate_offset=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
)

    trimmer_view_col = ft.Column([
        trim_file_section,
        ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
        trim_content_row,
        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
        trim_controls_row
    ], 
    visible=True, 
    expand=True,
    offset=ft.Offset(2, 0),
    animate_offset=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
)

    # --- Merger UI (Implementation) ---
    merger_segments = []
    merger_target_path = None
    
    merger_picker = ft.FilePicker()
    merger_save_picker = ft.FilePicker()

    async def pick_merger_file(idx):
        res = await merger_picker.pick_files(allow_multiple=False)
        if res and len(res) > 0:
            merger_segments[idx]["path"] = res[0].path
            rebuild_merger_segments_list()

    def delete_merger_segment(idx):
        if 0 <= idx < len(merger_segments):
            merger_segments.pop(idx)
            rebuild_merger_segments_list()

    def move_merger_segment(idx, direction):
        new_idx = idx + direction
        if 0 <= new_idx < len(merger_segments):
            merger_segments[idx], merger_segments[new_idx] = merger_segments[new_idx], merger_segments[idx]
            rebuild_merger_segments_list()

    async def play_merger_segment(idx):
        if not merger_segments or idx >= len(merger_segments): return
        path = merger_segments[idx].get("path")
        if not path or not os.path.exists(path): return
        
        # merger_log(f"📽️ Loading segment preview: {os.path.basename(path)}")
        
        try:
            # Hide placeholder
            if merger_placeholder_img.current:
                merger_placeholder_img.current.opacity = 0
                merger_placeholder_img.current.update()
                
            # Replacing Video control (mirroring Trimmer strategy)
            if merger_player_container.current and isinstance(merger_player_container.current.content, ft.Stack):
                stack = merger_player_container.current.content
                
                # Create fresh Video control
                new_player = Video(
                    ref=merger_video_player,
                    expand=True,
                    autoplay=True,
                    playlist=[VideoMedia(path)],
                    playlist_mode=PlaylistMode.SINGLE,
                    aspect_ratio=16/9,
                    volume=100,
                    filter_quality=ft.FilterQuality.HIGH,
                )
                
                video_container = ft.Container(
                    content=new_player,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                    opacity=0,
                    animate_opacity=400
                )
                
                # Replace the player layer (index 1)
                stack.controls[1] = video_container
                merger_player_container.current.update()
                
                await asyncio.sleep(0.05)
                video_container.opacity = 1
                video_container.update()

        except Exception as ex:
            merger_log(f"❌ Preview Error: {ex}")

    merger_stop_event = threading.Event()

    def stop_merger(e):
        merger_stop_event.set()
        if merger_stop_btn.current:
            merger_stop_btn.current.disabled = True
            merger_stop_btn.current.update()
        merger_log("🛑 Stopping merge...")

    async def run_merger(e):
        if not merger_segments:
            merger_log("❌ Merge Queue is empty!")
            return
            
        # Validate all segments have paths
        video_paths = [s["path"] for s in merger_segments if s.get("path")]
        if len(video_paths) < len(merger_segments):
            merger_log("❌ Some segments are missing files!")
            return

        if not merger_target_path:
            # Prompt to choose output
            await merger_output_click(None)
            if not merger_target_path: return

        # Log and start
        merger_log("🎬 Starting Merger...")
        
        merger_stop_event.clear()
        
        # Show progress wrapper
        if merger_progress_wrapper.current:
            merger_progress_wrapper.current.height = 75
            merger_progress_wrapper.current.opacity = 1
            merger_progress_wrapper.current.update()
        
        btn = e.control
        btn.disabled = True
        btn.update()
        
        if merger_stop_btn.current:
            merger_stop_btn.current.disabled = False
            merger_stop_btn.current.update()
        
        # Reset progress bar
        update_merger_progress_bar(0)
        
        nonlocal merger_start_time
        merger_start_time = time.time()
        
        def do_merge():
            try:
                success, result = logic.merge_videos(video_paths, merger_target_path, merger_log, stop_event=merger_stop_event)
                if success:
                    merger_log(f"✨ MERGE SUCCESS: {result}")
                    play_complete_ding()
                    if user_settings.get("auto_open_folder"):
                        open_folder(merger_target_path)
                else:
                    merger_log(f"❌ MERGE FAILED: {result}")
            finally:
                btn.disabled = False
                btn.update()
                if merger_stop_btn.current:
                    merger_stop_btn.current.disabled = True
                    merger_stop_btn.current.update()
                
                # Hide progress wrapper after delay
                def hide_progress():
                    time.sleep(3.0)
                    if merger_progress_wrapper.current:
                        merger_progress_wrapper.current.opacity = 0
                        merger_progress_wrapper.current.height = 0
                        merger_progress_wrapper.current.update()
                threading.Thread(target=hide_progress, daemon=True).start()
            
        threading.Thread(target=do_merge, daemon=True).start()

    merger_total_duration = 0 # Store total duration of all segments
    merger_start_time = 0

    def merger_log(msg, replace_last=False):
        # Check if this is a progress line
        if "time=" in msg and "frame=" in msg:
            # Parse time
             try:
                import re
                match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", msg)
                if match and merger_total_duration > 0:
                    t_str = match.group(1)
                    parts = t_str.split(':')
                    secs = float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
                    
                    pct = 0
                    if merger_total_duration > 0:
                        pct = min(secs / merger_total_duration, 1.0)
                    
                    update_merger_progress_bar(pct)
                    
                    # Update percentage text
                    if merger_pct_text.current:
                        merger_pct_text.current.value = f"{int(pct*100)}%"
                        merger_pct_text.current.update()
                    
                    # Update time remaining text
                    if merger_status_text.current:
                        eta_str = "---"
                        if pct > 0.01 and merger_start_time > 0: # Wait for 1% progress for better estimate
                            elapsed = time.time() - merger_start_time
                            total_est = elapsed / pct
                            remaining = total_est - elapsed
                            if remaining < 0: remaining = 0
                            
                            m, s = divmod(int(remaining), 60)
                            h, m = divmod(m, 60)
                            if h > 0:
                                eta_str = f"{h:02d}:{m:02d}:{s:02d}"
                            else:
                                eta_str = f"{m:02d}:{s:02d}"
                        
                        merger_status_text.current.value = eta_str
                        merger_status_text.current.update()
             except: pass
        else:
            # For non-progress messages, show in status text only if it's a user message
            if "frame=" not in msg:
                print(msg)

    def build_merger_card(idx):
        seg = merger_segments[idx]
        file_path = seg.get("path", "")
        file_name = os.path.basename(file_path) if file_path else "No file selected"
        
        return ft.Container(
            content=ft.Row([
                ft.Text(str(idx + 1), size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY, width=30),
                ft.Row([
                    ft.Icon(ft.Icons.VIDEO_FILE_ROUNDED, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(file_name, size=14, weight=ft.FontWeight.W_500, expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                ], expand=True, spacing=10),
                ft.Row([
                    ft.IconButton(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, icon_size=18, tooltip="Preview", on_click=lambda _: page.run_task(play_merger_segment, idx)),
                    ft.IconButton(ft.Icons.FOLDER_OPEN_ROUNDED, icon_size=18, tooltip="Change file", on_click=lambda _: page.run_task(pick_merger_file, idx)),
                    ft.IconButton(ft.Icons.ARROW_UPWARD_ROUNDED, icon_size=18, tooltip="Move up", on_click=lambda _: move_merger_segment(idx, -1), disabled=(idx == 0)),
                    ft.IconButton(ft.Icons.ARROW_DOWNWARD_ROUNDED, icon_size=18, tooltip="Move down", on_click=lambda _: move_merger_segment(idx, 1), disabled=(idx == len(merger_segments)-1)),
                    ft.IconButton(ft.Icons.DELETE_ROUNDED, icon_size=18, icon_color=ft.Colors.RED_400, tooltip="Remove", on_click=lambda _: delete_merger_segment(idx)),
                ], spacing=0)
            ], alignment=ft.MainAxisAlignment.START),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            padding=ft.Padding(left=15, right=5, top=5, bottom=5),
            margin=ft.Margin.only(bottom=8),
            animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT)
        )

    def rebuild_merger_segments_list():
        if not merger_segments_list.current: return
        
        # Calculate total duration
        nonlocal merger_total_duration
        merger_total_duration = 0
        for seg in merger_segments:
            p = seg.get("path")
            if p and os.path.exists(p):
                merger_total_duration += logic.get_video_duration(p)

        controls = []
        for idx in range(len(merger_segments)):
            controls.append(build_merger_card(idx))
        if len(merger_segments) == 0:
            controls.append(ft.Container(content=ft.Text("Click + to add videos to merge", size=14, color=ft.Colors.ON_SURFACE_VARIANT, italic=True), alignment=ft.Alignment.CENTER, padding=30))
        merger_segments_list.current.controls = controls
        merger_segments_list.current.update()

    async def add_merger_segment(_=None):
        res = await merger_picker.pick_files(allow_multiple=True)
        if res:
            for f in res:
                merger_segments.append({"path": f.path})
            rebuild_merger_segments_list()

    async def merger_output_click(e):
        path = await merger_save_picker.save_file(file_name="merged.mp4")
        if path:
            nonlocal merger_target_path
            merger_target_path = path
            merger_output_field.current.value = os.path.basename(path)
            merger_output_field.current.update()

    # --- Merger UI Layout ---
    merger_file_section = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Container(expand=True),
                ft.FilledButton(
                    "Choose", 
                    icon=ft.Icons.DOWNLOAD_ROUNDED, 
                    on_click=merger_output_click, 
                    style=ft.ButtonStyle(
                        padding=10, 
                        shape=ft.RoundedRectangleBorder(radius=30),
                        bgcolor=ft.Colors.PRIMARY, 
                        color=ft.Colors.ON_PRIMARY
                    )
                )
            ], spacing=5),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.Row([
                ft.Container(
                    content=ft.TextField(
                        ref=merger_output_field, 
                        label="Output", 
                        read_only=True, 
                        border_color=ft.Colors.OUTLINE, 
                        border_radius=12, 
                        text_size=14, 
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        height=40,
                        content_padding=10
                    ), 
                    expand=True
                )
            ], spacing=10)
        ]),
        padding=0, 
        margin=ft.Margin.only(bottom=5)
    )

    merger_segments_scrollable = ft.Container(
        content=ft.Column(ref=merger_segments_list, controls=[ft.Container(content=ft.Text("Click + to add videos to merge", size=14, color=ft.Colors.ON_SURFACE_VARIANT, italic=True), alignment=ft.Alignment.CENTER, padding=30)], scroll=ft.ScrollMode.AUTO),
        expand=True, bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE), border_radius=15, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), padding=15
    )

    merger_left_side = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.VIDEO_LIBRARY_ROUNDED, color=ft.Colors.PRIMARY, size=20), 
                    ft.Text("Videos to Merge", size=16, weight=ft.FontWeight.W_900), 
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.ADD_CIRCLE_ROUNDED,
                        icon_color=ft.Colors.PRIMARY,
                        icon_size=24,
                        tooltip="Add Video(s)",
                        on_click=add_merger_segment
                    )
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER), 
                padding=ft.Padding.only(bottom=10)
            ),
            merger_segments_scrollable,
            ft.Container(
                content=ft.Column([
                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    ft.Row([
                        ft.Text("Time remaining : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("---", ref=merger_status_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                        ft.VerticalDivider(width=20, color=ft.Colors.TRANSPARENT),
                        ft.Text("Percentage : ", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("0%", ref=merger_pct_text, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                    ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(
                        ref=merger_progress_container,
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                        height=6,
                        border_radius=3,
                        alignment=ft.Alignment.CENTER_LEFT,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        content=ft.Container(
                            ref=merger_progress_fill,
                            width=0,
                            bgcolor=ft.Colors.PRIMARY,
                            height=6,
                            animate=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
                        )
                    )
                ], spacing=10),
                ref=merger_progress_wrapper,
                opacity=0, 
                height=0,
                animate_opacity=ft.Animation(400, ft.AnimationCurve.EASE_OUT),
                animate=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO),
                clip_behavior=ft.ClipBehavior.HARD_EDGE
            )
        ], expand=True),
        expand=True
    )

    merger_preview_side = ft.Container(
        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE), 
        border_radius=15, 
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), 
        padding=15, 
        width=400, 
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Column([
            ft.Row([ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, size=20, color=ft.Colors.PRIMARY), ft.Text("Preview", size=18, weight=ft.FontWeight.W_900)], spacing=10),
            ft.Divider(color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                ref=merger_player_container, 
                content=ft.Stack([
                    # Placeholder
                    ft.Container(
                        ref=merger_placeholder_img, 
                        content=ft.Image(src="placeholder.png", fit=ft.BoxFit.COVER, expand=True), 
                        opacity=1, 
                        animate_opacity=400,
                        alignment=ft.Alignment.CENTER, 
                        expand=True
                    ),
                    # Video Player
                    ft.Container(
                        content=Video(
                            ref=merger_video_player,
                            expand=True,
                            autoplay=False,
                            playlist=[],
                            playlist_mode=PlaylistMode.SINGLE,
                            aspect_ratio=16/9,
                            opacity=0,
                            animate_opacity=400
                        ),
                        alignment=ft.Alignment.CENTER,
                        expand=True
                    )
                ], expand=True, alignment=ft.Alignment.CENTER), 
                expand=True, 
                bgcolor=ft.Colors.TRANSPARENT, 
                border_radius=12, 
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS
            )
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
    )

    merger_content_row = ft.Row([merger_left_side, ft.Container(ref=merger_preview_container, content=merger_preview_side, width=400, visible=True, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)], spacing=20, expand=True)

    merger_view_col = ft.Column([
        merger_file_section,
        ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
        merger_content_row,
        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
        ft.Column([
            ft.Row([
                ft.FilledButton(
                    content=ft.Row([ft.Icon(ft.Icons.MERGE_ROUNDED), ft.Text("Merge Videos", size=16, weight=ft.FontWeight.W_900)], alignment=ft.MainAxisAlignment.CENTER, spacing=10), 
                    on_click=run_merger, 
                    expand=True, 
                    style=ft.ButtonStyle(
                        padding=15, 
                        shape=ft.RoundedRectangleBorder(radius=10), 
                        bgcolor={ft.ControlState.DEFAULT: ft.Colors.PRIMARY}, 
                        color={ft.ControlState.DEFAULT: ft.Colors.ON_PRIMARY}
                    )
                ),
                ft.OutlinedButton(
                    ref=merger_stop_btn,
                    content="Stop",
                    icon=ft.Icons.STOP_CIRCLE_OUTLINED,
                    style=ft.ButtonStyle(
                        padding=15,
                        color={ft.ControlState.DEFAULT: ft.Colors.RED_400},
                        shape=ft.RoundedRectangleBorder(radius=10),
                        side={ft.ControlState.DEFAULT: ft.BorderSide(1, ft.Colors.RED_400)}
                    ), 
                    on_click=stop_merger, 
                    disabled=True
                )
            ], spacing=15)
        ], spacing=10)
    ], 
    visible=True, 
    expand=True,
    offset=ft.Offset(3, 0),
    animate_offset=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
    )

    # --- More View ---
    more_view_col = ft.Column([
        ft.Container(
            content=ft.Column([
                ft.Text("App", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                ft.Divider(height=10, thickness=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.SETTINGS_ROUNDED, size=30, color=ft.Colors.PRIMARY),
                            ft.Text("App Settings", size=14, weight=ft.FontWeight.W_600),
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        width=150,
                        height=100,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        border_radius=15,
                        alignment=ft.Alignment.CENTER,
                        ink=True,
                        on_click=lambda _: set_tab("settings"),
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.INFO_ROUNDED, size=30, color=ft.Colors.PRIMARY),
                            ft.Text("About", size=14, weight=ft.FontWeight.W_600),
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        width=150,
                        height=100,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        border_radius=15,
                        alignment=ft.Alignment.CENTER,
                        ink=True,
                        on_click=lambda _: set_tab("about"),
                    ),
                ], spacing=15, alignment=ft.MainAxisAlignment.CENTER),
                
                ft.Divider(height=40, color=ft.Colors.TRANSPARENT),
                
                # Placeholder for other sections
                ft.Icon(ft.Icons.AUTO_AWESOME_MOTION_ROUNDED, size=40, color=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE)),
                ft.Text("More tools coming soon...", size=14, color=ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE)),
                
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            padding=30,
            expand=True,
        )
    ], 
    visible=True, 
    expand=True,
    offset=ft.Offset(4, 0),
    animate_offset=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
    )

    def toggle_theme(e):
        is_dark = e.control.value
        page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        user_settings["theme_mode"] = "dark" if is_dark else "light"
        
        # Reset color seed based on standard or custom
        curr_accent = user_settings.get("accent_color", "INDIGO_ACCENT")
        page.theme.color_scheme_seed = getattr(ft.Colors, curr_accent, ft.Colors.INDIGO_ACCENT)
        
        save_settings(user_settings)
        page.update()

    def toggle_setting(key, e):
        user_settings[key] = e.control.value
        save_settings(user_settings)

    def set_accent_color(color_name):
        user_settings["accent_color"] = color_name
        page.theme.color_scheme_seed = getattr(ft.Colors, color_name)
        save_settings(user_settings)
        page.update()

    # --- Settings View ---
    setting_auto_open_switch = ft.Switch(value=user_settings.get("auto_open_folder", False), on_change=lambda e: toggle_setting("auto_open_folder", e), active_color=ft.Colors.PRIMARY)
    setting_ding_switch = ft.Switch(value=user_settings.get("play_ding", True), on_change=lambda e: toggle_setting("play_ding", e), active_color=ft.Colors.PRIMARY)

    def color_dot(color_name, real_color):
        return ft.Container(
            width=30, height=30, bgcolor=real_color, border_radius=15,
            ink=True, on_click=lambda _: set_accent_color(color_name),
            tooltip=color_name.replace("_", " ").title()
        )

    settings_view_col = ft.Column([
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.IconButton(ft.Icons.ARROW_BACK_ROUNDED, on_click=lambda _: set_tab("more"), icon_size=20),
                    ft.Text("Settings", size=20, weight=ft.FontWeight.BOLD),
                ], spacing=10),
                
                ft.Divider(height=10, thickness=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
                
                # Appearance section
                ft.Column([
                    ft.Text("Appearance", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Row([
                                    ft.Icon(ft.Icons.DARK_MODE_ROUNDED, size=20),
                                    ft.Column([
                                        ft.Text("Dark Mode", size=16, weight=ft.FontWeight.W_600),
                                        ft.Text("Switch application theme.", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ], spacing=0),
                                ], spacing=15),
                                ft.Switch(ref=setting_theme_switch, value=(user_settings.get("theme_mode")=="dark"), on_change=toggle_theme, active_color=ft.Colors.PRIMARY)
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                            ft.Text("Accent Color", size=14, weight=ft.FontWeight.W_600),
                            ft.Row([
                                color_dot("INDIGO_ACCENT", ft.Colors.INDIGO_ACCENT),
                                color_dot("BLUE", ft.Colors.BLUE),
                                color_dot("TEAL", ft.Colors.TEAL),
                                color_dot("GREEN", ft.Colors.GREEN),
                                color_dot("AMBER", ft.Colors.AMBER),
                                color_dot("DEEP_ORANGE", ft.Colors.DEEP_ORANGE),
                                color_dot("PINK", ft.Colors.PINK),
                            ], spacing=10),
                        ]),
                        padding=20, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=15,
                    ),
                ], spacing=10),

                # Behavior section
                ft.Column([
                    ft.Text("Behavior", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Row([
                                    ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=20),
                                    ft.Column([
                                        ft.Text("Auto-Open Folder", size=16, weight=ft.FontWeight.W_600),
                                        ft.Text("Open destination folder after task completion.", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ], spacing=0),
                                ], spacing=15),
                                setting_auto_open_switch
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            # Notification Sound Toggle (Enabled via playsound library)
                            ft.Row([
                                ft.Row([
                                    ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE_ROUNDED, size=20),
                                    ft.Column([
                                        ft.Text("Notification Sound", size=16, weight=ft.FontWeight.W_600),
                                        ft.Text("Play a sound when a task finishes.", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ], spacing=0),
                                ], spacing=15),
                                setting_ding_switch
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ]),
                        padding=20, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=15,
                    ),
                ], spacing=10),
                
                ft.Container(expand=True),
            ], spacing=25),
            padding=30, expand=True
        )
    ], visible=True, expand=True, offset=ft.Offset(5, 0), animate_offset=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO))

    # --- About View ---
    about_view_col = ft.Column([
        ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Image(src="Icon.svg", width=100, height=100),
                        ft.Text("Video Utilities", size=28, weight=ft.FontWeight.W_900),
                        ft.Text(f"Version {APP_VERSION}", size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Divider(height=30, color=ft.Colors.TRANSPARENT),
                        ft.Text("A premium toolset for video processing.", size=16, italic=True),
                        ft.Text("Built with Flet and FFmpeg.", size=14, color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE)),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    expand=True,
                    alignment=ft.Alignment.CENTER
                )
            ], spacing=20),
            padding=30,
            expand=True
        )
    ], 
    visible=True, 
    expand=True,
    offset=ft.Offset(6, 0),
    animate_offset=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
    )

    TAB_WIDTH = 135
    TAB_HEIGHT = 36

    def update_tabs():
        # Text Colors
        if tab_compressor_text.current:
            is_active = (current_tab == "compressor")
            c = ft.Colors.ON_PRIMARY_CONTAINER if is_active else ft.Colors.ON_SURFACE_VARIANT
            tab_compressor_text.current.color = c
            tab_compressor_icon.current.color = c
            tab_compressor_text.current.update()
            tab_compressor_icon.current.update()
            
        if tab_converter_text.current:
            is_active = (current_tab == "converter")
            c = ft.Colors.ON_PRIMARY_CONTAINER if is_active else ft.Colors.ON_SURFACE_VARIANT
            tab_converter_text.current.color = c
            tab_converter_icon.current.color = c
            tab_converter_text.current.update()
            tab_converter_icon.current.update()
        if tab_trimmer_text.current:
            is_active = (current_tab == "trimmer")
            c = ft.Colors.ON_PRIMARY_CONTAINER if is_active else ft.Colors.ON_SURFACE_VARIANT
            tab_trimmer_text.current.color = c
            tab_trimmer_icon.current.color = c
            tab_trimmer_text.current.update()
            tab_trimmer_icon.current.update()

        if tab_merger_text.current:
            is_active = (current_tab == "merger")
            c = ft.Colors.ON_PRIMARY_CONTAINER if is_active else ft.Colors.ON_SURFACE_VARIANT
            tab_merger_text.current.color = c
            tab_merger_icon.current.color = c
            tab_merger_text.current.update()
            tab_merger_icon.current.update()

        if tab_more_text.current:
            is_active = (current_tab == "more")
            c = ft.Colors.ON_PRIMARY_CONTAINER if is_active else ft.Colors.ON_SURFACE_VARIANT
            tab_more_text.current.color = c
            tab_more_icon.current.color = c
            tab_more_text.current.update()
            tab_more_icon.current.update()

    def set_tab(name):
        nonlocal current_tab
        if current_tab == name: return
        current_tab = name
        
        # Slide Indicator (Only 5 positions)
        if tab_indicator.current:
            pos_map = {
                "compressor": 0, "converter": 1, "trimmer": 2, "merger": 3, "more": 4
            }
            if name in pos_map:
                tab_indicator.current.left = TAB_WIDTH * pos_map[name]
                tab_indicator.current.opacity = 1
            else:
                # Sub-views (settings/about) - hide the indicator
                tab_indicator.current.opacity = 0
            tab_indicator.current.update()
            
        # Switch View with Animation (Full 7-slot stack)
        offsets = {
            "compressor": 0, "converter": 1, "trimmer": 2, "merger": 3, 
            "more": 4, "settings": 5, "about": 6
        }
        target_idx = offsets.get(name, 0)
        
        # Apply offsets to all views
        views = [
            compressor_view_col, converter_view_col, trimmer_view_col, 
            merger_view_col, more_view_col, settings_view_col, about_view_col
        ]
        
        for i, view in enumerate(views):
            view.offset = ft.Offset(i - target_idx, 0)
            view.update()
        
        update_tabs()

    tab_bar = ft.Container(
        bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.SURFACE_CONTAINER_HIGHEST),
        border_radius=TAB_HEIGHT/2,
        padding=0,
        width=TAB_WIDTH * 5,
        height=TAB_HEIGHT,
        content=ft.Stack([
            # Animated Pill
            ft.Container(
                ref=tab_indicator,
                width=TAB_WIDTH,
                height=TAB_HEIGHT,
                bgcolor=ft.Colors.PRIMARY_CONTAINER,
                border_radius=TAB_HEIGHT/2,
                left=0,
                animate_position=ft.Animation(600, ft.AnimationCurve.EASE_OUT_EXPO)
            ),
            # Labels Row
            ft.Row([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.COMPRESS, ref=tab_compressor_icon, size=16, color=ft.Colors.ON_PRIMARY_CONTAINER), 
                        ft.Text("Compressor", ref=tab_compressor_text, weight=ft.FontWeight.W_600, size=13, color=ft.Colors.ON_PRIMARY_CONTAINER)
                    ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                    width=TAB_WIDTH,
                    height=TAB_HEIGHT,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda _: set_tab("compressor"),
                    border_radius=TAB_HEIGHT/2,
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CACHED, ref=tab_converter_icon, size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("Converter", ref=tab_converter_text, weight=ft.FontWeight.W_600, size=13, color=ft.Colors.ON_SURFACE_VARIANT)
                    ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                    width=TAB_WIDTH,
                    height=TAB_HEIGHT,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda _: set_tab("converter"),
                    border_radius=TAB_HEIGHT/2,
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CONTENT_CUT_ROUNDED, ref=tab_trimmer_icon, size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("Trimmer", ref=tab_trimmer_text, weight=ft.FontWeight.W_600, size=13, color=ft.Colors.ON_SURFACE_VARIANT)
                    ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                    width=TAB_WIDTH,
                    height=TAB_HEIGHT,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda _: set_tab("trimmer"),
                    border_radius=TAB_HEIGHT/2,
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.MERGE_ROUNDED, ref=tab_merger_icon, size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("Merger", ref=tab_merger_text, weight=ft.FontWeight.W_600, size=13, color=ft.Colors.ON_SURFACE_VARIANT)
                    ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                    width=TAB_WIDTH,
                    height=TAB_HEIGHT,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda _: set_tab("merger"),
                    border_radius=TAB_HEIGHT/2,
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.MENU, ref=tab_more_icon, size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("More...", ref=tab_more_text, weight=ft.FontWeight.W_600, size=13, color=ft.Colors.ON_SURFACE_VARIANT)
                    ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                    width=TAB_WIDTH,
                    height=TAB_HEIGHT,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda _: set_tab("more"),
                    border_radius=TAB_HEIGHT/2,
                )
            ], spacing=0)
        ]),
        margin=ft.Margin.all(0)
    )

    # Window Actions
    # Window Actions (Optimized for Linux)
    # Window Actions (Robust and Flet-Version Agnostic)
    # Window Actions (Robust and Async for Flet 0.80.2)

    # Title Bar - Single layer structure for better draggability
    title_bar = ft.WindowDragArea(
        content=ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            height=35,
            padding=ft.padding.only(left=15, right=5),
            content=ft.Row([
                # Left side: Icon and Name
                ft.Row([
                    ft.Image(src="Icon.png", width=18, height=18),
                    ft.Text("Video Utilities", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE_VARIANT),
                ], spacing=10),
                
                # Right side: Control Buttons
                # Right side: Control Buttons
                ft.Row([
                    ft.IconButton(
                        ft.Icons.REMOVE_ROUNDED, 
                        icon_size=14, 
                        on_click=window_minimize,
                        style=ft.ButtonStyle(
                            shape=ft.StadiumBorder(),
                            bgcolor={"": ft.Colors.PRIMARY, "hovered": "#B69DF8"},
                            color={"": ft.Colors.ON_PRIMARY},
                            animation_duration=300,
                            padding=0
                        ),
                        width=40,
                        height=26,
                    ),
                    ft.IconButton(
                        ft.Icons.CROP_SQUARE_ROUNDED, 
                        icon_size=12, 
                        on_click=window_toggle_maximize,
                        style=ft.ButtonStyle(
                            shape=ft.StadiumBorder(),
                            bgcolor={"": ft.Colors.PRIMARY, "hovered": "#B69DF8"},
                            color={"": ft.Colors.ON_PRIMARY},
                            animation_duration=300,
                            padding=0
                        ),
                        width=40,
                        height=26,
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE_ROUNDED, 
                        icon_size=14, 
                        on_click=window_close,
                        style=ft.ButtonStyle(
                            shape=ft.StadiumBorder(),
                            bgcolor={"": ft.Colors.PRIMARY, "hovered": "#EF5350"},
                            color={"": ft.Colors.ON_PRIMARY},
                            animation_duration=300,
                            padding=0
                        ),
                        width=40,
                        height=26,
                    ),
                ], spacing=8)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        )
    )

    page.add(
        ft.Column([
            title_bar,
            ft.Container(
                content=ft.Column([
                    # Header (Centered Tabs)
                    ft.Stack([
                        ft.Row([tab_bar], alignment=ft.MainAxisAlignment.CENTER),
                    ], height=TAB_HEIGHT, clip_behavior=ft.ClipBehavior.NONE),
                    
                    ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
                    
                    # Main Views (Clipped Container for Slide Transition)
                    ft.Container(
                        content=ft.Stack([
                            compressor_view_col,
                            converter_view_col,
                            trimmer_view_col,
                            merger_view_col,
                            more_view_col,
                            settings_view_col,
                            about_view_col
                        ]),
                        expand=True,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE
                    )
                ], expand=True),
                expand=True,
                padding=15
            )
        ], expand=True, spacing=0)
    )

    # Initialize first tab
    set_tab("compressor")
    # Start monitor task
    if hasattr(page, "run_task"):
        page.run_task(monitor_preview_loop)
     
def run_cli():
    """
    Official Entry Point for Video Utilities.
    Using delayed imports ensures that child processes (worker threads/pids)
    do not accidentally re-initialize the entire GUI, preventing fork bombs.
    """
    print("\n--- Video Utilities (CLI Mode) ---")
    
    # Helper to get arg or prompt
    def get_arg_or_input(flag, prompt, default=None):
        if flag in sys.argv:
            try:
                idx = sys.argv.index(flag)
                return sys.argv[idx + 1]
            except IndexError:
                pass
        val = input(f"{prompt} (default: {default}): ").strip() if default else input(f"{prompt}: ").strip()
        return val or default

    mode = get_arg_or_input("--mode", "Mode (compress/convert)", "compress").lower()

    # 1. Input File
    input_file = get_arg_or_input("--input", "Input Video Path").replace('"', '').replace("'", "")
    if not os.path.exists(input_file):
        print(f"❌ File not found: {input_file}")
        return

    # 2. Setup Logic
    def cli_log(msg, replace_last=False):
        if replace_last:
            sys.stdout.write(f"\r{msg}")
            sys.stdout.flush()
        else:
            print(msg)

    if mode == "convert":
        print("\n[ Converter Mode Selected ]")
        vcodec = get_arg_or_input("--vcodec", "Video Codec (e.g. libx264, copy)", "libx264")
        acodec = get_arg_or_input("--acodec", "Audio Codec (e.g. aac, copy)", "aac")
        fmt = get_arg_or_input("--format", "Output Format (mp4, mkv, mov, avi, mp3)", "mp4").lower()
        if fmt and not fmt.startswith("."):
            fmt = "." + fmt
            
        output_file = get_arg_or_input("--output", "Output Path")
        if output_file and not output_file.lower().endswith(fmt):
            base, _ = os.path.splitext(output_file)
            output_file = f"{base}{fmt}"
        
        success, result = logic.simple_convert(input_file, output_file, vcodec, acodec, log_func=cli_log)
    else:
        # 2. Target Size
        try:
            target_mb = float(get_arg_or_input("--size", "Target Size (MB)"))
        except Exception:
            print("❌ Invalid size!")
            return

        # 3. Codec
        print("\n[ All encoders enabled by default in CLI ]")
        codec = get_arg_or_input("--codec", "Codec (e.g. h264, av1, cinepak)", "h264").lower()
        
        # 4. GPU
        if "--gpu" in sys.argv:
            use_gpu = True
        elif "--no-gpu" in sys.argv:
            use_gpu = False
        else:
            use_gpu = input("Use GPU hardware acceleration? (y/n, default: n): ").lower().strip() == 'y'
        
        # 5. Output
        fmt = get_arg_or_input("--format", "Container Format (mp4, mkv, mov, avi)", "mp4").lower()
        if fmt and not fmt.startswith("."):
            fmt = "." + fmt
            
        output_file = get_arg_or_input("--output", "Output Path (leave empty for auto)", "auto")
        if output_file == "auto":
            output_file = None
        else:
            # If they provided an extension, respect it. 
            # If no extension provided, add the chosen format.
            _, ext = os.path.splitext(output_file)
            if not ext:
                output_file = f"{output_file}{fmt}"

        print(f"\n🚀 STARTING COMPRESSION: {os.path.basename(input_file)}")
        success, result = logic.auto_compress(
            input_file=input_file,
            target_mb=target_mb,
            codec=codec,
            use_gpu=use_gpu,
            output_file=output_file,
            log_func=cli_log
        )
    
    if success:
        print(f"\n✨ SUCCESS: {result}")
    else:
        print("\n❌ FAILED: Operation could not be completed.")

# This file is now imported as a module by launcher.py to prevent fork bombs on Windows
