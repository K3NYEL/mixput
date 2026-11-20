import tempfile
import unittest
from pathlib import Path

from app.components.core.pairing_store import PairingStore
from app.components.core.virtual_network import VirtualNetworkManager


class VirtualNetworkTests(unittest.TestCase):
    def test_host_has_reserved_virtual_address(self):
        network = VirtualNetworkManager("a" * 32)
        self.assertEqual(network.host_ip, "10.77.0.1")
        self.assertEqual(network.network_cidr, "10.77.0.0/16")

    def test_devices_receive_unique_virtual_addresses(self):
        network = VirtualNetworkManager("a" * 32)
        first = network.address_for("b" * 32)
        second = network.address_for("c" * 32)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("10.77."))
        self.assertTrue(second.startswith("10.77."))
        self.assertEqual(network.address_for("b" * 32), first)

    def test_saved_device_address_survives_manager_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pairing.json"
            store = PairingStore(path)
            host_id, client_id = "a" * 32, "b" * 32
            store.authorize_client(client_id, "Laptop B", "192.168.1.20", "test-token")

            first_manager = VirtualNetworkManager(host_id)
            assigned = first_manager.address_for(client_id)
            self.assertTrue(store.set_client_virtual_ip(client_id, assigned))

            reloaded_store = PairingStore(path)
            second_manager = VirtualNetworkManager(host_id)
            saved = reloaded_store.get_authorized_client(client_id)["virtual_ip"]
            self.assertEqual(second_manager.reserve(client_id, saved), assigned)
            self.assertEqual(second_manager.address_for(client_id), assigned)

    def test_invalid_device_identity_is_rejected(self):
        network = VirtualNetworkManager("a" * 32)
        with self.assertRaises(ValueError):
            network.address_for("not-a-device-id")


if __name__ == "__main__":
    unittest.main()
