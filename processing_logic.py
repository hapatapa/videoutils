import subprocess
import os
import sys
import platform
import threading
import re
import shutil
import tempfile

# Logic to prevent console windows from popping up on Windows
SUBPROCESS_FLAGS = 0
if os.name == 'nt':
    SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW

# Define for cross-platform safety (only used on Windows)
CREATE_NEW_CONSOLE = 16

# --- System & Setup Utilities ---

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
            creation_flags = CREATE_NEW_CONSOLE
            process = subprocess.Popen(['winget', 'install', 'ffmpeg'], creationflags=creation_flags)
            process.wait()
            return process.returncode == 0
            
        elif system == "linux":
            log_func("🐧 Linux detected. Identifying package manager...")
            
            managers = [
                (['apt-get', 'install', '-y', 'ffmpeg'], "Debian/Ubuntu/Pop!_OS/Mint"),
                (['pacman', '-S', '--noconfirm', 'ffmpeg'], "Arch/Manjaro/SteamOS/Endeavour"),
                (['dnf', 'install', '-y', 'ffmpeg'], "Fedora/RHEL/CentOS")
            ]
            
            for cmd_args, distro_name in managers:
                if subprocess.run(['which', cmd_args[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS).returncode == 0:
                    log_func(f"📦 Found {distro_name} manager. Installing...")
                    
                    final_cmd = cmd_args
                    if os.getuid() != 0:
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

# --- Helper Utilities ---

def hms_to_seconds(hms):
    try:
        parts = hms.split(':')
        if len(parts) == 3:
            h, m, s = parts
            return float(h) * 3600 + float(m) * 60 + float(s)
    except: pass
    return 0

def get_video_duration(path, log_func=print):
    """Return duration in seconds via ffprobe, or None on failure."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                creationflags=SUBPROCESS_FLAGS)
        output = result.stdout.strip()
        if not output:
             return None
        return float(output)
    except Exception as e:
        log_func(f"⚠️ Could not get duration: {e}")
        return None

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
            if line.strip().startswith('V'):
                parts = line.split()
                if len(parts) >= 2:
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
                    "nvidia": ['vp8_vaapi'],
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
        
        if codec_choice in fallbacks:
            return fallbacks[codec_choice]
            
        if f" {codec_choice} " in output or codec_choice in output.split():
            return codec_choice
            
        return None
    except:
        return None

# --- Compression & Conversion Features ---

def compress_attempt(input_file, output_file, target_mb, res, codec, use_gpu, log_func=print, stop_event=None, preview_path=None, progress_callback=None, advanced_params=None):
    if stop_event and stop_event.is_set(): return False

    duration = get_video_duration(input_file, log_func)
    if duration is None or duration <= 0:
        log_func(f"❌ Error getting duration for {input_file}")
        return False
    
    video_kbps = max(int(((target_mb * 8192 * 0.9) / duration) - 64), 50)
    
    v_enc = get_encoder(codec, use_gpu, log_func)
    if not v_enc:
        log_func(f"❌ Error: No encoder found for {codec}")
        return False

    if v_enc == "h261":
        res = min(res, 288)
        video_kbps = min(video_kbps, 64)
    elif v_enc in ["h263", "flv", "roqvideo", "cinepak"]:
        res = min(res, 480) 
        video_kbps = min(video_kbps, 2000)
    
    mode_str = "GPU" if use_gpu and any(x in v_enc for x in ['nvenc', 'amf', 'vaapi', 'qsv']) else "Software"
    log_func(f"\n--- ENCODING: {v_enc.upper()} ({mode_str}) | {res}p | Target: {video_kbps}kbps ---")

    hw_init = []
    if 'vaapi' in v_enc:
        hw_init = ['-vaapi_device', '/dev/dri/renderD128']

    v_filter = f"scale=-2:{res},format=yuv420p"
    
    if v_enc == "h261":
        h261_res = 288 if res >= 288 else 144
        w261 = 352 if h261_res == 288 else 176
        v_filter = f"scale={w261}:{h261_res},format=yuv420p,fps=30000/1001"
    elif v_enc == "roqvideo":
        v_filter = f"scale='trunc(iw/16)*16':'trunc(ih/16)*16',format=yuv420p,fps=30"
    elif v_enc == "h263":
        v_filter = f"scale='bitand(iw, -16)':'bitand(ih, -16)',format=yuv420p"
    elif v_enc == "cinepak":
        v_filter = f"scale='bitand(iw, -4)':'bitand(ih, -4)',format=yuv420p,fps=30"
    elif v_enc == "snow":
        v_filter = f"scale=-2:{res},format=yuv420p"

    if advanced_params and advanced_params.get("denoise"):
        v_filter += ",hqdn3d=2:2:7:7"

    ten_bit = advanced_params.get("ten_bit") if advanced_params else False

    if ten_bit:
        v_filter = v_filter.replace("format=yuv420p", "format=yuv420p10le")
        
    if 'vaapi' in v_enc:
        fmt = "p010" if ten_bit else "nv12"
        base_filter = ""
        if advanced_params and advanced_params.get("denoise"):
            base_filter = "hqdn3d=2:2:7:7,"
        v_filter = f"{base_filter}format={fmt},hwupload,scale_vaapi=w=-2:h={res}"
    
    enc_args = ['-c:v', v_enc, '-b:v', f"{video_kbps}k"]
    
    if v_enc == "h261":
        enc_args = ['-c:v', 'h261', '-b:v', '64k', '-r', '30000/1001']
    
    if advanced_params and v_enc != "h261":
        if advanced_params.get("keyframe"):
            enc_args.extend(['-g', advanced_params.get("keyframe")])
            
        cpu = int(advanced_params.get("cpu_used", 6))
        
        if v_enc == "libsvtav1":
            p_val = cpu + 4 
            enc_args.extend(['-preset', str(p_val)])
            if advanced_params.get("aq"):
                enc_args.extend(['-svtav1-params', 'enable-variance-boost=1'])
        elif v_enc == "libvvenc":
            enc_args.extend(['-preset', 'faster'])
        elif codec == "av1" and "libaom" in v_enc: 
            enc_args.extend(['-cpu-used', str(cpu), '-tile-columns', '2'])
            if advanced_params.get("aq"):
                enc_args.extend(['-aq-mode', '3'])

    if 'nvenc' in v_enc:
        enc_args.extend(['-preset', 'p7', '-tune', 'hq'])
    
    audio_args = ['-c:a', 'aac', '-b:a', '64k']
    if advanced_params and codec == "av1":
        audio_args = ['-c:a', 'libopus', '-b:a', '48k', '-vbr', 'on', '-frame_duration', '60']

    legacy_encoders = ['h261', 'h263', 'roqvideo', 'snow', 'cinepak', 'msmpeg4v2', 'libxvid', 'flv', 'smc', 'wmv3']
    is_legacy = any(le in v_enc for le in legacy_encoders)
    if is_legacy:
        enc_args.extend(['-strict', '-2'])

    prev_process = None
    if preview_path:
        prev_cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', input_file,
            '-vf', 'fps=1,scale=480:-1', '-update', '1', '-q:v', '2', preview_path
        ]
        try:
            prev_process = subprocess.Popen(prev_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=SUBPROCESS_FLAGS)
            log_func(f"📸 Preview generator started for: {os.path.basename(preview_path)}")
        except Exception as e:
            log_func(f"⚠️ Failed to start preview generator: {e}")

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
                log_func(f"Encoding...", replace_last=True)
                cur_cmd = ['ffmpeg', '-y', '-hide_banner', '-stats'] + hw_init + ['-i', input_file] + \
                          ['-vf', v_filter] + enc_args + audio_args + [output_file]
            elif p == 1:
                log_func(f"Starting Pass 1...", replace_last=True)
                cur_cmd = ['ffmpeg', '-y', '-hide_banner', '-stats'] + hw_init + ['-i', input_file] + \
                          ['-vf', v_filter] + enc_args + ['-pass', '1'] + ['-an', '-f', 'null', '/dev/null']
            else:
                log_func(f"Starting Pass 2...", replace_last=True)
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
                            if p == 0:
                                pct = min(current_secs / duration, 1.0) if duration > 0 else 0
                            else:
                                pct_mult = 0.5
                                base_pct = 0.5 if p == 2 else 0.0
                                pct = base_pct + (min(current_secs / duration, 1.0) * pct_mult) if duration > 0 else 0
                            
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
                        
                        if p == 2:
                            log_func(f"⏳ {time_val} @ {fps_val} fps | Speed: {speed_val}x", replace_last=True)
                        elif p == 1:
                            log_func(f"⏳ Pass 1: {time_val} @ {fps_val} fps | Speed: {speed_val}x", replace_last=True)
                        else:
                            log_func(f"⏳ {time_val} @ {fps_val} fps | Speed: {speed_val}x", replace_last=True)
                    else:
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
    legacy_codecs = ["libxvid", "msmpeg4v2", "flv1", "h261", "h263", "snow", "cinepak", "roq", "smc", "vc1"]
    
    if not output_file:
        ext = ".mkv" if codec in legacy_codecs else ".mp4"
        output_file = f"compressed_{codec}_{os.path.basename(input_file).rsplit('.', 1)[0]}{ext}"
    
    if codec in legacy_codecs and output_file.lower().endswith(".mp4"):
        output_file = output_file.rsplit('.', 1)[0] + ".mkv"
        log_func(f"ℹ️ {codec.upper()} is incompatible with MP4. Forcing MKV container...")
    
    is_deck = platform.system().lower() == "linux" and os.path.exists('/home/deck')

    last_msg = ""
    def smart_log(msg, replace_last=False):
        nonlocal last_msg
        log_func(msg, replace_last=replace_last)
        last_msg = msg

    for res in [1440, 1080, 720, 480, 360]:
        if stop_event and stop_event.is_set(): break

        success = compress_attempt(input_file, output_file, target_mb, res, codec, use_gpu, smart_log, stop_event, preview_path, progress_callback, advanced_params)
        
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
    try:
        total_duration = get_video_duration(input_file, log_func)
        if total_duration is None: total_duration = 0

        cmd = ["ffmpeg", "-y", "-i", input_file]
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
    if stop_event and stop_event.is_set():
        return False, "Process cancelled"

    if not video_paths:
        log_func("❌ No videos to merge.")
        return False, "No videos selected"

    if len(video_paths) == 1:
        log_func("⚠️ Only one video selected. Copying to output...")
        try:
            shutil.copy2(video_paths[0], output_path)
            return True, output_path
        except Exception as e:
            return False, str(e)

    inputs = []
    filter_complex = ""
    w, h, fps = 1920, 1080, 30
    
    for i in range(len(video_paths)):
        inputs.extend(["-i", video_paths[i]])
        filter_complex += (
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={fps},format=yuv420p[v{i}];"
            f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}];"
        )
    
    for i in range(len(video_paths)):
        filter_complex += f"[v{i}][a{i}]"
    
    filter_complex += f"concat=n={len(video_paths)}:v=1:a=1[outv_raw][outa]"
    
    video_encoder = get_encoder("h264", use_gpu=use_gpu, log_func=log_func)
    
    hw_init = []
    final_v_map = "[outv_raw]"
    enc_args = ["-preset", "fast"]
    
    if "vaapi" in video_encoder:
        hw_init = ["-vaapi_device", "/dev/dri/renderD128"]
        filter_complex += f";[outv_raw]format=nv12,hwupload[outv]"
        final_v_map = "[outv]"
        enc_args = []
    elif "nvenc" in video_encoder:
        enc_args = ["-preset", "p4", "-rc", "vbr", "-cq", "23"]
    elif "amf" in video_encoder:
        enc_args = ["-rc", "vbr_peak", "-peak_bitrate", "5000k"]
    else:
        enc_args = ["-preset", "fast", "-crf", "23"]

    cmd = ["ffmpeg", "-y", "-hide_banner"]
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

# --- Audio Specialized Features ---

def replace_audio(video_path, audio_path, output_path, log_func=print, loop_audio=False):
    """
    Replaces the audio track of the video with the provided audio file.
    If loop_audio is True and the audio is shorter than the video, the
    audio will be looped to fill the full video length.
    """
    try:
        if not os.path.exists(video_path):
            return False, "Video file not found"
        if not os.path.exists(audio_path):
            return False, "Audio file not found"

        video_dur = get_video_duration(video_path, log_func)
        if loop_audio:
            if video_dur is None:
                log_func("⚠️ Could not detect video duration, falling back to -shortest")
                loop_audio = False

        if loop_audio:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-stream_loop", "-1", "-i", audio_path,
                "-c:v", "copy",
                "-map", "0:v:0", "-map", "1:a:0",
                "-t", str(video_dur),
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path, "-i", audio_path,
                "-c:v", "copy",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                output_path
            ]

        log_func(f"🚀 Replacing audio: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            creationflags=SUBPROCESS_FLAGS
        )

        for line in process.stdout:
            log_func(line.strip())

        process.wait()

        if process.returncode == 0:
            return True, output_path
        else:
            return False, "FFmpeg failed during audio replacement"

    except Exception as e:
        return False, str(e)

def normalize_audio(input_path, output_path, target_i=-14.0, log_func=print):
    """
    Normalizes audio using loudnorm (single pass).
    Target -14 LUFS is a good standard for web/streaming.
    """
    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "copy",
            "-af", f"loudnorm=I={target_i}:TP=-1.5:LRA=11",
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]

        log_func(f"🚀 Normalizing audio: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            creationflags=SUBPROCESS_FLAGS
        )

        for line in process.stdout:
            log_func(line.strip())

        process.wait()

        if process.returncode == 0:
            return True, output_path
        else:
            return False, "FFmpeg failed during normalization"

    except Exception as e:
        return False, str(e)

def remove_silence(input_path, output_path, db_threshold=-30, min_duration=0.5,
                   log_func=print, stop_event=None):
    """
    Removes silent parts from a video using segment-extract + concat.
    """
    try:
        total_duration = get_video_duration(input_path, log_func)
        if total_duration is None:
            return False, "Could not determine video duration"

        log_func(f"🔍 Detecting silence (threshold: {db_threshold}dB, min duration: {min_duration}s)...")

        detect_cmd = [
            "ffmpeg", "-hide_banner", "-i", input_path,
            "-af", f"silencedetect=noise={db_threshold}dB:d={min_duration}",
            "-f", "null", "-"
        ]
        proc = subprocess.run(detect_cmd, capture_output=True, text=True,
                              creationflags=SUBPROCESS_FLAGS)
        stderr_out = proc.stderr

        silence_periods = []
        pending_start = None
        for line in stderr_out.splitlines():
            if "silence_start" in line:
                m = re.search(r"silence_start:\s*([\d\.]+)", line)
                if m:
                    pending_start = float(m.group(1))
            elif "silence_end" in line and pending_start is not None:
                m = re.search(r"silence_end:\s*([\d\.]+)", line)
                if m:
                    end = float(m.group(1))
                    if end > pending_start:
                        silence_periods.append((pending_start, end))
                    pending_start = None

        if not silence_periods:
            if pending_start is not None:
                silence_periods.append((pending_start, total_duration))
            else:
                log_func("⚠️ No silence detected matching the given criteria — copying file.")
                shutil.copy2(input_path, output_path)
                return True, output_path
        elif pending_start is not None:
            silence_periods.append((pending_start, total_duration))

        silence_periods.sort(key=lambda x: x[0])
        
        for i, (s, e) in enumerate(silence_periods[:10]):
            log_func(f"  Silence {i+1}: {s:.2f}s → {e:.2f}s")
        if len(silence_periods) > 10:
            log_func(f"  ... and {len(silence_periods)-10} more.")

        keep_segments = []
        cursor = 0.0
        MIN_KEEP_DURATION = 0.1 
        
        for (s_start, s_end) in silence_periods:
            if s_start > cursor + MIN_KEEP_DURATION:
                keep_segments.append((cursor, s_start))
            cursor = max(cursor, s_end)

        if cursor < total_duration - MIN_KEEP_DURATION:
            keep_segments.append((cursor, total_duration))

        if not keep_segments:
            return False, "Nothing left after removing all silence — output would be empty."

        log_func(f"  Keeping {len(keep_segments)} segment(s) after filtering micro-fragments.")

        tmp_dir = tempfile.mkdtemp(prefix="silence_cut_")
        temp_files = []

        try:
            for idx, (seg_start, seg_end) in enumerate(keep_segments):
                if stop_event and stop_event.is_set():
                    log_func("🛑 Cancelled.")
                    return False, "Cancelled"

                temp_out = os.path.join(tmp_dir, f"_keep_{idx:04d}.mp4")
                temp_files.append(temp_out)

                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{seg_start:.6f}",
                    "-to", f"{seg_end:.6f}",
                    "-i", input_path,
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    temp_out
                ]
                log_func(f"  Extracting segment {idx + 1}/{len(keep_segments)} "
                         f"({seg_start:.2f}s → {seg_end:.2f}s)...")

                result = subprocess.run(cmd, capture_output=True, text=True,
                                        creationflags=SUBPROCESS_FLAGS)
                if result.returncode != 0:
                    log_func(f"  ⚠️ Segment {idx + 1} had extraction issues.")

            if len(temp_files) == 1:
                shutil.move(temp_files[0], output_path)
            else:
                concat_list = os.path.join(tmp_dir, "_concat_list.txt")
                with open(concat_list, "w") as f:
                    for tf in temp_files:
                        f.write(f"file '{tf}'\n")

                log_func(f"  Concatenating {len(temp_files)} segment(s)...")
                concat_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_list,
                    "-c", "copy",
                    output_path
                ]
                result = subprocess.run(concat_cmd, capture_output=True, text=True,
                                        creationflags=SUBPROCESS_FLAGS)
                if result.returncode != 0:
                    return False, f"Concat failed: {result.stderr[-500:]}"

            log_func(f"✅ Done! Saved to: {os.path.basename(output_path)}")
            return True, output_path

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    except Exception as e:
        import traceback
        log_func(f"❌ Exception: {traceback.format_exc()}")
        return False, str(e)
