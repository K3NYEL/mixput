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
        self.capture_enabled = False

    def start_capture(self):
        self.started.set()

    def stop_capture(self):
        self.stopped.set()

    def set_capture_enabled(self, enabled):
        self.capture_enabled = bool(enabled)

    def set_relative_mode(self, enabled):
        self.relative_mode = bool(enabled)

    def park_cursor(self):
        self.parked = True
        return True

    def warp_to_edge(self, side):
        self.warped_to = side
        return True

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
        self.assertTrue(request["name"])
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
        self.assertTrue(authorized[0]["name"])
        self.assertTrue(self.client.pairings.get_host("127.0.0.1", self.port))

        self.server._set_owner(self.client.pairings.device_id, "left")
        event = {"type": "mouse_move", "dx": 12, "dy": -4}
        self.server._send_input(event)
        self._wait(self.receiver_backend.event_received, "forwarded input event")
        self.assertEqual(self.receiver_backend.events, [event])

    def test_edge_handoff_is_bidirectional_and_routes_remote_input(self):
        self._start_server()
        self.assertTrue(self.client.connect("127.0.0.1", self.port))
        self._wait(self.client_connected, "initial pairing")
        self._wait(self.server_connected, "host authentication")

        self.server._on_local_edge("right")
        deadline = time.monotonic() + 5
        while self.server._control_owner != self.client.pairings.device_id and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.server._control_owner, self.client.pairings.device_id)
        self.assertTrue(self.host_backend.capture_enabled)
        self.assertFalse(self.receiver_backend.capture_enabled)

        event = {"type": "key_down", "key": "a"}
        self.server._send_input(event)
        self._wait(self.receiver_backend.event_received, "host input routed to active receiver")
        self.assertEqual(self.receiver_backend.events, [event])

        deadline = time.monotonic() + 5
        while self.client._control_owner != self.client.pairings.device_id and time.monotonic() < deadline:
            time.sleep(0.01)
        self.client._on_local_edge("left")
        deadline = time.monotonic() + 5
        while self.server._control_owner != "host" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.server._control_owner, "host")
        self.assertTrue(self.host_backend.capture_enabled)
        self.assertFalse(self.receiver_backend.capture_enabled)

    def test_revoked_device_must_request_approval_again(self):
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

        self.server.on_pairing_request = lambda request: self.server.approve_pairing(
            request["request_id"], False
        )
        self.client_connected.clear()
        self.assertTrue(self.client.connect("127.0.0.1", self.port))
        deadline = time.monotonic() + 5
        while self.client.running and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.client.running)
        self.assertFalse(self.client_connected.is_set())



    def test_three_remote_devices_horizontal_handoff_chat_and_capacity(self):
        self._start_server()
        chat_received = threading.Event()
        received_messages = []

        def make_client(label, on_chat=None):
            backend = RecordingInputBackend()
            client = NetworkClient(
                on_status=lambda status: None,
                on_chat=on_chat,
                input_backend=backend,
                pairing_store=PairingStore(Path(self.temp.name) / f"{label}.json"),
            )
            return client, backend

        second_chat = threading.Event()
        third, third_backend = make_client("third", lambda message: (
            received_messages.append(message), second_chat.set()
        ))
        second, second_backend = make_client("second")
        self.assertTrue(self.client.connect("127.0.0.1", self.port))
        self._wait(self.client_connected, "first remote device")
        self.assertTrue(second.connect("127.0.0.1", self.port))
        deadline = time.monotonic() + 5
        while not second.running and time.monotonic() < deadline:
            time.sleep(0.01)
        deadline = time.monotonic() + 5
        while len(self.server.connected_devices) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(self.server.connected_devices), 3)
        deadline = time.monotonic() + 5
        while len(self.client._devices) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(self.client._devices), 3)
        self.assertTrue(third.connect("127.0.0.1", self.port))
        deadline = time.monotonic() + 5
        while len(self.server.connected_devices) < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(self.server.connected_devices), 4)

        self.server._on_local_edge("right")
        deadline = time.monotonic() + 5
        while self.server._control_owner != self.client.pairings.device_id and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.server._control_owner, self.client.pairings.device_id)

        # The server changes ownership before the receiver thread processes the
        # session_state message. Wait for that state to arrive before simulating
        # the receiver crossing its edge; otherwise the test races the network
        # reader and may drop a valid handoff attempt.
        deadline = time.monotonic() + 5
        while self.client._control_owner != self.client.pairings.device_id and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.client._control_owner, self.client.pairings.device_id)

        self.client._on_local_edge("right")
        deadline = time.monotonic() + 5
        while self.server._control_owner != second.pairings.device_id and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.server._control_owner, second.pairings.device_id)

        self.assertTrue(second.send_chat("hello from device two"))
        self._wait(second_chat, "group chat delivery to third device")
        self.assertEqual(received_messages[-1]["text"], "hello from device two")

        overflow, _ = make_client("overflow")
        self.assertTrue(overflow.connect("127.0.0.1", self.port))
        deadline = time.monotonic() + 5
        while overflow.running and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(overflow.running)
        self.assertEqual(len(self.server.connected_devices), 4)

        overflow.disconnect()
        third.disconnect()
        second.disconnect()

if __name__ == "__main__":
    unittest.main()
