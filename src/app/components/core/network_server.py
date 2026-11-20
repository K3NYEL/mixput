"""LAN host for explicitly authorized Mixput input-sharing sessions."""
import secrets
import socket
import threading

from cryptography.fernet import Fernet

from app.components.core.input_protocol import PROTOCOL_VERSION, EVENT_TYPES, ProtocolError
from app.components.core.secure_transport import SecureChannel


class NetworkServer:
    def __init__(self, on_log=None, on_status=None, on_pairing_key=None):
        self.on_log = on_log or (lambda message: None)
        self.on_status = on_status or (lambda status: None)
        self.on_pairing_key = on_pairing_key or (lambda key: None)
        self.running = False
        self._server_socket = None
        self._client_socket = None
        self._channel = None
        self._thread = None
        self._lock = threading.RLock()
        self._capture = None
        self.pairing_key = None

    def start(self, host="0.0.0.0", port=8080):
        with self._lock:
            if self.running:
                return False
            self.pairing_key = Fernet.generate_key().decode("ascii")
            self.running = True
            self._thread = threading.Thread(
                target=self._run, args=(host, port, self.pairing_key), daemon=True
            )
            self._thread.start()
        self.on_pairing_key(self.pairing_key)
        return True

    def set_input_backend(self, backend):
        self._capture = backend

    def _send_input(self, event):
        with self._lock:
            channel = self._channel
        if channel is None:
            return
        try:
            if event.get("type") in EVENT_TYPES:
                channel.send({
                    "version": PROTOCOL_VERSION,
                    "kind": "input",
                    "event": event,
                })
        except (OSError, ProtocolError, ValueError) as error:
            self.on_log(f"[Mixput] Could not transmit input: {error}")

    def _run(self, host, port, pairing_key):
        server = None
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(1)
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
                self._handle_peer(connection, address, pairing_key)
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

    def _handle_peer(self, connection, address, pairing_key):
        channel = None
        connection.settimeout(1.0)
        try:
            channel = SecureChannel(connection, pairing_key)
            with self._lock:
                self._client_socket = connection
                self._channel = channel
            self.on_status("authenticating")
            hello = channel.receive()
            if not hello or hello.get("version") != PROTOCOL_VERSION or hello.get("kind") != "hello":
                raise ProtocolError("Invalid peer handshake.")
            channel.send({"version": PROTOCOL_VERSION, "kind": "hello_ack"})
            self.on_status("connected")
            self.on_log(f"[Mixput] Paired laptop connected: {address[0]}")
            if self._capture is None:
                raise RuntimeError("Input backend is not configured.")
            self._capture.start_capture()
            while self.running:
                try:
                    message = channel.receive()
                except socket.timeout:
                    continue
                if message is None:
                    break
                if message.get("version") != PROTOCOL_VERSION:
                    raise ProtocolError("Unsupported peer protocol.")
                if message.get("kind") == "disconnect":
                    break
        except (OSError, ProtocolError, RuntimeError, ValueError) as error:
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
