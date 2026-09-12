"""Media probing and encoder resolution: ffprobe/ffmpeg interrogation helpers."""

import os
import platform
import subprocess

from .system import SUBPROCESS_FLAGS


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