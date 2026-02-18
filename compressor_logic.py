import subprocess
import os
import sys
import platform
import threading
import re

# Logic to prevent console windows from popping up on Windows
SUBPROCESS_FLAGS = 0
if os.name == 'nt':
    SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW

# Define for cross-platform safety (only used on Windows)
CREATE_NEW_CONSOLE = 16

def is_ffmpeg_installed():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS, check=True)
        return True
    except:
        return False

def install_ffmpeg(log_func=print):
    system = platform.system().lower()
    
    try:
        if system == "windows":
            log_func("🪟 Windows detected. Attempting install via winget...")
            # Using run instead of Popen for simplicity here, or Popen if we want to stream logs
            # Launch in a new visible console so user can accept terms/prompts
            creation_flags = CREATE_NEW_CONSOLE
            process = subprocess.Popen(['winget', 'install', 'ffmpeg'], creationflags=creation_flags)
            process.wait()
            return process.returncode == 0
            
        elif system == "linux":
            log_func("🐧 Linux detected. Identifying package manager...")
            
            # Check for common package managers
            managers = [
                (['apt-get', 'install', '-y', 'ffmpeg'], "Debian/Ubuntu/Pop!_OS/Mint"),
                (['pacman', '-S', '--noconfirm', 'ffmpeg'], "Arch/Manjaro/SteamOS/Endeavour"),
                (['dnf', 'install', '-y', 'ffmpeg'], "Fedora/RHEL/CentOS")
            ]
            
            for cmd_args, distro_name in managers:
                if subprocess.run(['which', cmd_args[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS).returncode == 0:
                    log_func(f"📦 Found {distro_name} manager. Installing...")
                    # Note: sudo might be needed, which is tricky in a GUI without a terminal.
                    # We'll try pkexec or similar if available, otherwise raw.
                    
                    final_cmd = cmd_args
                    if os.getuid() != 0:
                        # Try to use pkexec for a GUI password prompt
                        if subprocess.run(['which', 'pkexec'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS).returncode == 0:
                            final_cmd = ['pkexec'] + cmd_args
                        else:
                            log_func("⚠️ sudo privileges required but pkexec (GUI sudo) not found.")
                    
                    process = subprocess.Popen(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, creationflags=SUBPROCESS_FLAGS)
                    for line in process.stdout:
                        log_func(line.strip())
                    process.wait()
                    return process.returncode == 0
            
            log_func("❌ No supported package manager found (apt, pacman, dnf).")
            return False
            
    except Exception as e:
        log_func(f"❌ Install error: {e}")
        return False
    
    return False

def hms_to_seconds(hms):
    try:
        parts = hms.split(':')
        if len(parts) == 3:
            h, m, s = parts
            return float(h) * 3600 + float(m) * 60 + float(s)
    except: pass
    return 0

def get_hardware_info():
    try:
        lspci = subprocess.check_output(['lspci'], encoding='utf-8', stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS)
        lspci_up = lspci.upper()
        if "NVIDIA" in lspci_up: return "nvidia"
        if "AMD" in lspci_up or "ATI" in lspci_up or "ADVANCED MICRO DEVICES" in lspci_up: return "amd"
        if "INTEL" in lspci_up: return "intel"
    except:
        pass
    return "unknown"

def get_all_encoders():
    try:
        output = subprocess.check_output(['ffmpeg', '-encoders'], encoding='utf-8', stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS)
        encoders = []
        for line in output.split('\n'):
            # Only look for Video (V) encoders
            if line.strip().startswith('V'):
                parts = line.split()
                if len(parts) >= 2:
                    # parts[1] is the encoder name
                    encoders.append(parts[1])
        return sorted(list(set(encoders)))
    except:
        return []

def get_encoder(codec_choice, use_gpu, log_func=print):
    try:
        output = subprocess.check_output(['ffmpeg', '-encoders'], encoding='utf-8', stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS)
        is_linux = platform.system().lower() == "linux"
        
        if use_gpu:
            hw = get_hardware_info()
            
            # Map codec to candidate lists prioritizing current hardware and OS
            codec_map = {
                "h264": {
                    "nvidia": ['h264_nvenc', 'h264_vaapi'],
                    "amd": (['h264_vaapi', 'h264_amf'] if is_linux else ['h264_amf', 'h264_vaapi']),
                    "intel": ['h264_vaapi', 'h264_qsv'],
                    "unknown": ['h264_nvenc', 'h264_amf', 'h264_vaapi']
                },
                "h265": {
                    "nvidia": ['hevc_nvenc', 'hevc_vaapi'],
                    "amd": (['hevc_vaapi', 'hevc_amf'] if is_linux else ['hevc_amf', 'hevc_vaapi']),
                    "intel": ['hevc_vaapi', 'hevc_qsv'],
                    "unknown": ['hevc_nvenc', 'hevc_amf', 'hevc_vaapi']
                },
                "av1": {
                    "nvidia": ['av1_nvenc', 'av1_vaapi'],
                    "amd": (['av1_vaapi', 'av1_amf'] if is_linux else ['av1_amf', 'av1_vaapi']),
                    "intel": ['av1_vaapi', 'av1_qsv'],
                    "unknown": ['av1_amf', 'av1_vaapi', 'av1_nvenc']
                },
                "vp9": {
                    "nvidia": ['vp9_nvenc', 'vp9_vaapi'],
                    "amd": ['vp9_vaapi'],
                    "intel": ['vp9_vaapi', 'vp9_qsv'],
                    "unknown": ['vp9_vaapi', 'vp9_qsv', 'vp9_nvenc']
                },
                "vp8": {
                    "nvidia": ['vp8_vaapi'], # NVENC doesn't support VP8
                    "amd": ['vp8_vaapi'],
                    "intel": ['vp8_vaapi', 'vp8_qsv'],
                    "unknown": ['vp8_vaapi', 'vp8_qsv']
                },
                "mpeg2": {
                    "intel": ['mpeg2_vaapi', 'mpeg2_qsv'],
                    "nvidia": ['mpeg2_nvenc', 'mpeg2_vaapi'],
                    "unknown": ['mpeg2_vaapi', 'mpeg2_qsv']
                }
            }
            
            if codec_choice in codec_map:
                candidates = codec_map[codec_choice].get(hw, codec_map[codec_choice]["unknown"])
                for enc in candidates:
                    if enc in output: return enc
            
            log_func(f"⚠️ GPU encoder for {codec_choice} requested but no compatible hardware found. Falling back to software.")
        
        # Software Fallbacks
        fallbacks = {
            "h264": "libx264", 
            "h265": "libx265", 
            "av1": "libsvtav1", 
            "h266": "libvvenc", 
            "vp9": "libvpx-vp9", 
            "vp8": "libvpx", 
            "theora": "libtheora",
            "mpeg4": "mpeg4",
            "mpeg2": "mpeg2video",
            "wmv": "wmv2",
            "libxvid": "libxvid",
            "msmpeg4v2": "msmpeg4v2",
            "flv1": "flv",
            "h261": "h261",
            "h263": "h263",
            "snow": "snow",
            "cinepak": "cinepak",
            "roq": "roqvideo",
            "smc": "smc",
            "vc1": "wmv3"
        }
        
        # If it's in the fallback list, use the fallback
        if codec_choice in fallbacks:
            return fallbacks[codec_choice]
            
        # If the user provided a raw encoder name that FFmpeg supports, use it directly (CLI flexibility)
        if f" {codec_choice} " in output or codec_choice in output.split():
            return codec_choice
            
        return None
    except:
        return None

def get_video_duration(input_file):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
        dur = subprocess.check_output(cmd, encoding='utf-8', stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS)
        return float(dur.strip())
    except:
        return 0

def compress_attempt(input_file, output_file, target_mb, res, codec, use_gpu, log_func=print, stop_event=None, preview_path=None, progress_callback=None, advanced_params=None):
    if stop_event and stop_event.is_set(): return False

    # Get Duration
    try:
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', input_file], encoding='utf-8', creationflags=SUBPROCESS_FLAGS)
        duration = float(probe)
    except Exception as e:
        log_func(f"❌ Error getting duration: {e}")
        return False
    
    # Calculate bitrate (Target Size minus ~10% for overhead)
    video_kbps = max(int(((target_mb * 8192 * 0.9) / duration) - 64), 50)
    
    v_enc = get_encoder(codec, use_gpu, log_func)
    if not v_enc:
        log_func(f"❌ Error: No encoder found for {codec}")
        return False

    # Resolution & Bitrate Caps for legacy encoders
    if v_enc == "h261":
        res = min(res, 288) # H.261 max is CIF (352x288)
        video_kbps = min(video_kbps, 64) # H.261 ONLY supports 64k or multiples. 64k is the safest.
    elif v_enc in ["h263", "flv", "roqvideo", "cinepak"]:
        res = min(res, 480) 
        video_kbps = min(video_kbps, 2000) # Prevents bloat in ancient formats
    
    mode_str = "GPU" if use_gpu and any(x in v_enc for x in ['nvenc', 'amf', 'vaapi', 'qsv']) else "Software"
    log_func(f"\n--- ENCODING: {v_enc.upper()} ({mode_str}) | {res}p | Target: {video_kbps}kbps ---")

    # Global/Hardware Init
    hw_init = []
    if 'vaapi' in v_enc:
        hw_init = ['-vaapi_device', '/dev/dri/renderD128']

    # Filters & Advanced Params
    v_filter = f"scale=-2:{res},format=yuv420p"
    
    # --- OBSTACLE COURSE: Handle goofy encoder constraints ---
    if v_enc == "h261":
        # H.261 only supports 176x144 (QCIF) or 352x288 (CIF) AND exactly 29.97 fps
        h261_res = 288 if res >= 288 else 144
        w261 = 352 if h261_res == 288 else 176
        v_filter = f"scale={w261}:{h261_res},format=yuv420p,fps=30000/1001"
    elif v_enc == "roqvideo":
        # RoQ requires width/height to be multiples of 16 and prefers 30fps
        v_filter = f"scale='trunc(iw/16)*16':'trunc(ih/16)*16',format=yuv420p,fps=30"
    elif v_enc == "h263":
        # H.263 prefers multiples of 16
        v_filter = f"scale='bitand(iw, -16)':'bitand(ih, -16)',format=yuv420p"
    elif v_enc == "cinepak":
        # Cinepak requires multiples of 4 and likes steady fps
        v_filter = f"scale='bitand(iw, -4)':'bitand(ih, -4)',format=yuv420p,fps=30"
    elif v_enc == "snow":
        # Snow often likes yuv420p
        v_filter = f"scale=-2:{res},format=yuv420p"
    # --------------------------------------------------------

    # Apply Denoise if enabled
    if advanced_params and advanced_params.get("denoise"):
        v_filter += ",hqdn3d=2:2:7:7"

    ten_bit = advanced_params.get("ten_bit") if advanced_params else False

    if ten_bit:
        v_filter = v_filter.replace("format=yuv420p", "format=yuv420p10le")
        
    if 'vaapi' in v_enc:
        # VAAPI requires p010 for 10-bit, nv12 for 8-bit
        fmt = "p010" if ten_bit else "nv12"
        # If denoise was applied (it ends with hqdn3d...), we append the rest. 
        # But we must ensure format compatibility. hqdn3d output is yuv420p typically.
        # So we transition to fmt(nv12/p010) -> hwupload -> scale_vaapi
        
        # We replace the software scale/format with VAAPI chain, BUT if denoise is on, we keep it?
        # Standard software path: scale=-2:{res},format=yuv420p,hqdn3d
        # VAAPI path: (optional denoise) -> format=nv12,hwupload,scale_vaapi
        
        base_filter = ""
        if advanced_params and advanced_params.get("denoise"):
            base_filter = "hqdn3d=2:2:7:7,"
            
        v_filter = f"{base_filter}format={fmt},hwupload,scale_vaapi=w=-2:h={res}"
    
    enc_args = ['-c:v', v_enc, '-b:v', f"{video_kbps}k"]
    
    # H.261 / Ancient Codec overrides
    if v_enc == "h261":
        # Force exactly 29.97, no advanced bitrate params
        enc_args = ['-c:v', 'h261', '-b:v', '64k', '-r', '30000/1001']
    
    # Apply Advanced Parameters (Skips H.261 to avoid bitrate conflicts)
    if advanced_params and v_enc != "h261":
            
        if advanced_params.get("keyframe"):
            enc_args.extend(['-g', advanced_params.get("keyframe")])
            
        # Encoder Specific Settings
        cpu = int(advanced_params.get("cpu_used", 6))
        
        if v_enc == "libsvtav1":
            p_val = cpu + 4 
            enc_args.extend(['-preset', str(p_val)])
            if advanced_params.get("aq"):
                enc_args.extend(['-svtav1-params', 'enable-variance-boost=1'])
                
        elif v_enc == "libvvenc":
            enc_args.extend(['-preset', 'faster'])
            
        elif v_enc == "av1_vaapi":
            pass 
            
        elif codec == "av1" and "libaom" in v_enc: 
            enc_args.extend(['-cpu-used', str(cpu), '-tile-columns', '2'])
            if advanced_params.get("aq"):
                enc_args.extend(['-aq-mode', '3'])

    if 'nvenc' in v_enc:
        enc_args.extend(['-preset', 'p7', '-tune', 'hq'])
    
    audio_args = ['-c:a', 'aac', '-b:a', '64k']
    if advanced_params and codec == "av1":
        # Professional Opus audio for AV1 as per recipe
        audio_args = ['-c:a', 'libopus', '-b:a', '48k', '-vbr', 'on', '-frame_duration', '60']

    # --- OBSTACLE COURSE: Strict compatibility for legacy encoders ---
    legacy_encoders = ['h261', 'h263', 'roqvideo', 'snow', 'cinepak', 'msmpeg4v2', 'libxvid', 'flv', 'smc', 'wmv3']
    is_legacy = any(le in v_enc for le in legacy_encoders)
    if is_legacy:
        enc_args.extend(['-strict', '-2'])
    # ----------------------------------------------------------------

    # Setup main encoding command
    
    prev_process = None
    if preview_path:
        # Start a lightweight independent preview generator
        # Using -update 1 to continuously update a single file
        prev_cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', input_file,
            '-vf', 'fps=1,scale=480:-1', '-update', '1', '-q:v', '2', preview_path
        ]
        try:
            prev_process = subprocess.Popen(prev_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=SUBPROCESS_FLAGS)
            log_func(f"📸 Preview generator started for: {os.path.basename(preview_path)}")
        except Exception as e:
            log_func(f"⚠️ Failed to start preview generator: {e}")

    # Two-Pass Logic: Force single pass for legacy encoders
    passes = [1, 2] if advanced_params and advanced_params.get("two_pass") and not is_legacy else [0]
    
    try:
        for p in passes:
            if stop_event and stop_event.is_set():
                if prev_process:
                    try: prev_process.terminate()
                    except: pass
                log_func("🛑 Process stopped by user.")
                try: os.remove(preview_path) if preview_path and os.path.exists(preview_path) else None
                except: pass
                return False
            
            if p == 0:
                # Single-pass encoding (no -pass flag)
                log_func(f"Encoding...", replace_last=True)
                cur_cmd = ['ffmpeg', '-y', '-hide_banner', '-stats'] + hw_init + ['-i', input_file] + \
                          ['-vf', v_filter] + enc_args + audio_args + [output_file]
            elif p == 1:
                log_func(f"Starting Pass 1...", replace_last=True)
                # Pass 1: No audio, dummy output
                cur_cmd = ['ffmpeg', '-y', '-hide_banner', '-stats'] + hw_init + ['-i', input_file] + \
                          ['-vf', v_filter] + enc_args + ['-pass', '1'] + ['-an', '-f', 'null', '/dev/null']
            else:
                log_func(f"Starting Pass 2...", replace_last=True)
                # Pass 2: Final output
                cur_cmd = ['ffmpeg', '-y', '-hide_banner', '-stats'] + hw_init + ['-i', input_file] + \
                          ['-vf', v_filter] + enc_args + ['-pass', '2'] + audio_args + [output_file]

            process = subprocess.Popen(
                cur_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                creationflags=SUBPROCESS_FLAGS
            )

            progress_re = re.compile(r"fps=\s*([\d.]+).*time=(\d+:\d+:\d+\.\d+).*speed=\s*([\d.]+)x")
            error_log = []

            if process.stdout:
                for line in process.stdout:
                    if stop_event and stop_event.is_set():
                        try: process.terminate()
                        except: pass
                        if prev_process:
                            try: prev_process.terminate()
                            except: pass
                        log_func("🛑 Process stopped by user.")
                        try: os.remove(preview_path) if preview_path and os.path.exists(preview_path) else None
                        except: pass
                        return False
                    
                    match = progress_re.search(line)
                    if match:
                        fps_val, time_val, speed_val = match.groups()
                        if progress_callback:
                            current_secs = hms_to_seconds(time_val)
                            # Handle both single-pass (p=0) and two-pass (p=1,2)
                            if p == 0:
                                # Single pass: 0-100%
                                pct = min(current_secs / duration, 1.0) if duration > 0 else 0
                            else:
                                # Two-pass: each pass is 50%
                                pct_mult = 0.5
                                base_pct = 0.5 if p == 2 else 0.0
                                pct = base_pct + (min(current_secs / duration, 1.0) * pct_mult) if duration > 0 else 0
                            
                            # Calculate time remaining for the current pass
                            try:
                                speed = float(speed_val)
                                rem_secs = (duration - current_secs) / speed if speed > 0 else 0
                                
                                m, s = divmod(int(rem_secs), 60)
                                h, m = divmod(m, 60)
                                rem_time_str = f"{h:02d}:{m:02d}:{s:02d}"
                            except:
                                rem_time_str = "00:00:00"

                            progress_callback({
                                "res": res,
                                "pct": pct,
                                "fps": fps_val,
                                "rem_time": rem_time_str
                            })
                        
                        if p == 2: # Only log detailed progress for the second pass
                            log_func(f"⏳ {time_val} @ {fps_val} fps | Speed: {speed_val}x", replace_last=True)
                        elif p == 1:
                            log_func(f"⏳ Pass 1: {time_val} @ {fps_val} fps | Speed: {speed_val}x", replace_last=True)
                        else:
                            log_func(f"⏳ {time_val} @ {fps_val} fps | Speed: {speed_val}x", replace_last=True)
                    else:
                        # Capture output for debugging if it fails
                        if line.strip():
                            error_log.append(line.strip())
                            if len(error_log) > 20: error_log.pop(0)

            process.wait()
            if process.returncode != 0:
                log_func(f"❌ FFmpeg process failed during Pass {p} with exit code {process.returncode}")
                if error_log:
                    log_func(f"Last output:\n" + "\n".join(error_log))
                if prev_process:
                    try: prev_process.terminate()
                    except: pass
                return False
        
        if prev_process:
            try: prev_process.terminate()
            except: pass
        return True
    except Exception as e:
        if prev_process:
            try: prev_process.terminate()
            except: pass
        log_func(f"❌ Error: {e}")
        return False

def auto_compress(input_file, target_mb, codec, use_gpu, output_file=None, log_func=print, stop_event=None, preview_path=None, progress_callback=None, advanced_params=None):
    # --- Container Compatibility Check ---
    # Many obscure easter egg codecs are incompatible with standard MP4.
    # However, MOV (Myst's favorite) and MKV are generally okay for these fossils.
    legacy_codecs = ["libxvid", "msmpeg4v2", "flv1", "h261", "h263", "snow", "cinepak", "roq", "smc", "vc1"]
    
    if not output_file:
        # Default to MKV for legacy codecs to avoid MP4 failures
        ext = ".mkv" if codec in legacy_codecs else ".mp4"
        output_file = f"compressed_{codec}_{os.path.basename(input_file).rsplit('.', 1)[0]}{ext}"
    
    if codec in legacy_codecs and output_file.lower().endswith(".mp4"):
        output_file = output_file.rsplit('.', 1)[0] + ".mkv"
        log_func(f"ℹ️ {codec.upper()} is incompatible with MP4. Forcing MKV container...")
    # -------------------------------------

    is_deck = platform.system().lower() == "linux" and os.path.exists('/home/deck')

    last_msg = ""
    def smart_log(msg, replace_last=False):
        nonlocal last_msg
        log_func(msg, replace_last=replace_last)
        last_msg = msg

    for res in [1440, 1080, 720, 480, 360]:
        if stop_event and stop_event.is_set(): break

        # Attempt 1: As requested
        success = compress_attempt(input_file, output_file, target_mb, res, codec, use_gpu, smart_log, stop_event, preview_path, progress_callback, advanced_params)
        
        # Fallback to software
        if not success and use_gpu and not (stop_event and stop_event.is_set()):
            smart_log(f"🔄 GPU attempt failed at {res}p. Retrying with Software...")
            success = compress_attempt(input_file, output_file, target_mb, res, codec, False, smart_log, stop_event, preview_path, progress_callback, advanced_params)

        if success and os.path.exists(output_file):
            final_size = os.path.getsize(output_file) / 1048576
            if final_size <= target_mb:
                smart_log(f"\n✅ SUCCESS: {output_file} ({final_size:.2f} MB)")
                if is_deck:
                    subprocess.run(['kitten', 'notify', 'Compression Done', f"{res}p {codec} finished"], stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS)
                try: os.remove(preview_path) if preview_path and os.path.exists(preview_path) else None
                except: pass
                return True, output_file
            else:
                smart_log(f"⚠️ Result too large ({final_size:.2f}MB). Trying lower resolution...")
        elif not (stop_event and stop_event.is_set()):
            smart_log(f"❌ Encoding failed at {res}p. Skipping...")
    
    try: os.remove(preview_path) if preview_path and os.path.exists(preview_path) else None
    except: pass
    return False, None

def simple_convert(input_file, output_file, vcodec, acodec, log_func=print, progress_callback=None):
    """Simple 1:1 conversion without bitrate targeting."""
    try:
        # Detect total duration for progress
        total_duration = 0
        try:
            dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file]
            dur_res = subprocess.run(dur_cmd, capture_output=True, text=True, creationflags=SUBPROCESS_FLAGS)
            total_duration = float(dur_res.stdout.strip())
        except: pass

        # Build command
        cmd = ["ffmpeg", "-y", "-i", input_file]
        
        # Determine if it's audio-only based on extension
        audio_exts = [".mp3", ".wav", ".flac", ".aac", ".opus", ".ogg", ".m4a"]
        is_audio = any(output_file.lower().endswith(ext) for ext in audio_exts)
        
        if is_audio:
            cmd.extend(["-vn", "-c:a", acodec if acodec else "copy"])
        else:
            cmd.extend(["-c:v", vcodec if vcodec else "copy", "-c:a", acodec if acodec else "copy"])
        
        cmd.append(output_file)
        
        log_func(f"🚀 Running: {' '.join(cmd)}")
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, creationflags=SUBPROCESS_FLAGS)
        
        progress_re = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")
        
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None: break
            if line:
                match = progress_re.search(line)
                if match and total_duration > 0:
                    t_str = match.group(1)
                    parts = t_str.split(':')
                    secs = float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
                    pct = min(secs / total_duration, 1.0)
                    
                    if progress_callback:
                        progress_callback({"pct": pct, "time": t_str})
                    
                    log_func(f"⏳ Progress: {int(pct*100)}% ({t_str})", replace_last=True)
        
        if process.returncode == 0:
            return True, output_file
        else:
            return False, None
    except Exception as e:
        log_func(f"❌ Conversion Error: {e}")
        return False, None

