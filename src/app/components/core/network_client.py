"""Authenticated Mixput client with server-managed horizontal topology and group chat."""
import base64
import ipaddress
import os
import socket
import threading
from app.components.core.input_protocol import PROTOCOL_VERSION, EVENT_TYPES, ProtocolError
from app.components.core.pairing_handshake import (
    PAIRING_VERSION, send_control, receive_control, new_ephemeral_key,
    derive_pairing_key, decrypt_session_token,
)
from app.components.core.pairing_store import PairingStore
from app.components.core.secure_transport import SecureChannel

MAX_CHAT_LENGTH = 1000


class NetworkClient:
    def __init__(self, on_message=None, on_status=None, on_chat=None, on_session=None,
                 input_backend=None, pairing_store=None):
        self.on_message = on_message or (lambda message: None)
        self.on_status = on_status or (lambda status: None)
        self.on_chat = on_chat or (lambda message: None)
        self.on_session = on_session or (lambda state: None)
        self.input_backend = input_backend
        self.pairings = pairing_store or PairingStore()
        self.running = False
        self.sock = None
        self._channel = None
        self._thread = None
        self._lock = threading.RLock()
        self._control_owner = "host"
        self._ownership_epoch = -1
        self._last_input_sequence = 0
        self._local_mode = False
        self._device_id = self.pairings.device_id
        self._index = 1
        self._devices = []
        self._virtual_ip = None
        self._virtual_network = None
        if self.input_backend is not None:
            self.input_backend.on_event = self._send_input
            self.input_backend.on_edge = self._on_local_edge
            self.input_backend.on_toggle_local = self.toggle_local_mode

    @property
    def virtual_ip(self):
        with self._lock:
            return self._virtual_ip

    @property
    def local_mode(self):
        with self._lock:
            return self._local_mode

    def toggle_local_mode(self):
        return self.set_local_mode(not self.local_mode)

    def set_local_mode(self, enabled):
        enabled = bool(enabled)
        with self._lock:
            if self._local_mode == enabled:
                return False
            self._local_mode = enabled
        if self.input_backend:
            self.input_backend.release_all()
        self.on_message(f"[Mixput] Local mode {'enabled' if enabled else 'disabled'}.")
        self.on_session({
            "devices": self._devices, "owner": self._control_owner,
            "index": self._index, "local_mode": enabled,
        })
        return True

    def connect(self, host, port=8080):
        if self.running:
            return False
        if not host:
            self.on_message("[Mixput] Select or enter the host laptop address.")
            return False
        self.running = True
        self.on_status("connecting")
        self._thread = threading.Thread(target=self._run, args=(host, port), daemon=True, name="MixputClient")
        self._thread.start()
        return True

    def _send_input(self, event):
        # Clients are receivers only; the host is the sole physical input source.
        return

    def _on_local_edge(self, side):
        with self._lock:
            if self._local_mode or self._control_owner != self._device_id or not self._channel:
                return
            target = self._index + (1 if side == "right" else -1)
            if not any(d.get("index") == target for d in self._devices):
                channel = None
            else:
                channel = self._channel
        if channel is None:
            return
        try:
            channel.send({
                "version": PROTOCOL_VERSION, "kind": "control_switch",
                "side": side, "ownership_epoch": self._ownership_epoch,
            })
        except (OSError, ProtocolError, ValueError) as error:
            self.on_message(f"[Mixput] Could not switch device: {error}")

    def send_chat(self, text):
        if not isinstance(text, str):
            return False
        text = text.strip()
        if not text or len(text) > MAX_CHAT_LENGTH:
            return False
        with self._lock:
            channel = self._channel
        if not channel:
            return False
        try:
            channel.send({"version": PROTOCOL_VERSION, "kind": "chat", "text": text})
            return True
        except (OSError, ProtocolError, ValueError):
            return False

    def _request_pairing(self, connection, host):
        private, public_text = new_ephemeral_key()
        salt = os.urandom(32)
        send_control(connection, {"type": "pair_request", "version": PAIRING_VERSION,
            "device_id": self.pairings.device_id, "name": socket.gethostname()[:64],
            "public_key": public_text, "nonce": base64.b64encode(salt).decode("ascii")})
        response = receive_control(connection)
        if response.get("type") == "pair_denied":
            reason = response.get("reason")
            raise ProtocolError("The Mixput server is full." if reason == "server_full" else "The host rejected the pairing request.")
        if response.get("type") != "pair_accept" or response.get("version") != PAIRING_VERSION:
            raise ProtocolError("The host did not complete device pairing.")
        key = derive_pairing_key(private, response.get("public_key", ""), salt)
        token = decrypt_session_token(key, response.get("nonce", ""), response.get("ciphertext", ""))
        host_id, host_name = response.get("host_id"), response.get("host_name")
        if not isinstance(host_id, str) or len(host_id) != 32 or not isinstance(host_name, str):
            raise ProtocolError("The host returned an invalid identity.")
        self.pairings.save_host(host, self._port, host_id, host_name, token)
        self.on_message(f"[Mixput] Pairing approved by {host_name}. Authorization saved.")

    def _apply_session_state(self, message):
        devices, owner = message.get("devices"), message.get("owner")
        if not isinstance(devices, list) or not 2 <= len(devices) <= 4 or not isinstance(owner, str):
            raise ProtocolError("Invalid server topology.")
        epoch = message.get("ownership_epoch")
        if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
            raise ProtocolError("The server provided an invalid ownership epoch.")
        with self._lock:
            if epoch < self._ownership_epoch:
                return False
            previous_epoch = self._ownership_epoch
        network_cidr = message.get("virtual_network")
        try:
            virtual_network = ipaddress.ip_network(network_cidr, strict=True)
        except (TypeError, ValueError) as error:
            raise ProtocolError("The server provided an invalid Mixput virtual network.") from error
        if virtual_network.version != 4 or not virtual_network.is_private:
            raise ProtocolError("The Mixput virtual network must use a private IPv4 range.")
        virtual_addresses = []
        for device in devices:
            if not isinstance(device, dict):
                raise ProtocolError("Invalid device entry in server topology.")
            try:
                virtual_address = ipaddress.ip_address(device.get("virtual_ip", ""))
            except ValueError as error:
                raise ProtocolError("The server provided an invalid Mixput virtual IP.") from error
            if (virtual_address.version != 4 or virtual_address not in virtual_network
                    or virtual_address in (virtual_network.network_address, virtual_network.broadcast_address)):
                raise ProtocolError("The server provided an out-of-range Mixput virtual IP.")
            virtual_addresses.append(str(virtual_address))
        if len(set(virtual_addresses)) != len(virtual_addresses):
            raise ProtocolError("The server assigned duplicate Mixput virtual IP addresses.")
        valid_owners = {device.get("id") for device in devices}
        if owner not in valid_owners:
            raise ProtocolError("The server selected an unknown input owner.")
        own = next((d for d in devices if isinstance(d, dict) and d.get("id") == self._device_id), None)
        if own is None:
            raise ProtocolError("This device is missing from the server topology.")
        with self._lock:
            old_owner = self._control_owner
            self._devices = devices
            self._index = int(own.get("index", 1))
            self._virtual_ip = str(own["virtual_ip"])
            self._virtual_network = str(virtual_network)
            self._control_owner = owner
            self._ownership_epoch = epoch
            if epoch != previous_epoch:
                self._last_input_sequence = 0
            active = owner == self._device_id
        if self.input_backend:
            if old_owner == self._device_id and not active:
                self.input_backend.release_all()
            self.input_backend.set_capture_enabled(False)
            self.input_backend.set_relative_mode(False)
            if active and old_owner != self._device_id:
                self.input_backend.warp_to_edge(message.get("enter_edge") or "left")
        self.on_session({
            "devices": devices, "owner": owner, "index": self._index,
            "local_mode": self.local_mode,
            "virtual_ip": self.virtual_ip,
            "virtual_network": self._virtual_network,
            "ownership_epoch": self._ownership_epoch,
        })
        return True

    def _apply_remote_input(self, message):
        with self._lock:
            valid = (
                not self._local_mode
                and self._control_owner == self._device_id
                and message.get("target_id") == self._device_id
                and message.get("source_id") == "host"
                and message.get("ownership_epoch") == self._ownership_epoch
                and isinstance(message.get("sequence"), int)
                and not isinstance(message.get("sequence"), bool)
                and message["sequence"] > self._last_input_sequence
            )
            if not valid:
                return False
            self._last_input_sequence = message["sequence"]
        event = message.get("event")
        if not isinstance(event, dict) or event.get("type") not in EVENT_TYPES or not self.input_backend:
            return False
        return bool(self.input_backend.apply_event(event))

    def _run(self, host, port):
        channel = None
        try:
            self._port = int(port)
            self.on_message(f"[Mixput] Connecting to {host}:{port}...")
            connection = socket.create_connection((host, port), timeout=6)
            connection.settimeout(8.0)
            self.sock = connection
            saved = self.pairings.get_host(host, port)
            if saved:
                send_control(connection, {"type": "resume", "version": PAIRING_VERSION,
                    "device_id": self.pairings.device_id, "host_id": saved["host_id"]})
                response = receive_control(connection)
                if response.get("type") == "resume_ok":
                    channel = SecureChannel(connection, saved["token"])
                elif response.get("type") != "pair_required":
                    raise ProtocolError("The host could not verify this device.")
            if channel is None:
                self._request_pairing(connection, host)
                saved = self.pairings.get_host(host, port)
                channel = SecureChannel(connection, saved["token"])
            self._channel = channel
            channel.send({"version": PROTOCOL_VERSION, "kind": "hello"})
            hello = channel.receive()
            if not hello or hello.get("version") != PROTOCOL_VERSION or hello.get("kind") != "hello_ack":
                raise ProtocolError("The host rejected the secure session.")
            connection.settimeout(0.5)
            if self.input_backend:
                self.input_backend.start_capture()
                self.input_backend.set_capture_enabled(False)
                self.input_backend.set_relative_mode(False)
            self.on_status("connected")
            self.on_message(f"[Mixput] Connected to Mixput server at {host}.")
            while self.running:
                try:
                    message = channel.receive()
                except socket.timeout:
                    continue
                if message is None:
                    break
                if message.get("version") != PROTOCOL_VERSION:
                    raise ProtocolError("Unsupported peer protocol.")
                kind = message.get("kind")
                if kind == "session_state":
                    self._apply_session_state(message)
                elif kind == "input":
                    if not self._apply_remote_input(message):
                        self.on_message("[Mixput] Rejected stale, unauthorized, or invalid input event.")
                elif kind == "chat":
                    sender, text = message.get("sender"), message.get("text")
                    if isinstance(sender, str) and isinstance(text, str) and len(text) <= MAX_CHAT_LENGTH:
                        self.on_chat(message)
                elif kind == "disconnect":
                    break
        except (OSError, ProtocolError, ValueError, KeyError, RuntimeError, TypeError) as error:
            if self.running:
                self.on_message(f"[Mixput] Connection failed: {error}")
        finally:
            self.running = False
            with self._lock:
                self._control_owner = "host"
                self._ownership_epoch = -1
                self._last_input_sequence = 0
                self._devices = []
                self._virtual_ip = None
                self._virtual_network = None
                self._local_mode = False
            if self.input_backend:
                self.input_backend.stop_capture()
                self.input_backend.release_all()
            if channel:
                channel.close()
            elif self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
            self.sock = None
            self._channel = None
            self.on_session({"devices": [], "owner": "host", "index": 1})
            self.on_status("disconnected")

    def disconnect(self):
        self.running = False
        channel = self._channel
        if channel:
            try:
                channel.send({"version": PROTOCOL_VERSION, "kind": "disconnect"})
            except (OSError, ProtocolError):
                pass
            channel.close()
        elif self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
        self.on_status("disconnected")
