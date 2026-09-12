"""Audio utilities: replace track, loudness-normalize, and remove silence."""

import os
import re
import shutil
import subprocess
import tempfile

from ..media import get_video_duration
from ..system import SUBPROCESS_FLAGS


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