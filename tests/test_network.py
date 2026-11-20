import socket
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.components.core import network


class NetworkDetailsTests(unittest.TestCase):
    def _interface_data(self):
        return {
            "Ethernet": [
                SimpleNamespace(
                    family=socket.AF_INET,
                    address="192.168.1.20",
                    netmask="255.255.255.0",
                )
            ]
        }

    @patch("app.components.core.network.get_active_network_info")
    @patch("app.components.core.network.psutil.net_if_addrs")
    @patch("app.components.core.network.platform.system", return_value="Windows")
    @patch("app.components.core.network.subprocess.run")
    def test_ipconfig_non_utf8_output_does_not_crash(
        self, run, _system, net_if_addrs, active_info
    ):
        active_info.return_value = ("Ethernet", "192.168.1.20")
        net_if_addrs.return_value = self._interface_data()
        run.return_value = SimpleNamespace(
            stdout=b"Adaptador Ethernet\n   DNS Servers . . . : 8.8.8.8\n   DNS Servers . . . : 1.1.1.1\n\xa2"
        )
        result = network.get_network_details()
        self.assertEqual(result, (
            "Ethernet", "192.168.1.20", "255.255.255.0", "8.8.8.8, 1.1.1.1"
        ))

    @patch("app.components.core.network.get_active_network_info")
    @patch("app.components.core.network.psutil.net_if_addrs")
    @patch("app.components.core.network.platform.system", return_value="Windows")
    @patch("app.components.core.network.subprocess.run")
    def test_missing_ipconfig_stdout_is_safe(
        self, run, _system, net_if_addrs, active_info
    ):
        active_info.return_value = ("Ethernet", "192.168.1.20")
        net_if_addrs.return_value = self._interface_data()
        run.return_value = SimpleNamespace(stdout=None)
        result = network.get_network_details()
        self.assertEqual(result, (
            "Ethernet", "192.168.1.20", "255.255.255.0", "Unavailable"
        ))


if __name__ == "__main__":
    unittest.main()
