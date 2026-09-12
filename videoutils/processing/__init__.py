"""Video processing engine.

This package groups all ffmpeg-backed operations into focused modules and
re-exports the public API so consumers can do::

    from videoutils import processing as logic

    logic.auto_compress(...)
    logic.merge_videos(...)
"""

from ..ffmpeg import install_ffmpeg, is_ffmpeg_installed
from ..media import (get_all_encoders, get_encoder, get_hardware_info,
                     get_video_duration, hms_to_seconds)
from .audio import normalize_audio, remove_silence, replace_audio
from .compression import auto_compress, compress_attempt
from .conversion import simple_convert
from .merging import merge_videos

__all__ = [
    # ffmpeg detection / install
    "is_ffmpeg_installed",
    "install_ffmpeg",
    # media probing / encoders
    "hms_to_seconds",
    "get_video_duration",
    "get_hardware_info",
    "get_all_encoders",
    "get_encoder",
    # processing features
    "compress_attempt",
    "auto_compress",
    "simple_convert",
    "merge_videos",
    "replace_audio",
    "normalize_audio",
    "remove_silence",
]