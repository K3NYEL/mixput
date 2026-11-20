import socket
import threading
import time
import unittest

from app.components.core.network_client import NetworkClient
from app.components.core.network_server import NetworkServer


class RecordingInputBackend:
    def __init__(self):
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.events = []
        self.event_received = threading.Event()

    def start_capture(self):
        self.started.set()

    def stop_capture(self):
        self.stopped.set()

    def apply_event(self, event):
        self.events.append(event)
        self.event_received.set()
        return True

    def release_all(self):
        pass


class NetworkIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Ask the OS for an available TCP port, then release it before startup.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]

        self.host_backend = RecordingInputBackend()
        self.receiver_backend = RecordingInputBackend()
        self.server_status = []
        self.client_status = []
        self.server_connected = threading.Event()
        self.client_connected = threading.Event()

        def on_server_status(status):
            self.server_status.append(status)
            if status == "connected":
                self.server_connected.set()

        def on_client_status(status):
            self.client_status.append(status)
            if status == "connected":
                self.client_connected.set()

        self.server = NetworkServer(on_status=on_server_status)
        self.server.set_input_backend(self.host_backend)
        self.client = NetworkClient(
            on_status=on_client_status,
            input_backend=self.receiver_backend,
        )

    def tearDown(self):
        self.client.disconnect()
        self.server.stop()

    def _wait(self, event, description):
        self.assertTrue(event.wait(5), f"Timed out waiting for {description}")

    def test_authenticated_lan_session_forwards_input_and_disconnects(self):
        self.assertTrue(self.server.start("127.0.0.1", self.port))

        deadline = time.monotonic() + 5
        while "listening" not in self.server_status and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn("listening", self.server_status)

        self.assertTrue(
            self.client.connect("127.0.0.1", self.port, self.server.pairing_key)
        )
        self._wait(self.server_connected, "host authentication")
        self._wait(self.client_connected, "receiver authentication")
        self._wait(self.host_backend.started, "host input capture")

        event = {"type": "mouse_move", "dx": 12, "dy": -4}
        self.server._send_input(event)
        self._wait(self.receiver_backend.event_received, "forwarded input event")
        self.assertEqual(self.receiver_backend.events, [event])

        self.client.disconnect()
        deadline = time.monotonic() + 5
        while self.client.running and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.client.running)
        self._wait(self.host_backend.stopped, "host capture shutdown")
        self.assertIn("disconnected", self.client_status)


if __name__ == "__main__":
    unittest.main()
