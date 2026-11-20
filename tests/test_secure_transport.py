import socket
import threading
import unittest

from cryptography.fernet import Fernet

from app.components.core.input_protocol import ProtocolError
from app.components.core.secure_transport import SecureChannel


class SecureChannelTests(unittest.TestCase):
    def setUp(self):
        self.left_socket, self.right_socket = socket.socketpair()
        self.key = Fernet.generate_key()
        self.left = SecureChannel(self.left_socket, self.key)
        self.right = SecureChannel(self.right_socket, self.key)

    def tearDown(self):
        self.left.close()
        self.right.close()

    def test_encrypted_round_trip(self):
        sent = {"version": 1, "kind": "hello"}
        self.left.send(sent)
        self.assertEqual(self.right.receive(), sent)

    def test_sequence_preserves_concurrent_writes(self):
        messages = [{"version": 1, "kind": "input", "index": i} for i in range(40)]
        threads = [
            threading.Thread(target=self.left.send, args=(message,))
            for message in messages
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        received = [self.right.receive() for _ in messages]
        self.assertEqual({item["index"] for item in received}, set(range(40)))

    def test_wrong_pairing_key_is_rejected(self):
        self.right.close()
        self.right_socket = socket.socketpair()[1]
        wrong_key = Fernet.generate_key()
        wrong_peer = SecureChannel(self.right_socket, wrong_key)
        try:
            self.left.send({"version": 1, "kind": "hello"})
            with self.assertRaises(ProtocolError):
                wrong_peer.receive()
        finally:
            wrong_peer.close()


if __name__ == "__main__":
    unittest.main()
