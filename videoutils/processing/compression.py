"""Video compression: target-size-aware encoding with auto resolution scaling."""

import os
import platform
import re
import subprocess

from ..media import get_encoder, get_video_duration, hms_to_seconds
from ..system import SUBPROCESS_FLAGS


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

    if isinstance(res, str) and "x" in res.lower():
        try:
            w, h = res.lower().split("x")
            v_filter = f"scale={w}:{h},format=yuv420p"
            # For hardware acceleration paths that need a numeric height fallback,
            # we'll keep a 'base_res' int as well.
            base_res = int(h) if h.isdigit() else 720
        except:
            v_filter = f"scale=-2:{res},format=yuv420p"
            base_res = int(res) if isinstance(res, int) else 720
    else:
        v_filter = f"scale=-2:{res},format=yuv420p"
        base_res = res

    if v_enc == "h261":
        h261_res = 288 if base_res >= 288 else 144
        w261 = 352 if h261_res == 288 else 176
        v_filter = f"scale={w261}:{h261_res},format=yuv420p,fps=30000/1001"
    elif v_enc == "roqvideo":
        v_filter = f"scale='trunc(iw/16)*16':'trunc(ih/16)*16',format=yuv420p,fps=30"
    elif v_enc == "h263":
        v_filter = f"scale='bitand(iw, -16)':'bitand(ih, -16)',format=yuv420p"
    elif v_enc == "cinepak":
        v_filter = f"scale='bitand(iw, -4)':'bitand(ih, -4)',format=yuv420p,fps=30"
    elif v_enc == "snow":
        v_filter = f"scale=-2:{base_res},format=yuv420p"

    if advanced_params and advanced_params.get("denoise"):
        ls = advanced_params.get("denoise_luma", 4)
        cs = advanced_params.get("denoise_chroma", 3)
        lt = advanced_params.get("denoise_luma_temp", ls*1.5)
        ct = advanced_params.get("denoise_chroma_temp", cs*1.5)
        # hqdn3d=luma_spatial:chroma_spatial:luma_temporal:chroma_temporal
        v_filter += f",hqdn3d={ls}:{cs}:{lt}:{ct}"

    ten_bit = advanced_params.get("ten_bit") if advanced_params else False
    override_colorspace = advanced_params.get("colorspace") if advanced_params else None

    if override_colorspace:
        # If user explicitly chose a colorspace, replace the default format
        v_filter = re.sub(r"format=\S+?", f"format={override_colorspace}", v_filter, count=1)
    elif ten_bit:
        v_filter = v_filter.replace("format=yuv420p", "format=yuv420p10le")

    # Frame rate
    fps_value = advanced_params.get("fps") if advanced_params else None
    if fps_value:
        v_filter += f",fps={fps_value}"

    if 'vaapi' in v_enc:
        fmt = "p010" if ten_bit else "nv12"
        base_filter = ""
        if advanced_params and advanced_params.get("denoise"):
            base_filter = "hqdn3d=2:2:7:7,"
        v_filter = f"{base_filter}format={fmt},hwupload,scale_vaapi=w=-2:h={base_res}"

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

    audio_codec_choice = advanced_params.get("audio_codec", "aac") if advanced_params else "aac"
    if not audio_codec_choice:
        audio_codec_choice = "aac"

    audio_args = ['-c:a', audio_codec_choice, '-b:a', '64k']
    if audio_codec_choice == "libopus":
        audio_args = ['-c:a', 'libopus', '-b:a', '48k', '-vbr', 'on', '-frame_duration', '60']
    elif audio_codec_choice == "copy":
        audio_args = ['-c:a', 'copy']
    elif audio_codec_choice in ("pcm_s16le", "pcm_s24le", "flac", "alac"):
        audio_args = ['-c:a', audio_codec_choice]  # lossless, no bitrate arg

    # --- Audio Filters ---
    audio_filters = []
    hp = advanced_params.get("audio_highpass", 0) if advanced_params else 0
    lp = advanced_params.get("audio_lowpass", 22050) if advanced_params else 22050
    if hp > 0: audio_filters.append(f"highpass=f={hp}")
    if lp < 22050: audio_filters.append(f"lowpass=f={lp}")

    a_filter_args = []
    if audio_filters:
        a_filter_args = ['-af', ",".join(audio_filters)]

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

            strip_meta = advanced_params.get("strip_metadata", False) if advanced_params else False
            meta_args = ['-map_metadata', '-1'] if strip_meta else []

            # Custom Metadata
            if not strip_meta and advanced_params:
                m_title = advanced_params.get("meta_title", "")
                m_author = advanced_params.get("meta_author", "")
                if m_title: meta_args += ['-metadata', f"title={m_title}"]
                if m_author: meta_args += ['-metadata', f"author={m_author}", '-metadata', f"artist={m_author}"]

            if p == 0:
                log_func(f"Encoding...", replace_last=True)
                cur_cmd = ['ffmpeg', '-y', '-hide_banner', '-stats'] + hw_init + ['-i', input_file] + \
                          ['-vf', v_filter] + enc_args + audio_args + a_filter_args + meta_args + [output_file]
            elif p == 1:
                log_func(f"Starting Pass 1...", replace_last=True)
                cur_cmd = ['ffmpeg', '-y', '-hide_banner', '-stats'] + hw_init + ['-i', input_file] + \
                          ['-vf', v_filter] + enc_args + ['-pass', '1'] + ['-an', '-f', 'null', '/dev/null']
            else:
                log_func(f"Starting Pass 2...", replace_last=True)
                cur_cmd = ['ffmpeg', '-y', '-hide_banner', '-stats'] + hw_init + ['-i', input_file] + \
                          ['-vf', v_filter] + enc_args + ['-pass', '2'] + audio_args + a_filter_args + meta_args + [output_file]

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


def auto_compress(input_file, target_mb, codec, use_gpu, output_file=None, log_func=print, stop_event=None, preview_path=None, progress_callback=None, advanced_params=None, res_params=None):
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

    # Build the resolution list to attempt based on res_params
    res_params = res_params or {}
    res_mode = res_params.get("mode", "auto")

    if res_mode == "custom":
        res_list = [res_params.get("fixed", "1280x720")]
    elif res_mode == "fixed":
        # Use a single fixed resolution — no fallback scaling
        fixed_res = res_params.get("fixed", 1080)
        res_list = [fixed_res]
    else:
        # Auto: use progressive scale-down list, bounded by min/max
        all_res = [2160, 1440, 1080, 720, 480, 360, 240]
        res_max = res_params.get("max")
        res_min = res_params.get("min")
        res_list = [r for r in all_res if (res_max is None or r <= res_max) and (res_min is None or r >= res_min)]
        if not res_list:
            # Fallback if user set an impossible range
            res_list = [1080, 720, 480, 360]

    last_result_size = None  # Tracks most recent output size (for "too big" detection)

    for res in res_list:
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
                return True, output_file, None
            else:
                last_result_size = final_size
                if res_mode == "fixed":
                    # In fixed mode there's only one attempt, report size and stop
                    smart_log(f"⚠️ Result too large ({final_size:.2f} MB). Fixed resolution mode — no fallback.")
                    break
                smart_log(f"⚠️ Result too large ({final_size:.2f}MB). Trying lower resolution...")
        elif not (stop_event and stop_event.is_set()):
            smart_log(f"❌ Encoding failed at {res}p. Skipping...")

    try: os.remove(preview_path) if preview_path and os.path.exists(preview_path) else None
    except: pass

    # If last_result_size is set it means encoding succeeded but was too large — return it for the UI
    return False, None, last_result_size