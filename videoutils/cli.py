"""Command-line interface for headless compression/conversion."""

import os
import sys

from .processing import auto_compress, simple_convert


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

        success, result = simple_convert(input_file, output_file, vcodec, acodec, log_func=cli_log)
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
        success, result, _ = auto_compress(
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