"""LAN host with authenticated input forwarding and edge-based control handoff."""
import socket
import threading
import uuid

from cryptography.fernet import Fernet

from app.components.core.input_protocol import PROTOCOL_VERSION, EVENT_TYPES, ProtocolError
from app.components.core.pairing_handshake import (
    PAIRING_VERSION, send_control, receive_control, new_ephemeral_key,
    derive_pairing_key, encrypt_session_token,
)
from app.components.core.pairing_store import PairingStore
from app.components.core.secure_transport import SecureChannel


class NetworkServer:
    def __init__(self, on_log=None, on_status=None, on_pairing_request=None, pairing_store=None):
        self.on_log = on_log or (lambda message: None)
        self.on_status = on_status or (lambda status: None)
        self.on_pairing_request = on_pairing_request or (lambda request: None)
        self.pairings = pairing_store or PairingStore()
        self.running = False
        self._server_socket = None
        self._client_socket = None
        self._channel = None
        self._thread = None
        self._lock = threading.RLock()
        self._capture = None
        self._pending = {}
        self._client_device_id = None
        self._control_owner = "host"

    def start(self, host="0.0.0.0", port=8080):
        with self._lock:
            if self.running:
                return False
            self.running = True
            self._thread = threading.Thread(
                target=self._run, args=(host, port), daemon=True, name="MixputServer"
            )
            self._thread.start()
        return True

    def set_input_backend(self, backend):
        self._capture = backend
        backend.on_event = self._send_input
        backend.on_edge = self._on_local_edge

    def _send_control(self, kind, **values):
        with self._lock:
            channel = self._channel
        if channel is None:
            return False
        try:
            channel.send({"version": PROTOCOL_VERSION, "kind": kind, **values})
            return True
        except (OSError, ProtocolError, ValueError):
            return False

    def _on_local_edge(self, side):
        if side != "right":
            return
        with self._lock:
            if self._control_owner != "host" or self._channel is None:
                return
            self._control_owner = "client"
            channel = self._channel
        self._capture.set_capture_enabled(False)
        self._capture.release_all()
        try:
            channel.send({"version": PROTOCOL_VERSION, "kind": "control_switch", "owner": "client", "enter_edge": "left"})
            self.on_log("[Mixput] Control transferred to the connected laptop.")
        except (OSError, ProtocolError, ValueError) as error:
            with self._lock:
                self._control_owner = "host"
            self._capture.set_capture_enabled(True)
            self.on_log(f"[Mixput] Could not transfer control: {error}")

    def approve_pairing(self, request_id, approved):
        with self._lock:
            pending = self._pending.get(request_id)
            if pending is None:
                return False
            pending["approved"] = bool(approved)
            pending["event"].set()
            return True

    def revoke_device(self, device_id):
        revoked = self.pairings.revoke_client(device_id)
        if revoked:
            with self._lock:
                active = self._client_device_id == device_id
                channel = self._channel if active else None
            if channel:
                channel.close()
            self.on_log("[Mixput] Device authorization revoked.")
        return revoked

    def _send_input(self, event):
        with self._lock:
            channel = self._channel
            allowed = self._control_owner == "host"
        if channel is None or not allowed:
            return
        try:
            if event.get("type") in EVENT_TYPES:
                channel.send({"version": PROTOCOL_VERSION, "kind": "input", "event": event})
        except (OSError, ProtocolError, ValueError) as error:
            self.on_log(f"[Mixput] Could not transmit input: {error}")

    def _run(self, host, port):
        server = None
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(5)
            server.settimeout(0.5)
            with self._lock:
                self._server_socket = server
            self.on_status("listening")
            self.on_log(f"[Mixput] Sharing endpoint ready on port {port}.")
            while self.running:
                try:
                    connection, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.running:
                        raise
                    break
                self._handle_peer(connection, address)
        except OSError as error:
            if self.running:
                self.on_log(f"[Mixput] Server error: {error}")
                self.on_status("error")
        finally:
            self._stop_capture()
            self._close_peer()
            if server is not None:
                try:
                    server.close()
                except OSError:
                    pass
            with self._lock:
                self._server_socket = None
                self.running = False
            self.on_status("stopped")

    def _request_approval(self, request):
        request_id = uuid.uuid4().hex
        pending = {"event": threading.Event(), "approved": False}
        with self._lock:
            self._pending[request_id] = pending
        self.on_pairing_request({**request, "request_id": request_id})
        try:
            return pending["event"].wait(60) and pending["approved"]
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def _handle_peer(self, connection, address):
        channel = None
        try:
            connection.settimeout(8.0)
            control = receive_control(connection)
            client_id = control.get("device_id")
            if control.get("version") != PAIRING_VERSION or not isinstance(client_id, str) or len(client_id) != 32:
                raise ProtocolError("Invalid device identity or pairing protocol.")

            if control.get("type") == "resume":
                record = None
                if control.get("host_id") == self.pairings.device_id:
                    record = self.pairings.get_authorized_client(client_id)
                if record is None:
                    send_control(connection, {"type": "pair_required", "version": PAIRING_VERSION})
                    control = receive_control(connection)
                else:
                    send_control(connection, {"type": "resume_ok", "version": PAIRING_VERSION})
                    channel = SecureChannel(connection, record["token"])
            if channel is None:
                if control.get("type") != "pair_request":
                    raise ProtocolError("A pairing request is required.")
                name = control.get("name")
                ephemeral = control.get("public_key")
                salt_text = control.get("nonce")
                if not isinstance(name, str) or not name.strip() or len(name) > 64:
                    raise ProtocolError("Invalid device name.")
                if not isinstance(ephemeral, str) or not isinstance(salt_text, str):
                    raise ProtocolError("Invalid pairing request.")
                import base64
                try:
                    salt = base64.b64decode(salt_text, validate=True)
                except ValueError as error:
                    raise ProtocolError("Invalid pairing nonce.") from error
                if len(salt) != 32:
                    raise ProtocolError("Invalid pairing nonce.")
                self.on_status("pairing")
                approved = self._request_approval({
                    "device_id": client_id, "name": name.strip(), "ip": address[0],
                })
                if not approved or not self.running:
                    send_control(connection, {"type": "pair_denied", "version": PAIRING_VERSION})
                    return
                private, public_text = new_ephemeral_key()
                key = derive_pairing_key(private, ephemeral, salt)
                token = Fernet.generate_key().decode("ascii")
                nonce, ciphertext = encrypt_session_token(key, token)
                self.pairings.authorize_client(client_id, name, address[0], token)
                send_control(connection, {
                    "type": "pair_accept", "version": PAIRING_VERSION,
                    "host_id": self.pairings.device_id,
                    "host_name": socket.gethostname()[:64],
                    "public_key": public_text, "nonce": nonce, "ciphertext": ciphertext,
                })
                channel = SecureChannel(connection, token)

            with self._lock:
                self._client_socket = connection
                self._channel = channel
                self._client_device_id = client_id
                self._control_owner = "host"
            self.on_status("authenticating")
            hello = channel.receive()
            if not hello or hello.get("version") != PROTOCOL_VERSION or hello.get("kind") != "hello":
                raise ProtocolError("Invalid peer handshake.")
            channel.send({"version": PROTOCOL_VERSION, "kind": "hello_ack"})
            connection.settimeout(0.5)
            self.on_status("connected")
            self.on_log(f"[Mixput] Authorized laptop connected: {address[0]}")
            if self._capture is None:
                raise RuntimeError("Input backend is not configured.")
            self._capture.start_capture()
            self._capture.set_capture_enabled(True)
            while self.running:
                try:
                    message = channel.receive()
                except socket.timeout:
                    continue
                if message is None or message.get("kind") == "disconnect":
                    break
                if message.get("version") != PROTOCOL_VERSION:
                    raise ProtocolError("Unsupported peer protocol.")
                kind = message.get("kind")
                if kind == "input" and self._control_owner == "client":
                    event = message.get("event")
                    if isinstance(event, dict) and event.get("type") in EVENT_TYPES:
                        if not self._capture.apply_event(event):
                            self.on_log("[Mixput] A remote input event could not be applied.")
                elif kind == "control_switch" and message.get("owner") == "host":
                    with self._lock:
                        self._control_owner = "host"
                    self._capture.set_capture_enabled(True)
                    self._capture.warp_to_edge("right")
                    self.on_log("[Mixput] Control returned to this computer.")
        except (OSError, ProtocolError, ValueError, KeyError, RuntimeError) as error:
            if self.running:
                self.on_log(f"[Mixput] Peer session ended: {error}")
        finally:
            self._stop_capture()
            if channel:
                channel.close()
            else:
                try:
                    connection.close()
                except OSError:
                    pass
            with self._lock:
                if self._channel is channel:
                    self._channel = None
                    self._client_socket = None
                    self._client_device_id = None
                    self._control_owner = "host"
            if self.running:
                self.on_status("listening")
                self.on_log("[Mixput] Waiting for another laptop.")

    def _stop_capture(self):
        if self._capture is not None:
            self._capture.stop_capture()

    def _close_peer(self):
        with self._lock:
            channel = self._channel
            self._channel = None
            self._client_socket = None
            self._client_device_id = None
            self._control_owner = "host"
            pending = list(self._pending.values())
        for item in pending:
            item["approved"] = False
            item["event"].set()
        if channel:
            channel.close()

    def stop(self):
        with self._lock:
            self.running = False
            server = self._server_socket
        self._stop_capture()
        self._close_peer()
        if server:
            try:
                server.close()
            except OSError:
                pass
        self.on_status("stopped")
        self.on_log("[Mixput] Sharing stopped.")
