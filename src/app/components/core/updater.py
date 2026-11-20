"""Safe staged updater with progress reporting and restart diagnostics."""
from __future__ import annotations
import os, platform, shutil, stat, subprocess, sys, tempfile, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
import requests
from packaging.version import InvalidVersion, Version
from .version import __version__

REPO = "Under-our-Eyes/mixput"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
REQUEST_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "mixput-updater"}
MAX_DOWNLOAD_SIZE = 1024 * 1024 * 1024
MAX_ARCHIVE_FILES = 20_000
MAX_EXTRACTED_SIZE = 1024 * 1024 * 1024

def _report(callback, phase, downloaded=0, total=0, message=""):
    if callback:
        try: callback(phase, downloaded, total, message)
        except Exception: pass

def obtain_version(): return __version__
def is_frozen(): return bool(getattr(sys, "frozen", False))
def get_app_dir(): return Path(sys.executable).resolve().parent if is_frozen() else Path(__file__).resolve().parents[3]

def expected_asset_name():
    system = platform.system().lower()
    return "mixput-windows-x64.zip" if system == "windows" else "mixput-linux-x64.zip" if system == "linux" else None

def check_for_update():
    asset_name = expected_asset_name()
    if not asset_name: return None
    response = requests.get(API_URL, headers=REQUEST_HEADERS, timeout=(5, 12))
    response.raise_for_status()
    release = response.json()
    tag = release.get("tag_name", "").strip()
    if not tag: return None
    try:
        latest, current = Version(tag.removeprefix("v")), Version(__version__)
    except InvalidVersion: return None
    if latest <= current: return None
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            url = asset.get("browser_download_url", "")
            if urlparse(url).scheme == "https":
                return {"version": str(latest), "url": url, "name": asset_name, "release_url": release.get("html_url")}
    raise RuntimeError(f"Release {tag} exists, but its {asset_name} asset is missing.")

def _validate_archive(archive):
    entries = archive.infolist()
    if not entries or len(entries) > MAX_ARCHIVE_FILES: raise ValueError("Invalid number of files in update archive.")
    total_size = 0
    for entry in entries:
        member = PurePosixPath(entry.filename)
        if member.is_absolute() or ".." in member.parts: raise ValueError("Unsafe path found in update archive.")
        if not member.parts or ":" in member.parts[0]: raise ValueError("Invalid path found in update archive.")
        if stat.S_ISLNK(entry.external_attr >> 16): raise ValueError("Symbolic links are not allowed in updates.")
        total_size += entry.file_size
        if total_size > MAX_EXTRACTED_SIZE: raise ValueError("Update archive exceeds the extraction limit.")

def download_and_stage(url, filename, progress_callback=None):
    if urlparse(url).scheme != "https": raise ValueError("Update downloads must use HTTPS.")
    safe_filename = Path(filename).name
    if not safe_filename.lower().endswith(".zip"): raise ValueError("Unsupported update archive.")
    stage_dir = Path(tempfile.mkdtemp(prefix="mixput_update_"))
    zip_path, extract_dir = stage_dir / safe_filename, stage_dir / "extracted"
    try:
        _report(progress_callback, "download", 0, 0, "Connecting to release server…")
        with requests.get(url, headers={"User-Agent": "mixput-updater"}, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            if urlparse(response.url).scheme != "https": raise ValueError("The download did not remain on HTTPS.")
            total = int(response.headers.get("Content-Length") or 0)
            if total > MAX_DOWNLOAD_SIZE: raise ValueError("Update download exceeds the size limit.")
            downloaded = 0
            with zip_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk: continue
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_SIZE: raise ValueError("Update download exceeds the size limit.")
                    output.write(chunk)
                    message = f"Downloaded {downloaded / 1048576:.1f} MB" + (f" of {total / 1048576:.1f} MB" if total else "")
                    _report(progress_callback, "download", downloaded, total, message)
        _report(progress_callback, "verify", 0, 0, "Verifying archive integrity…")
        with zipfile.ZipFile(zip_path) as archive:
            _validate_archive(archive)
            bad = archive.testzip()
            if bad: raise ValueError(f"Corrupted file in update archive: {bad}")
            expected = "mixput.exe" if platform.system().lower() == "windows" else "mixput"
            names = [Path(name).name.lower() for name in archive.namelist() if not name.endswith("/")]
            if expected not in names: raise ValueError(f"Update archive does not contain {expected}.")
            _report(progress_callback, "extract", 0, 0, "Extracting update files…")
            extract_dir.mkdir()
            archive.extractall(extract_dir)
        if not any(extract_dir.iterdir()): raise ValueError("The update archive is empty.")
        _report(progress_callback, "ready", 1, 1, "Update downloaded and verified.")
        return extract_dir
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise

def _apply_windows_update(extracted_dir, app_dir, executable, stage_dir):
    import os as _os
    log_dir = Path(_os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Mixput" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "update.log"
    script = stage_dir / "apply_update.ps1"
    script.write_text(r"""
param([string]$AppDir,[string]$SourceDir,[string]$ExePath,[int]$ProcessId,[string]$StageDir,[string]$LogPath)
$ErrorActionPreference='Stop'
function Log([string]$m) { Add-Content -LiteralPath $LogPath -Value ("[{0}] {1}" -f (Get-Date -Format o),$m) }
try {
 $id=[Security.Principal.WindowsIdentity]::GetCurrent()
 $p=[Security.Principal.WindowsPrincipal]::new($id)
 if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Log 'Requesting administrator permission (UAC).'
  $a=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-AppDir',$AppDir,'-SourceDir',$SourceDir,'-ExePath',$ExePath,'-ProcessId',$ProcessId,'-StageDir',$StageDir,'-LogPath',$LogPath)
  Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $a
  exit 0
 }
 Log 'Elevated updater started; waiting for Mixput to exit.'
 try { Wait-Process -Id $ProcessId -Timeout 90 -ErrorAction Stop } catch {
  if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) { throw 'Timed out waiting for Mixput to exit.' }
 }
 if (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) { throw 'Update source directory is missing.' }
 if (-not (Test-Path -LiteralPath $AppDir -PathType Container)) { throw 'Application directory is missing.' }
 $sourceExe=Join-Path $SourceDir 'mixput.exe'
 if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) { throw 'Archive has no root-level mixput.exe.' }
 Copy-Item -LiteralPath $sourceExe -Destination $ExePath -Force
 if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) { throw 'Updated executable was not installed.' }
 Log 'Update copied. Starting updated Mixput.'
 Start-Process -FilePath $ExePath -WorkingDirectory $AppDir
 Log 'Updated Mixput process launched.'
} catch {
 Log ('ERROR: '+$_.Exception.Message)
 try { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(('Mixput update failed: '+$_.Exception.Message+[Environment]::NewLine+'Log: '+$LogPath),'Mixput updater') | Out-Null } catch {}
 exit 1
}
""", encoding="utf-8")
    subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script),
        "-AppDir",str(app_dir),"-SourceDir",str(extracted_dir),"-ExePath",str(executable),
        "-ProcessId",str(os.getpid()),"-StageDir",str(stage_dir),"-LogPath",str(log_path)],
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0), close_fds=True)

