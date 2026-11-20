"""Authenticated encrypted TCP channel used by Mixput peers."""
import json
import socket
import threading

from cryptography.fernet import Fernet, InvalidToken

from app.components.core.input_protocol import MAX_MESSAGE_BYTES, ProtocolError


class SecureChannel:
    """Newline-framed Fernet channel with authenticated encryption."""

    def __init__(self, connection, token):
        try:
            self._cipher = Fernet(token.encode("ascii") if isinstance(token, str) else token)
        except (ValueError, TypeError) as error:
            raise ProtocolError("Invalid pairing key.") from error
        self._socket = connection
        self._buffer = bytearray()
        self._send_lock = threading.Lock()
        self._closed = False

    def send(self, message):
        if self._closed:
            return False
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(payload) > MAX_MESSAGE_BYTES:
            raise ProtocolError("Message exceeds the protocol size limit.")
        encrypted = self._cipher.encrypt(payload) + b"\n"
        with self._send_lock:
            if self._closed:
                return False
            self._socket.sendall(encrypted)
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
                    message = json.loads(decoded.decode("utf-8"))
                except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ProtocolError("Pairing key is incorrect or message is invalid.") from error
                if not isinstance(message, dict):
                    raise ProtocolError("Invalid message.")
                return message

            chunk = self._socket.recv(4096)
            if not chunk:
                return None
            self._buffer.extend(chunk)
            if len(self._buffer) > MAX_MESSAGE_BYTES * 2:
                raise ProtocolError("Encrypted frame is too large.")
        return None

    def close(self):
        self._closed = True
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._socket.close()
        except OSError:
            pass
