# src/mixput/updater.py
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from packaging.version import parse as parse_version
import requests

from .version import __version__

REPO = "Under-our-Eyes/mixput"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
LASTEST_VERSION = "https://github.com/Under-our-Eyes/mixput/releases/latest"

def obtain_version():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mixput-updater",
    }

    resp = requests.get(API_URL, headers=headers, timeout=8)
    resp.raise_for_status()

    tag = resp.json().get("tag_name", "")
    return tag.lstrip('v') or None

def update_error(message: str) -> None:
    print(f"Update Error: {message}")
    sys.exit(1)


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def expected_asset_name() -> str | None:
    system = platform.system().lower()
    if system == "windows":
        return "mixput-windows-x64.zip"
    if system == "linux":
        return "mixput-linux-x64.zip"
    return None

def check_for_update() -> dict | None:
    try:
        resp = requests.get(
            API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "mixput-updater",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    tag = data.get("tag_name", "").lstrip("v")
    if not tag:
        return None

    if parse_version(tag) > parse_version(__version__):
        asset_name = expected_asset_name()
        for asset in data.get("assets", []):
            if asset.get("name") == asset_name:
                return {
                    "version": tag,
                    "url": asset["browser_download_url"],
                    "name": asset_name,
                }
    return None

def download_and_stage(url: str, filename: str) -> Path:
    stage_dir = Path(tempfile.mkdtemp(prefix="mixput_update_"))
    zip_path = stage_dir / filename
    extract_dir = stage_dir / "extracted"

    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            return extract_dir

def apply_update_and_restart(extracted_dir: Path) -> None:
    app_dir = get_app_dir()
    executable = Path(sys.executable).resolve()
    system = platform.system().lower()
    script_path = Path(tempfile.gettempdir()) / "update_mixput.bat"

    if system == "windows":
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        detached_process = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

        subprocess.Popen(
            ["cmd.exe", "/c", str(script_path)],
            creationflags=create_no_window | detached_process,
        )
    else:
        # En Linux copia sobre app_dir, restaura permisos de ejecución y relanza
        script_path = Path(tempfile.gettempdir()) / "update_mixput.sh"
        script_content = f"""#!/usr/bin/env bash
        sleep 2
        cp -rf "{extracted_dir}/." "{app_dir}/"
        chmod +x "{executable}"
        nohup "{executable}" >/dev/null 2>&1 &
        rm -f "$0"
        """
        script_path.write_text(script_content, encoding="utf-8")
        script_path.chmod(0o755)
        subprocess.Popen([str(script_path)], start_new_session=True)

    sys.exit(0)
