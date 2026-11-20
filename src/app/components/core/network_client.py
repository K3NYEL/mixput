"""LAN receiver that applies input only after successful pairing."""
import socket
import threading

from app.components.core.input_protocol import PROTOCOL_VERSION, EVENT_TYPES, ProtocolError
from app.components.core.secure_transport import SecureChannel


class NetworkClient:
    def __init__(self, on_message=None, on_status=None, input_backend=None):
        self.on_message = on_message or (lambda message: None)
        self.on_status = on_status or (lambda status: None)
        self.input_backend = input_backend
        self.running = False
        self.sock = None
        self._channel = None
        self._thread = None
        self._lock = threading.RLock()

    def connect(self, host, port=8080, pairing_key=""):
        if self.running:
            return False
        if not host or not pairing_key:
            self.on_message("[Mixput] Enter the other laptop IP and pairing key.")
            return False
        self.running = True
        self._thread = threading.Thread(
            target=self._run, args=(host, port, pairing_key), daemon=True
        )
        self._thread.start()
        return True

    def _run(self, host, port, pairing_key):
        channel = None
        try:
            self.on_message(f"[Mixput] Connecting to {host}:{port}...")
            connection = socket.create_connection((host, port), timeout=6)
            connection.settimeout(1.0)
            self.sock = connection
            channel = SecureChannel(connection, pairing_key)
            self._channel = channel
            channel.send({"version": PROTOCOL_VERSION, "kind": "hello"})
            hello = channel.receive()
            if not hello or hello.get("version") != PROTOCOL_VERSION or hello.get("kind") != "hello_ack":
                raise ProtocolError("The host rejected pairing or uses another protocol.")
            self.on_status("connected")
            self.on_message(f"[Mixput] Paired with {host}. Input sharing is active.")
            while self.running:
                try:
                    message = channel.receive()
                except socket.timeout:
                    continue
                if message is None:
                    break
                if message.get("version") != PROTOCOL_VERSION:
                    raise ProtocolError("Unsupported peer protocol.")
                if message.get("kind") == "input":
                    event = message.get("event")
                    if isinstance(event, dict) and event.get("type") in EVENT_TYPES:
                        if self.input_backend is not None and not self.input_backend.apply_event(event):
                            self.on_message("[Mixput] An input event could not be applied.")
        except (OSError, ProtocolError, ValueError) as error:
            if self.running:
                self.on_message(f"[Mixput] Connection failed: {error}")
        finally:
            self.running = False
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