def _apply_linux_update(extracted_dir, app_dir, executable, stage_dir):
    import shlex
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home()/".local"/"state"))
    log_dir = state/"mixput"/"logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir/"update.log"
    q = shlex.quote
    script_path = stage_dir/"apply_update.sh"
    script = f"""#!/usr/bin/env bash
set -Eeuo pipefail
LOG={q(str(log_path))}
log() {{ printf '[%s] %s\\n' "$(date --iso-8601=seconds)" "$*" >> "$LOG"; }}
trap 'code=$?; log "ERROR at line $LINENO (exit $code)"' ERR
log 'Updater started; waiting for Mixput to exit.'
while kill -0 {os.getpid()} 2>/dev/null; do sleep 1; done
SOURCE={q(str(extracted_dir))}/mixput
if [[ ! -f "$SOURCE" ]]; then log 'ERROR: archive has no root-level mixput executable.'; exit 2; fi
install -m 755 "$SOURCE" {q(str(executable))}
if [[ ! -x {q(str(executable))} ]]; then log 'ERROR: updated executable is not executable.'; exit 3; fi
log 'Update copied. Launching updated Mixput.'
nohup {q(str(executable))} >> "$LOG" 2>&1 < /dev/null &
NEW_PID=$!
sleep 2
if ! kill -0 "$NEW_PID" 2>/dev/null; then log 'ERROR: Mixput exited immediately; inspect startup output above.'; exit 4; fi
log "Updated Mixput started with PID $NEW_PID."
"""
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o700)
    with log_path.open("a",encoding="utf-8") as stream: stream.write("\n--- update started ---\n")
    subprocess.Popen(["/bin/bash",str(script_path)],start_new_session=True,stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)

def apply_update_and_restart(extracted_dir, progress_callback=None):
    if not is_frozen(): raise RuntimeError("Automatic updates are only available in packaged installations.")
    extracted_dir = Path(extracted_dir).resolve()
    if not extracted_dir.is_dir(): raise ValueError("The extracted update directory does not exist.")
    app_dir, executable = get_app_dir(), Path(sys.executable).resolve()
    stage_dir = extracted_dir.parent
    _report(progress_callback,"install",0,0,"Preparing installer and restart helper…")
    if platform.system().lower() == "windows": _apply_windows_update(extracted_dir,app_dir,executable,stage_dir)
    elif platform.system().lower() == "linux": _apply_linux_update(extracted_dir,app_dir,executable,stage_dir)
    else: raise RuntimeError("Automatic updates are not supported on this OS.")
    _report(progress_callback,"restart",1,1,"Updater started. Mixput will close and reopen.")
    sys.exit(0)
