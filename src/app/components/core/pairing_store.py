"""Persistent, per-user pairing identity and authorization storage."""
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path


def _data_directory():
    if os.name == "nt":
        root = os.environ.get("APPDATA")
        base = Path(root) if root else Path.home() / "AppData" / "Roaming"
    elif __import__("sys").platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        root = os.environ.get("XDG_CONFIG_HOME")
        base = Path(root) if root else Path.home() / ".config"
    directory = base / "Mixput"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    return directory


class PairingStore:
    """Store only local identity and explicitly approved peer credentials."""

    def __init__(self, path=None):
        self.path = Path(path) if path else _data_directory() / "pairing.json"
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        identity = data.get("device_id")
        if not isinstance(identity, str) or len(identity) != 32:
            identity = uuid.uuid4().hex
        clients = data.get("authorized_clients")
        hosts = data.get("paired_hosts")
        return {
            "device_id": identity,
            "authorized_clients": clients if isinstance(clients, dict) else {},
            "paired_hosts": hosts if isinstance(hosts, dict) else {},
        }

    @property
    def device_id(self):
        return self._data["device_id"]

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="pairing-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self._data, stream, separators=(",", ":"), ensure_ascii=True)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def authorize_client(self, device_id, name, address, token):
        with self._lock:
            self._data["authorized_clients"][device_id] = {
                "name": str(name)[:64],
                "address": str(address)[:64],
                "token": token,
            }
            self._save()

    def set_client_virtual_ip(self, device_id, virtual_ip):
        with self._lock:
            record = self._data["authorized_clients"].get(device_id)
            if not isinstance(record, dict):
                return False
            record["virtual_ip"] = str(virtual_ip)
            self._save()
            return True

    def get_authorized_client(self, device_id):
        with self._lock:
            item = self._data["authorized_clients"].get(device_id)
            return dict(item) if isinstance(item, dict) else None

    def list_authorized_clients(self):
        with self._lock:
            return [
                {"id": key, **value}
                for key, value in self._data["authorized_clients"].items()
                if isinstance(value, dict)
            ]

    def revoke_client(self, device_id):
        with self._lock:
            removed = self._data["authorized_clients"].pop(device_id, None)
            if removed is not None:
                self._save()
            return removed is not None

    @staticmethod
    def _endpoint(host, port):
        return f"{host.strip()}:{int(port)}"

    def save_host(self, host, port, host_id, name, token):
        with self._lock:
            self._data["paired_hosts"][self._endpoint(host, port)] = {
                "host_id": str(host_id),
                "name": str(name)[:64],
                "token": token,
            }
            self._save()

    def get_host(self, host, port):
        with self._lock:
            item = self._data["paired_hosts"].get(self._endpoint(host, port))
            return dict(item) if isinstance(item, dict) else None

    def forget_host(self, host, port):
        with self._lock:
            removed = self._data["paired_hosts"].pop(self._endpoint(host, port), None)
            if removed is not None:
                self._save()
            return removed is not None
