"""FFmpeg binary detection and installation helpers."""

import os
import platform
import subprocess

from .system import CREATE_NEW_CONSOLE, SUBPROCESS_FLAGS


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