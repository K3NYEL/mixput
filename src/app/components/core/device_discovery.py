"""UDP broadcast discovery for Mixput peers on the local IPv4 network."""

import ipaddress
import json
import socket
import threading
import time
import uuid

import psutil

DISCOVERY_PORT = 45821
DISCOVERY_INTERVAL = 2.0
PEER_TIMEOUT = 8.0
MAX_PACKET_BYTES = 1024
PROTOCOL_VERSION = 1


def _broadcast_addresses():
    """Return directed broadcast addresses for active IPv4 interfaces."""
    targets = {"255.255.255.255"}
    stats = psutil.net_if_stats()
    for interface, entries in psutil.net_if_addrs().items():
        status = stats.get(interface)
        if not status or not status.isup:
            continue
        for entry in entries:
            if entry.family != socket.AF_INET or not entry.netmask:
                continue
            try:
                address = ipaddress.IPv4Address(entry.address)
                mask = ipaddress.IPv4Address(entry.netmask)
                if (
                    address.is_loopback
                    or address.is_link_local
                    or address.is_unspecified
                ):
                    continue
                network = ipaddress.IPv4Network(f"{address}/{mask}", strict=False)
                if network.prefixlen < 31:
                    targets.add(str(network.broadcast_address))
            except ipaddress.AddressValueError, ipaddress.NetmaskValueError:
                continue
    return targets


class DeviceDiscovery:
    """Announce this Mixput instance and listen for peers without exposing secrets."""

    def __init__(self, on_devices=None, tcp_port=8080):
        self.on_devices = on_devices or (lambda devices: None)
        self.device_id = uuid.uuid4().hex
        self.device_name = socket.gethostname()[:64]
        self.tcp_port = int(tcp_port)
        self.sharing = False
        self.running = False
        self._socket = None
        self._thread = None
        self._lock = threading.RLock()
        self._peers = {}

    def start(self):
        with self._lock:
            if self.running:
                return False
            self.running = True
            self._thread = threading.Thread(
                target=self._run, name="MixputDiscovery", daemon=True
            )
            self._thread.start()
        return True

    def set_endpoint(self, tcp_port=None, sharing=None):
        with self._lock:
            if tcp_port is not None:
                self.tcp_port = int(tcp_port)
            if sharing is not None:
                self.sharing = bool(sharing)

    def _packet(self):
        with self._lock:
            port = self.tcp_port
            sharing = self.sharing
        return json.dumps(
            {
                "app": "mixput",
                "protocol": PROTOCOL_VERSION,
                "type": "announce",
                "device_id": self.device_id,
                "name": self.device_name,
                "port": port,
                "sharing": sharing,
            },
            separators=(",", ":"),
        ).encode("utf-8")

    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(0.35)
            self._socket = sock
            next_announce = 0.0
            next_publish = 0.0

            while self.running:
                now = time.monotonic()
                if now >= next_announce:
                    packet = self._packet()
                    for target in _broadcast_addresses():
                        try:
                            sock.sendto(packet, (target, DISCOVERY_PORT))
                        except OSError:
                            continue
                    next_announce = now + DISCOVERY_INTERVAL

                try:
                    payload, address = sock.recvfrom(MAX_PACKET_BYTES + 1)
                    if len(payload) <= MAX_PACKET_BYTES:
                        self._accept_packet(payload, address[0])
                except socket.timeout:
                    pass
                except OSError:
                    if self.running:
                        time.sleep(0.2)

                now = time.monotonic()
                expired = [
                    device_id
                    for device_id, peer in self._peers.items()
                    if now - peer["last_seen"] > PEER_TIMEOUT
                ]
                for device_id in expired:
                    self._peers.pop(device_id, None)

                if now >= next_publish:
                    self._publish()
                    next_publish = now + 1.0
        except OSError:
            # Discovery is best-effort; the manual IP connection remains available.
            self.running = False
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self._socket = None
            self._publish()

    def _accept_packet(self, payload, source_ip):
        try:
            message = json.loads(payload.decode("utf-8"))
        except UnicodeDecodeError, json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        if (
            message.get("app") != "mixput"
            or message.get("protocol") != PROTOCOL_VERSION
            or message.get("type") != "announce"
        ):
            return

        device_id = message.get("device_id")
        name = message.get("name")
        port = message.get("port")
        sharing = message.get("sharing")
        if (
            not isinstance(device_id, str)
            or len(device_id) != 32
            or device_id == self.device_id
            or not isinstance(name, str)
            or not name
            or not isinstance(port, int)
            or isinstance(port, bool)
            or not 1 <= port <= 65535
            or not isinstance(sharing, bool)
        ):
            return

        try:
            ip = ipaddress.ip_address(source_ip)
            if ip.version != 4 or ip.is_loopback or ip.is_unspecified:
                return
        except ValueError:
            return

        self._peers[device_id] = {
            "id": device_id,
            "name": name[:64],
            "ip": source_ip,
            "port": port,
            "sharing": sharing,
            "last_seen": time.monotonic(),
        }

    def _publish(self):
        devices = []
        for peer in self._peers.values():
            devices.append(
                {
                    "id": peer["id"],
                    "name": peer["name"],
                    "ip": peer["ip"],
                    "port": peer["port"],
                    "sharing": peer["sharing"],
                }
            )
        devices.sort(key=lambda item: (not item["sharing"], item["name"].lower()))
        try:
            self.on_devices(devices)
        except Exception:
            pass

    def stop(self):
        self.running = False
        sock = self._socket
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