def merge_videos(video_paths, output_path, log_func=print, stop_event=None, use_gpu=True):
    """
    Merge multiple videos into one using the concat filter (re-encoding for compatibility).
    """
    if stop_event and stop_event.is_set():
        return False, "Process cancelled"

    if not video_paths:
        log_func("❌ No videos to merge.")
        return False, "No videos selected"

    if len(video_paths) == 1:
        log_func("⚠️ Only one video selected. Copying to output...")
        try:
            import shutil
            shutil.copy2(video_paths[0], output_path)
            return True, output_path
        except Exception as e:
            return False, str(e)

    # Build Filter Complex
    # We must normalize all inputs to the same resolution, SAR, and framerate for the concat filter to work reliably.
    inputs = []
    filter_complex = ""
    
    # Target 1080p, 30fps, 16:9 for maximum compatibility
    w = 1920
    h = 1080
    fps = 30
    
    for i in range(len(video_paths)):
        inputs.extend(["-i", video_paths[i]])
        # Scale each video to target w:h, forcing SAR 1:1, and setting generic PTS
        # We use force_original_aspect_ratio=decrease and pad to keep aspect ratio without stretching
        filter_complex += (
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={fps},format=yuv420p[v{i}];"
            f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}];"
        )
    
    # Concat block
    for i in range(len(video_paths)):
        filter_complex += f"[v{i}][a{i}]"
    
    filter_complex += f"concat=n={len(video_paths)}:v=1:a=1[outv_raw][outa]"
    
    # Try to use GPU encoder, fallback to software
    video_encoder = get_encoder("h264", use_gpu=use_gpu, log_func=log_func)
    
    hw_init = []
    final_v_map = "[outv_raw]"
    enc_args = ["-preset", "fast"]
    
    if "vaapi" in video_encoder:
        hw_init = ["-vaapi_device", "/dev/dri/renderD128"]
        filter_complex += f";[outv_raw]format=nv12,hwupload[outv]"
        final_v_map = "[outv]"
        enc_args = [] # VAAPI uses different speed controls
    elif "nvenc" in video_encoder:
        enc_args = ["-preset", "p4", "-rc", "vbr", "-cq", "23"]
    elif "amf" in video_encoder:
        enc_args = ["-rc", "vbr_peak", "-peak_bitrate", "5000k"]
    else:
        # Software encoder (libx264)
        enc_args = ["-preset", "fast", "-crf", "23"]

    cmd = [
        "ffmpeg", "-y", "-hide_banner"
    ]
    cmd.extend(hw_init)
    cmd.extend(inputs)
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", final_v_map,
        "-map", "[outa]",
        "-c:v", video_encoder
    ])
    cmd.extend(enc_args)
    cmd.extend([
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ])

    log_func(f"🚀 Starting merge of {len(video_paths)} files...")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            creationflags=SUBPROCESS_FLAGS
        )

        for line in process.stdout:
            # Check for stop signal
            if stop_event and stop_event.is_set():
                process.terminate()
                log_func("🛑 Process stopped by user.")
                return False, "Cancelled"

            if "frame=" in line or "time=" in line:
                log_func(line.strip(), replace_last=True)
            else:
                log_func(line.strip())

        process.wait()
        
        if process.returncode == 0:
            return True, output_path
        else:
            return False, "FFmpeg process failed"
            
    except Exception as e:
        return False, str(e)