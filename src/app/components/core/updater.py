
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import requests
from packaging.version import InvalidVersion, Version

from .version import __version__


REPO = "Under-our-Eyes/mixput"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"

REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "mixput-updater",
}

MAX_DOWNLOAD_SIZE = 1024 * 1024 * 1024  # 1 GB
MAX_ARCHIVE_FILES = 20_000
MAX_EXTRACTED_SIZE = 1024 * 1024 * 1024  # 1 GB


def obtain_version() -> str:
    """Return the locally installed version without requiring Internet."""
    return __version__


def update_error(message: str) -> None:
    raise RuntimeError(f"Update Error: {message}")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[3]


def expected_asset_name() -> str | None:
    system = platform.system().lower()

    if system == "windows":
        return "mixput-windows-x64.zip"

    if system == "linux":
        return "mixput-linux-x64.zip"

    return None


def check_for_update() -> dict | None:
    """Check GitHub Releases for a newer version.

    Returns update information, or None if no update is available.
    Network errors are allowed to propagate so the UI can distinguish
    an unavailable service from an up-to-date installation.
    """
    asset_name = expected_asset_name()

    if asset_name is None:
        return None

    response = requests.get(
        API_URL,
        headers=REQUEST_HEADERS,
        timeout=(5, 12),
    )
    response.raise_for_status()

    release = response.json()
    tag = release.get("tag_name", "").strip()

    if not tag:
        return None

    try:
        latest_version = Version(tag.removeprefix("v"))
        current_version = Version(__version__)
    except InvalidVersion:
        return None

    if latest_version <= current_version:
        return None

    for asset in release.get("assets", []):
        if asset.get("name") != asset_name:
            continue

        download_url = asset.get("browser_download_url", "")

        if urlparse(download_url).scheme != "https":
            continue

        return {
            "version": str(latest_version),
            "url": download_url,
            "name": asset_name,
            "release_url": release.get("html_url"),
        }

    return None


def _validate_archive(archive: zipfile.ZipFile) -> None:
    """Reject unsafe paths, symbolic links and oversized archives."""
    entries = archive.infolist()

    if not entries or len(entries) > MAX_ARCHIVE_FILES:
        raise ValueError("Invalid number of files in update archive.")

    total_size = 0

    for entry in entries:
        member = PurePosixPath(entry.filename)

        if member.is_absolute() or ".." in member.parts:
            raise ValueError("Unsafe path found in update archive.")

        if not member.parts or ":" in member.parts[0]:
            raise ValueError("Invalid path found in update archive.")

        unix_mode = entry.external_attr >> 16

        if stat.S_ISLNK(unix_mode):
            raise ValueError("Symbolic links are not allowed in updates.")

        total_size += entry.file_size

        if total_size > MAX_EXTRACTED_SIZE:
            raise ValueError("Update archive exceeds the extraction limit.")


def download_and_stage(url: str, filename: str) -> Path:
    """Download, validate and extract an update into a temporary directory."""
    if urlparse(url).scheme != "https":
        raise ValueError("Update downloads must use HTTPS.")

    safe_filename = Path(filename).name

    if not safe_filename.lower().endswith(".zip"):
        raise ValueError("Unsupported update archive.")

    stage_dir = Path(tempfile.mkdtemp(prefix="mixput_update_"))
    zip_path = stage_dir / safe_filename
    extract_dir = stage_dir / "extracted"

    try:
        with requests.get(
            url,
            headers={"User-Agent": "mixput-updater"},
            stream=True,
            timeout=(10, 60),
        ) as response:
            response.raise_for_status()

            if urlparse(response.url).scheme != "https":
                raise ValueError("The download did not remain on HTTPS.")

            content_length = response.headers.get("Content-Length")

            if content_length and int(content_length) > MAX_DOWNLOAD_SIZE:
                raise ValueError("Update download exceeds the size limit.")

            downloaded = 0

            with zip_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=65_536):
                    if not chunk:
                        continue

                    downloaded += len(chunk)

                    if downloaded > MAX_DOWNLOAD_SIZE:
                        raise ValueError("Update download exceeds the size limit.")

                    output.write(chunk)

        with zipfile.ZipFile(zip_path, "r") as archive:
            _validate_archive(archive)

            corrupted_file = archive.testzip()

            if corrupted_file:
                raise ValueError(
                    f"Corrupted file in update archive: {corrupted_file}"
                )

            extract_dir.mkdir()
            archive.extractall(extract_dir)

        if not any(extract_dir.iterdir()):
            raise ValueError("The update archive is empty.")

        return extract_dir

    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise


