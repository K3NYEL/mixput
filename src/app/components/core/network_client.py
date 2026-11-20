"""LAN receiver with remembered pairing and bidirectional edge-switched input."""
import base64
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


class NetworkClient:
    def __init__(self, on_message=None, on_status=None, input_backend=None, pairing_store=None):
        self.on_message = on_message or (lambda message: None)
        self.on_status = on_status or (lambda status: None)
        self.input_backend = input_backend
        self.pairings = pairing_store or PairingStore()
        self.running = False
        self.sock = None
        self._channel = None
        self._thread = None
        self._lock = threading.RLock()
        self._control_owner = "host"
        if self.input_backend is not None:
            self.input_backend.on_event = self._send_input
            self.input_backend.on_edge = self._on_local_edge

    def connect(self, host, port=8080):
        if self.running:
            return False
        if not host:
            self.on_message("[Mixput] Select or enter the host laptop address.")
            return False
        self.running = True
        self._thread = threading.Thread(
            target=self._run, args=(host, port), daemon=True, name="MixputClient"
        )
        self._thread.start()
        return True

    def _send_input(self, event):
        with self._lock:
            channel = self._channel
            allowed = self._control_owner == "client"
        if channel is None or not allowed:
            return
        try:
            if event.get("type") in EVENT_TYPES:
                channel.send({"version": PROTOCOL_VERSION, "kind": "input", "event": event})
        except (OSError, ProtocolError, ValueError) as error:
            self.on_message(f"[Mixput] Could not transmit input: {error}")

    def _on_local_edge(self, side):
        if side != "left":
            return
        with self._lock:
            if self._control_owner != "client" or self._channel is None:
                return
            channel = self._channel
            self._control_owner = "host"
        self.input_backend.set_capture_enabled(False)
        self.input_backend.release_all()
        try:
            channel.send({
                "version": PROTOCOL_VERSION, "kind": "control_switch",
                "owner": "host", "enter_edge": "right",
            })
            self.on_message("[Mixput] Control returned to the host computer.")
        except (OSError, ProtocolError, ValueError) as error:
            with self._lock:
                self._control_owner = "client"
            self.input_backend.set_capture_enabled(True)
            self.on_message(f"[Mixput] Could not return control: {error}")

    def _request_pairing(self, connection, host):
        private, public_text = new_ephemeral_key()
        salt = os.urandom(32)
        send_control(connection, {
            "type": "pair_request", "version": PAIRING_VERSION,
            "device_id": self.pairings.device_id,
            "name": socket.gethostname()[:64], "public_key": public_text,
            "nonce": base64.b64encode(salt).decode("ascii"),
        })
        response = receive_control(connection)
        if response.get("type") == "pair_denied":
            raise ProtocolError("The host rejected the pairing request.")
        if response.get("type") != "pair_accept" or response.get("version") != PAIRING_VERSION:
            raise ProtocolError("The host did not complete device pairing.")
        key = derive_pairing_key(private, response.get("public_key", ""), salt)
        token = decrypt_session_token(key, response.get("nonce", ""), response.get("ciphertext", ""))
        host_id, host_name = response.get("host_id"), response.get("host_name")
        if not isinstance(host_id, str) or len(host_id) != 32 or not isinstance(host_name, str):
            raise ProtocolError("The host returned an invalid identity.")
        self.pairings.save_host(host, self._port, host_id, host_name, token)
        self.on_message(f"[Mixput] Pairing approved by {host_name}. Device authorization saved.")

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
                send_control(connection, {
                    "type": "resume", "version": PAIRING_VERSION,
                    "device_id": self.pairings.device_id, "host_id": saved["host_id"],
                })
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
            with self._lock:
                self._control_owner = "host"
            if self.input_backend is not None:
                self.input_backend.start_capture()
                self.input_backend.set_capture_enabled(False)
            self.on_status("connected")
            self.on_message(f"[Mixput] Connected to {host}. Move to the left screen edge to return control.")
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
                if kind == "input" and self._control_owner == "host":
                    event = message.get("event")
                    if isinstance(event, dict) and event.get("type") in EVENT_TYPES:
                        if self.input_backend is not None and not self.input_backend.apply_event(event):
                            self.on_message("[Mixput] An input event could not be applied.")
                elif kind == "control_switch" and message.get("owner") == "client":
                    with self._lock:
                        self._control_owner = "client"
                    if self.input_backend is not None:
                        self.input_backend.warp_to_edge("left")
                        self.input_backend.set_capture_enabled(True)
                    self.on_message("[Mixput] This computer now has keyboard and mouse control.")
        except (OSError, ProtocolError, ValueError, KeyError) as error:
            if self.running:
                self.on_message(f"[Mixput] Connection failed: {error}")
        finally:
            self.running = False
            with self._lock:
                self._control_owner = "host"
            if self.input_backend is not None:
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
        else:
            connection = self.sock
            if connection:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    connection.close()
                except OSError:
                    pass
        self.on_status("disconnected")
