"""Media format/container conversion and audio extraction."""

import re
import subprocess

from ..media import get_video_duration
from ..system import SUBPROCESS_FLAGS


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