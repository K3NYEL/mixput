import threading
import unittest

from app.components.core.network_client import NetworkClient
from app.components.core.network_server import NetworkServer


class FakePairings:
    device_id = "a" * 32


class FakeInputBackend:
    def __init__(self):
        self.released = 0

    def release_all(self):
        self.released += 1


class FakeChannel:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True


class FakeThread:
    def is_alive(self):
        return True


class NetworkLifecycleTests(unittest.TestCase):
    def test_client_local_mode_is_sent_to_host(self):
        backend = FakeInputBackend()
        client = NetworkClient(input_backend=backend, pairing_store=FakePairings())
        channel = FakeChannel()
        client._channel = channel
        client._ownership_epoch = 12

        self.assertTrue(client.set_local_mode(True))
        self.assertEqual(backend.released, 1)
        self.assertEqual(
            channel.messages[-1],
            {
                "version": 3,
                "kind": "local_mode",
                "enabled": True,
                "ownership_epoch": 12,
            },
        )

        self.assertTrue(client.set_local_mode(False))
        self.assertFalse(channel.messages[-1]["enabled"])

    def test_client_refuses_overlapping_reconnect_threads(self):
        client = NetworkClient(pairing_store=FakePairings())
        client._thread = FakeThread()
        self.assertFalse(client.connect("127.0.0.1", 8080))

    def test_server_refuses_restart_while_previous_thread_is_alive(self):
        server = NetworkServer.__new__(NetworkServer)
        server._lock = threading.RLock()
        server.running = False
        server._thread = FakeThread()
        self.assertFalse(server.start("127.0.0.1", 0))


if __name__ == "__main__":
    unittest.main()
