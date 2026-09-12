"""Video merging: concatenate multiple files into a single output."""

import os
import shutil
import subprocess

from ..media import get_encoder
from ..system import SUBPROCESS_FLAGS


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