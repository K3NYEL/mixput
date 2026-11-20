import unittest

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

    def test_invalid_device_identity_is_rejected(self):
        network = VirtualNetworkManager("a" * 32)
        with self.assertRaises(ValueError):
            network.address_for("not-a-device-id")


if __name__ == "__main__":
    unittest.main()
