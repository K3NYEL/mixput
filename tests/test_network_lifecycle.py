import threading
import unittest

from app.components.core.network_client import NetworkClient
from app.components.core.network_server import NetworkServer


class FakePairings:
    device_id = "a" * 32


class FakeInputBackend:
    def __init__(self):
        self.released = 0
        self.events = []
        self.capture_enabled = False
        self.exclusive = False

    def release_all(self):
        self.released += 1

    def set_capture_enabled(self, enabled):
        self.capture_enabled = bool(enabled)

    def set_exclusive_capture(self, enabled):
        self.exclusive = bool(enabled)
        return True

    def set_relative_mode(self, _enabled):
        pass

    def warp_to_edge(self, _side):
        pass

    def apply_event(self, event):
        self.events.append(event)
        return True


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

    def test_client_forwards_local_input_to_active_screen(self):
        client = NetworkClient(pairing_store=FakePairings())
        channel = FakeChannel()
        client._channel = channel
        client._control_owner = "remote-device"
        client._ownership_epoch = 7

        self.assertTrue(client._send_input({"type": "key_down", "key": "a"}))
        packet = channel.messages[-1]
        self.assertEqual(packet["kind"], "input")
        self.assertEqual(packet["target_id"], "remote-device")
        self.assertEqual(packet["ownership_epoch"], 7)
        self.assertEqual(packet["sequence"], 1)
        self.assertEqual(packet["event"]["key"], "a")

    def test_client_keeps_edge_detection_without_suppressing_active_local_input(self):
        backend = FakeInputBackend()
        client = NetworkClient(input_backend=backend, pairing_store=FakePairings())
        own_id = client._device_id
        devices = [
            {"id": "host", "index": 0},
            {"id": own_id, "index": 1},
        ]
        self.assertTrue(client._apply_session_state({
            "devices": devices, "owner": own_id, "ownership_epoch": 1,
        }))
        self.assertTrue(backend.capture_enabled)
        self.assertFalse(backend.exclusive)

        self.assertTrue(client._apply_session_state({
            "devices": devices, "owner": "host", "ownership_epoch": 2,
        }))
        self.assertTrue(backend.capture_enabled)
        self.assertTrue(backend.exclusive)

    def test_server_routes_peer_input_to_host(self):
        from app.components.core.input_ownership import InputOwnership

        backend = FakeInputBackend()
        server = NetworkServer.__new__(NetworkServer)
        server._lock = threading.RLock()
        server._ownership = InputOwnership("host")
        source = {"id": "peer-a", "local_mode": False, "input_sequence": 0}
        server._peers = {"peer-a": source}
        server._capture = backend

        accepted = server._route_peer_input(source, {
            "target_id": "host", "ownership_epoch": 0, "sequence": 1,
            "event": {"type": "key_down", "key": "a"},
        })
        self.assertTrue(accepted)
        self.assertEqual(backend.events, [{"type": "key_down", "key": "a"}])

    def test_server_routes_peer_input_to_another_peer(self):
        from app.components.core.input_ownership import InputOwnership

        server = NetworkServer.__new__(NetworkServer)
        server._lock = threading.RLock()
        server._ownership = InputOwnership("peer-b")
        source = {"id": "peer-a", "local_mode": False, "input_sequence": 0}
        target_channel = FakeChannel()
        target = {"id": "peer-b", "local_mode": False, "channel": target_channel}
        server._peers = {"peer-a": source, "peer-b": target}
        server._capture = None

        accepted = server._route_peer_input(source, {
            "target_id": "peer-b", "ownership_epoch": 0, "sequence": 1,
            "event": {"type": "mouse_move", "dx": 4, "dy": -2},
        })
        self.assertTrue(accepted)
        self.assertEqual(target_channel.messages[-1]["source_id"], "peer-a")
        self.assertEqual(target_channel.messages[-1]["target_id"], "peer-b")

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


    def test_host_local_mode_releases_remote_held_input(self):
        class FakeCapture:
            def release_all(self):
                pass

            def set_exclusive_capture(self, _enabled):
                return True

            def set_relative_mode(self, _enabled):
                return None

            def park_cursor(self):
                return True

        from app.components.core.input_ownership import InputOwnership

        server = NetworkServer.__new__(NetworkServer)
        server._lock = threading.RLock()
        server._ownership = InputOwnership("peer-device")
        server._local_mode = False
        server._peers = {"peer-device": {"channel": FakeChannel()}}
        server._capture = FakeCapture()
        server.on_log = lambda _message: None

        self.assertTrue(server.set_local_mode(True))
        self.assertEqual(
            server._peers["peer-device"]["channel"].messages[-1],
            {"version": 3, "kind": "release_inputs"},
        )


    def test_linux_has_x11_input_dependency(self):
        import sys
        if sys.platform.startswith("linux"):
            import Xlib  # noqa: F401


if __name__ == "__main__":
    unittest.main()
