"""Application self-update system: checks releases, downloads, and applies updates."""

import os
import platform
import subprocess
import sys
import tempfile

import httpx

from .system import open_folder


class UpdateManager:
    """Handles background version checks, downloads, and applying updates."""

    def __init__(self, page, current_version: str):
        self.page = page
        self.current_version = current_version
        self.latest_release = None
        self.update_available = False
        self.download_path = None
        self.repo = "hapatapa/videoutils"
        self.is_downloading = False
        self.download_progress = 0.0

    async def check_for_updates(self):
        # Don't check if we're in a dev build unless forced (optional)
        if self.current_version == "Dev Build":
            return False

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                response = await client.get(f"https://api.github.com/repos/{self.repo}/releases/latest")
                if response.status_code == 200:
                    data = response.json()
                    latest_tag = data.get("tag_name", "").replace("v", "")

                    # Simple semantic version comparison could be better, but string comparison
                    # works if we always increment.
                    if latest_tag and latest_tag != self.current_version:
                        self.latest_release = data
                        self.update_available = True
                        return True
        except Exception as e:
            print(f"Update check failed: {e}")
        return False

    def get_asset_info(self):
        if not self.latest_release: return None, None
        assets = self.latest_release.get("assets", [])
        sys_name = platform.system()

        target_name = ""
        if sys_name == "Windows":
            target_name = "VideoUtilities-Windows.exe"
        elif sys_name == "Linux":
            # Detect if we are running from a .run (self-extractor) or the Native (tar.gz) version
            # MAKESELF_PATH is set by our custom build wrapper in build.yml
            exec_path = sys.executable
            if os.environ.get("MAKESELF_PATH") or exec_path.startswith("/tmp") or "/tmp/" in exec_path or "/.mount_" in exec_path:
                target_name = "VideoUtilities-Linux.run"
            else:
                # If running from a home directory or /opt without being in /tmp, assume Native
                target_name = "VideoUtilities-Linux-Native.tar.gz"

        for asset in assets:
            if asset.get("name") == target_name:
                return asset.get("browser_download_url"), asset.get("size")
        return None, None

    async def download_update(self, on_progress=None):
        url, size = self.get_asset_info()
        if not url: return False

        self.is_downloading = True
        self.download_path = os.path.join(tempfile.gettempdir(), os.path.basename(url))

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
                async with client.stream("GET", url) as response:
                    total_bytes = int(response.headers.get("Content-Length", size or 0))
                    bytes_downloaded = 0

                    with open(self.download_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
                            if total_bytes > 0:
                                self.download_progress = bytes_downloaded / total_bytes
                                if on_progress: on_progress(self.download_progress)

            self.is_downloading = False
            return True
        except Exception as e:
            self.is_downloading = False
            print(f"Download failed: {e}")
            return False

    def install_and_restart(self):
        """Prepare system-specific replacement script and exit."""
        if not self.download_path or not os.path.exists(self.download_path):
            return

        current_exe = sys.executable
        # Check if we have the original .run path from makeself (passed via build wrapper)
        makeself_path = os.environ.get("MAKESELF_PATH")
        is_using_makeself = makeself_path and os.path.exists(makeself_path)

        if is_using_makeself:
            current_exe = makeself_path

        new_asset = self.download_path
        sys_name = platform.system()

        # Handle formats that can't be auto-replaced easily (folders/tarballs)
        if sys_name == "Linux":
            if new_asset.endswith(".tar.gz"):
                open_folder(new_asset)
                return

            # If we're in /tmp but DON'T have a MAKESELF_PATH, we can't auto-replace
            is_in_tmp = current_exe.startswith("/tmp") or "/tmp/" in current_exe or "/.mount_" in current_exe
            if is_in_tmp and not is_using_makeself:
                open_folder(new_asset)
                return

        if sys_name == "Windows":
            # Create a more robust batch file that retries deletion (handles AV locks)
            # IMPORTANT: We MUST unset _MEIPASS so the new process doesn't try to use
            # the old extraction folder (which leads to "Failed to load Python DLL").
            batch_path = os.path.join(tempfile.gettempdir(), "update_vu.bat")
            with open(batch_path, "w") as f:
                f.write(f"@echo off\n")
                f.write(f"timeout /t 2 /nobreak > nul\n")
                f.write(f":retry_del\n")
                f.write(f"del /f /q \"{current_exe}\"\n")
                f.write(f"if exist \"{current_exe}\" (\n")
                f.write(f"    timeout /t 1 /nobreak > nul\n")
                f.write(f"    goto retry_del\n")
                f.write(f")\n")
                f.write(f"move /y \"{new_asset}\" \"{current_exe}\"\n")
                # Clear PyInstaller environment to ensure clean extraction for the new version
                f.write(f"set _MEIPASS=\n")
                f.write(f"start \"\" \"{current_exe}\"\n")
                f.write(f"del \"%~f0\"\n")

            # Start the batch hidden
            subprocess.Popen(
                ["cmd.exe", "/c", batch_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NO_WINDOW
            )
            sys.exit(0)

        elif sys_name == "Linux":
            # Create a shell script to handle replacement
            sh_path = os.path.join(tempfile.gettempdir(), "update_vu.sh")
            with open(sh_path, "w") as f:
                f.write(f"#!/bin/bash\n")
                f.write(f"sleep 2\n")
                f.write(f"mv -f \"{new_asset}\" \"{current_exe}\"\n")
                f.write(f"chmod +x \"{current_exe}\"\n")
                # Clear environment variables that might interfere with a clean relaunch
                f.write(f"unset _MEIPASS\n")
                # For makeself, we don't necessarily want to relaunch the *installer*
                # but in most cases, it's what the user wants to see next.
                f.write(f"\"{current_exe}\" &\n")
                f.write(f"rm \"$0\"\n")
            os.chmod(sh_path, 0o755)
            subprocess.Popen(["/bin/bash", sh_path])
            sys.exit(0)