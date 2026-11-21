import json
import socket
import threading
import unittest

from cryptography.fernet import Fernet

from app.components.core.input_protocol import ProtocolError
from app.components.core.secure_transport import SecureChannel


class BlockingSocket:
    """Small send-only socket double used to make queue saturation deterministic."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False

    def setsockopt(self, *args):
        return None

    def sendall(self, data):
        self.started.set()
        self.release.wait(timeout=3)
        if self.closed:
            raise OSError("socket closed")

    def shutdown(self, *_args):
        self.closed = True
        self.release.set()

    def close(self):
        self.closed = True
        self.release.set()


class SecureChannelTests(unittest.TestCase):
    def setUp(self):
        self.left_socket, self.right_socket = socket.socketpair()
        self.token = Fernet.generate_key().decode("ascii")
        self.left = SecureChannel(self.left_socket, self.token)
        self.right = SecureChannel(self.right_socket, self.token)

    def tearDown(self):
        self.left.close()
        self.right.close()

    def test_encrypted_bidirectional_round_trip(self):
        outgoing = {"version": 3, "kind": "ping", "value": "mixput"}
        self.assertTrue(self.left.send(outgoing))
        self.assertEqual(self.right.receive(), outgoing)

        response = {"version": 3, "kind": "pong"}
        self.assertTrue(self.right.send(response))
        self.assertEqual(self.left.receive(), response)

    def test_rejects_replayed_or_out_of_order_sequence(self):
        raw_peer, raw_channel = socket.socketpair()
        receiver = SecureChannel(raw_channel, self.token)
        try:
            payload = json.dumps(
                {"sequence": 1, "message": {"version": 3, "kind": "invalid"}},
                separators=(",", ":"),
            ).encode("utf-8")
            raw_peer.sendall(Fernet(self.token.encode("ascii")).encrypt(payload) + b"\n")
            with self.assertRaises(ProtocolError):
                receiver.receive()
        finally:
            receiver.close()
            raw_peer.close()

    def test_rejects_oversized_message(self):
        with self.assertRaises(ProtocolError):
            self.left.send({"kind": "large", "value": "x" * 5000})

    def test_rejects_boolean_sequence_even_when_equal_to_integer(self):
        raw_peer, raw_channel = socket.socketpair()
        receiver = SecureChannel(raw_channel, self.token)
        cipher = Fernet(self.token.encode("ascii"))
        try:
            first = json.dumps(
                {"sequence": 0, "message": {"kind": "first"}},
                separators=(",", ":"),
            ).encode("utf-8")
            boolean_sequence = json.dumps(
                {"sequence": True, "message": {"kind": "second"}},
                separators=(",", ":"),
            ).encode("utf-8")
            raw_peer.sendall(cipher.encrypt(first) + b"\\n" + cipher.encrypt(boolean_sequence) + b"\\n")
            self.assertEqual(receiver.receive(), {"kind": "first"})
            with self.assertRaises(ProtocolError):
                receiver.receive()
        finally:
            receiver.close()
            raw_peer.close()

    def test_writer_thread_stops_when_channel_closes(self):
        self.left.close()
        self.assertFalse(self.left._writer.is_alive())

    def test_queue_overflow_closes_session_instead_of_dropping_input(self):
        blocked_socket = BlockingSocket()
        channel = SecureChannel(blocked_socket, self.token)
        try:
            channel.send({"kind": "first"})
            self.assertTrue(blocked_socket.started.wait(timeout=1))
            for index in range(256):
                channel.send({"kind": "queued", "index": index})
            with self.assertRaises(ProtocolError):
                channel.send({"kind": "overflow"})
            self.assertTrue(channel.closed)
        finally:
            channel.close()


if __name__ == "__main__":
    unittest.main()
