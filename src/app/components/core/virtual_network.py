"""Application-level virtual addressing for Mixput overlay sessions.

These addresses identify peers inside Mixput only. They are not assigned to
operating-system interfaces and do not route arbitrary system traffic.
"""
import hashlib
import ipaddress
import threading


DEFAULT_NETWORK = ipaddress.ip_network("10.77.0.0/16")
HOST_VIRTUAL_IP = ipaddress.ip_address("10.77.0.1")


class VirtualNetworkManager:
    """Allocate deterministic, collision-safe virtual IPv4 addresses per session."""

    def __init__(self, host_device_id, network=DEFAULT_NETWORK):
        if not isinstance(host_device_id, str) or len(host_device_id) != 32:
            raise ValueError("A valid persistent Mixput device identity is required.")
        self.network = ipaddress.ip_network(network)
        if self.network.version != 4 or self.network.prefixlen > 24:
            raise ValueError("The Mixput virtual network must be an IPv4 network /24 or larger.")
        if HOST_VIRTUAL_IP not in self.network:
            raise ValueError("The configured virtual network must contain the host address.")
        self.host_device_id = host_device_id
        self.host_ip = str(HOST_VIRTUAL_IP)
        self._lock = threading.RLock()
        self._by_device = {host_device_id: self.host_ip}
        self._by_address = {self.host_ip: host_device_id}

    @property
    def network_cidr(self):
        return str(self.network)

    def reserve(self, device_id, address):
        """Restore an existing assignment while preventing address collisions."""
        if not isinstance(device_id, str) or len(device_id) != 32:
            raise ValueError("A valid persistent Mixput device identity is required.")
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as error:
            raise ValueError("Invalid Mixput virtual address.") from error
        if (
            parsed.version != 4
            or parsed not in self.network
            or parsed in (self.network.network_address, self.network.broadcast_address)
            or parsed == HOST_VIRTUAL_IP
        ):
            raise ValueError("The address is not usable in the Mixput virtual network.")
        address = str(parsed)
        with self._lock:
            current = self._by_device.get(device_id)
            owner = self._by_address.get(address)
            if current and current != address:
                raise ValueError("The device already has another Mixput virtual address.")
            if owner and owner != device_id:
                raise ValueError("The Mixput virtual address is already assigned.")
            self._by_device[device_id] = address
            self._by_address[address] = device_id
        return address

    def address_for(self, device_id):
        if not isinstance(device_id, str) or len(device_id) != 32:
            raise ValueError("A valid Mixput device identity is required.")
        with self._lock:
            existing = self._by_device.get(device_id)
            if existing:
                return existing

            usable_count = self.network.num_addresses - 2
            digest = hashlib.blake2s(device_id.encode("ascii"), digest_size=4).digest()
            offset = 1 + (int.from_bytes(digest, "big") % usable_count)
            for _ in range(usable_count):
                address = str(self.network.network_address + offset)
                if address not in self._by_address:
                    self._by_device[device_id] = address
                    self._by_address[address] = device_id
                    return address
                offset += 1
                if offset >= self.network.num_addresses - 1:
                    offset = 1
            raise RuntimeError("The Mixput virtual network has no available addresses.")

    def snapshot(self):
        with self._lock:
            return dict(self._by_device)
