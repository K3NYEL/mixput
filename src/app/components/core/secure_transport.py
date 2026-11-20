"""Authenticated encrypted TCP channel with per-direction sequence numbers."""
import json
import socket
import threading

from cryptography.fernet import Fernet, InvalidToken

from app.components.core.input_protocol import MAX_MESSAGE_BYTES, ProtocolError


class SecureChannel:
    """Fernet encryption, integrity checks, framing, and replay ordering."""

    def __init__(self, connection, token):
        try:
            self._cipher = Fernet(token.encode("ascii") if isinstance(token, str) else token)
        except (ValueError, TypeError) as error:
            raise ProtocolError("Invalid pairing key.") from error
        self._socket = connection
        self._buffer = bytearray()
        self._send_lock = threading.Lock()
        self._closed = False
        self._send_sequence = 0
        self._receive_sequence = 0

    def send(self, message):
        with self._send_lock:
            if self._closed:
                return False
            envelope = {"sequence": self._send_sequence, "message": message}
            payload = json.dumps(envelope, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            if len(payload) > MAX_MESSAGE_BYTES:
                raise ProtocolError("Message exceeds the protocol size limit.")
            encrypted = self._cipher.encrypt(payload) + b"\\n"
            self._socket.sendall(encrypted)
            self._send_sequence += 1
        return True

    def receive(self):
        while not self._closed:
            marker = self._buffer.find(b"\n")
            if marker >= 0:
                line = bytes(self._buffer[:marker])
                del self._buffer[:marker + 1]
                if not line or len(line) > MAX_MESSAGE_BYTES * 2:
                    raise ProtocolError("Invalid encrypted frame size.")
                try:
                    decoded = self._cipher.decrypt(line)
                    envelope = json.loads(decoded.decode("utf-8"))
                except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ProtocolError("Pairing key is incorrect or message is invalid.") from error
                if not isinstance(envelope, dict) or envelope.get("sequence") != self._receive_sequence:
                    raise ProtocolError("Invalid or replayed message sequence.")
                message = envelope.get("message")
                if not isinstance(message, dict):
                    raise ProtocolError("Invalid message.")
                self._receive_sequence += 1
                return message

            chunk = self._socket.recv(4096)
            if not chunk:
                return None
            self._buffer.extend(chunk)
            if len(self._buffer) > MAX_MESSAGE_BYTES * 2:
                raise ProtocolError("Encrypted frame is too large.")
        return None

    def close(self):
        with self._send_lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