def _apply_windows_update(
    extracted_dir: Path,
    app_dir: Path,
    executable: Path,
    stage_dir: Path,
) -> None:
    script_path = stage_dir / "apply_update.ps1"

    script_path.write_text(
        r"""
            param(
                [Parameter(Mandatory=$true)][string]$AppDir,
                [Parameter(Mandatory=$true)][string]$SourceDir,
                [Parameter(Mandatory=$true)][string]$ExePath,
                [Parameter(Mandatory=$true)][int]$ProcessId,
                [Parameter(Mandatory=$true)][string]$StageDir
            )

            $ErrorActionPreference = "Stop"

            try {
                Wait-Process -Id $ProcessId -ErrorAction SilentlyContinue

                if (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) {
                    throw "Update source directory does not exist."
                }

                if (-not (Test-Path -LiteralPath $AppDir -PathType Container)) {
                    throw "Application directory does not exist."
                }

                Copy-Item -Path (Join-Path $SourceDir '*') `
                    -Destination $AppDir -Recurse -Force

                if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
                    throw "Updated executable was not found."
                }

                Remove-Item -LiteralPath $StageDir -Recurse -Force
                Start-Process -FilePath $ExePath -WorkingDirectory $AppDir
            }
            catch {
                Write-Error $_
                exit 1
            }
            """,
        encoding="utf-8",
    )

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-AppDir",
            str(app_dir),
            "-SourceDir",
            str(extracted_dir),
            "-ExePath",
            str(executable),
            "-ProcessId",
            str(os.getpid()),
            "-StageDir",
            str(stage_dir),
        ],
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        ),
        close_fds=True,
    )


def _apply_linux_update(
    extracted_dir: Path,
    app_dir: Path,
    executable: Path,
    stage_dir: Path,
) -> None:
    import shlex

    script_path = stage_dir / "apply_update.sh"

    script_content = f"""#!/usr/bin/env bash
set -e

while kill -0 {os.getpid()} 2>/dev/null; do
    sleep 1
done

cp -a {shlex.quote(str(extracted_dir))}/. {shlex.quote(str(app_dir))}/
chmod +x {shlex.quote(str(executable))}

rm -rf {shlex.quote(str(stage_dir))}

nohup {shlex.quote(str(executable))} >/dev/null 2>&1 &
"""

    script_path.write_text(script_content, encoding="utf-8")
    script_path.chmod(0o755)

    subprocess.Popen(
        ["/bin/bash", str(script_path)],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def apply_update_and_restart(extracted_dir: Path) -> None:
    """Apply a staged update after the current application exits."""
    if not is_frozen():
        raise RuntimeError(
            "Automatic updates are only available in packaged installations."
        )

    extracted_dir = extracted_dir.resolve()

    if not extracted_dir.is_dir():
        raise ValueError("The extracted update directory does not exist.")

    app_dir = get_app_dir()
    executable = Path(sys.executable).resolve()
    stage_dir = extracted_dir.parent

    if platform.system().lower() == "windows":
        _apply_windows_update(
            extracted_dir,
            app_dir,
            executable,
            stage_dir,
        )

    elif platform.system().lower() == "linux":
        _apply_linux_update(
            extracted_dir,
            app_dir,
            executable,
            stage_dir,
        )

    else:
        raise RuntimeError("Automatic updates are not supported on this OS.")

    sys.exit(0)
