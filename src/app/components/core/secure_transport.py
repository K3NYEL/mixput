"""Authenticated encrypted TCP channel with bounded asynchronous writes.

A single writer preserves frame ordering while keeping mouse/keyboard capture
callbacks away from blocking socket.sendall calls. Queue overflow fails closed:
the peer disconnects and releases every held input instead of receiving a
silently truncated input stream.
"""
import json
import queue
import socket
import threading
import time

from cryptography.fernet import Fernet, InvalidToken

from app.components.core.input_protocol import MAX_MESSAGE_BYTES, ProtocolError

MAX_PENDING_FRAMES = 256
MAX_ENCRYPTED_FRAME_BYTES = MAX_MESSAGE_BYTES * 2


class SecureChannel:
    """Fernet encryption, integrity checks, framing, replay ordering and queued writes."""

    def __init__(self, connection, token):
        try:
            self._cipher = Fernet(token.encode("ascii") if isinstance(token, str) else token)
        except (ValueError, TypeError) as error:
            raise ProtocolError("Invalid pairing key.") from error

        self._socket = connection
        self._buffer = bytearray()
        self._send_lock = threading.Lock()
        self._closed = threading.Event()
        self._send_sequence = 0
        self._receive_sequence = 0
        self._send_queue = queue.Queue(maxsize=MAX_PENDING_FRAMES)

        try:
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass

        self._writer = threading.Thread(
            target=self._write_loop,
            name="MixputSecureWriter",
            daemon=True,
        )
        self._writer.start()

    @property
    def closed(self):
        return self._closed.is_set()

    def _shutdown_socket(self):
        self._closed.set()
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._socket.close()
        except OSError:
            pass

    def _write_loop(self):
        while not self._closed.is_set():
            try:
                frame = self._send_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if frame is None:
                    return
                if self._closed.is_set():
                    continue
                self._socket.sendall(frame)
            except OSError:
                self._shutdown_socket()
                return
            finally:
                self._send_queue.task_done()

    def send(self, message):
        with self._send_lock:
            if self._closed.is_set():
                return False

            envelope = {
                "sequence": self._send_sequence,
                "message": message,
            }
            try:
                payload = json.dumps(
                    envelope,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            except (TypeError, ValueError) as error:
                raise ProtocolError("Message is not JSON serializable.") from error

            if len(payload) > MAX_MESSAGE_BYTES:
                raise ProtocolError("Message exceeds the protocol size limit.")

            encrypted = self._cipher.encrypt(payload) + b"\n"
            if len(encrypted) > MAX_ENCRYPTED_FRAME_BYTES:
                raise ProtocolError("Encrypted frame exceeds the protocol size limit.")

            try:
                self._send_queue.put_nowait(encrypted)
            except queue.Full as error:
                self._shutdown_socket()
                raise ProtocolError(
                    "Network output queue is full; the secure session was closed."
                ) from error

            self._send_sequence += 1
            return True

    def flush(self, timeout=0.2):
        """Wait briefly for queued frames to reach the socket."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while self._send_queue.unfinished_tasks and not self._closed.is_set():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        return self._send_queue.unfinished_tasks == 0

    def receive(self):
        while not self._closed.is_set():
            marker = self._buffer.find(b"\n")
            if marker >= 0:
                line = bytes(self._buffer[:marker])
                del self._buffer[:marker + 1]
                if not line or len(line) > MAX_ENCRYPTED_FRAME_BYTES:
                    raise ProtocolError("Invalid encrypted frame size.")
                try:
                    decoded = self._cipher.decrypt(line)
                    envelope = json.loads(decoded.decode("utf-8"))
                except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ProtocolError(
                        "Pairing key is incorrect or message is invalid."
                    ) from error

                if (
                    not isinstance(envelope, dict)
                    or isinstance(envelope.get("sequence"), bool)
                    or envelope.get("sequence") != self._receive_sequence
                ):
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
            if len(self._buffer) > MAX_ENCRYPTED_FRAME_BYTES:
                # A complete frame may be followed by more frames in one TCP read.
                # Reject only when no delimiter exists within the maximum frame.
                if self._buffer.find(b"\n") < 0:
                    raise ProtocolError("Encrypted frame is too large.")
        return None

    def close(self):
        if self._closed.is_set():
            return
        self.flush(timeout=0.15)
        self._shutdown_socket()
        if threading.current_thread() is not self._writer:
            self._writer.join(timeout=0.25)
