import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.components.core.network_client import NetworkClient
from app.components.core.network_server import NetworkServer
from app.components.core.pairing_store import PairingStore


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
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]

        self.temp = tempfile.TemporaryDirectory()
        self.host_backend = RecordingInputBackend()
        self.receiver_backend = RecordingInputBackend()
        self.server_status = []
        self.client_status = []
        self.server_connected = threading.Event()
        self.client_connected = threading.Event()
        self.pairing_requested = threading.Event()

        def on_server_status(status):
            self.server_status.append(status)
            if status == "connected":
                self.server_connected.set()

        def on_client_status(status):
            self.client_status.append(status)
            if status == "connected":
                self.client_connected.set()

        self.server = NetworkServer(
            on_status=on_server_status,
            on_pairing_request=self._approve_pairing,
            pairing_store=PairingStore(Path(self.temp.name) / "host.json"),
        )
        self.server.set_input_backend(self.host_backend)
        self.client = NetworkClient(
            on_status=on_client_status,
            input_backend=self.receiver_backend,
            pairing_store=PairingStore(Path(self.temp.name) / "client.json"),
        )

    def _approve_pairing(self, request):
        self.pairing_requested.set()
        self.assertEqual(request["name"], "test-client")
        self.server.approve_pairing(request["request_id"], True)

    def tearDown(self):
        self.client.disconnect()
        self.server.stop()
        self.temp.cleanup()

    def _wait(self, event, description):
        self.assertTrue(event.wait(5), f"Timed out waiting for {description}")

    def _start_server(self):
        self.assertTrue(self.server.start("127.0.0.1", self.port))
        deadline = time.monotonic() + 5
        while "listening" not in self.server_status and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn("listening", self.server_status)

    def test_approval_pairing_persists_and_forwards_input(self):
        self._start_server()
        self.assertTrue(self.client.connect("127.0.0.1", self.port))
        self._wait(self.pairing_requested, "host pairing approval")
        self._wait(self.server_connected, "host authentication")
        self._wait(self.client_connected, "receiver authentication")
        self._wait(self.host_backend.started, "host input capture")

        authorized = self.server.pairings.list_authorized_clients()
        self.assertEqual(len(authorized), 1)
        self.assertEqual(authorized[0]["name"], "test-client")
        self.assertTrue(self.client.pairings.get_host("127.0.0.1", self.port))

        event = {"type": "mouse_move", "dx": 12, "dy": -4}
        self.server._send_input(event)
        self._wait(self.receiver_backend.event_received, "forwarded input event")
        self.assertEqual(self.receiver_backend.events, [event])

    def test_revoked_device_is_not_authorized_for_resume(self):
        self._start_server()
        self.assertTrue(self.client.connect("127.0.0.1", self.port))
        self._wait(self.client_connected, "initial pairing")
        device_id = self.client.pairings.device_id
        self.client.disconnect()
        deadline = time.monotonic() + 5
        while self.client.running and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.server.revoke_device(device_id))
        self.assertIsNone(self.server.pairings.get_authorized_client(device_id))


if __name__ == "__main__":
    unittest.main()
