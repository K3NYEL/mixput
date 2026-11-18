import ipaddress
import socket

import psutil


def _is_usable_ipv4(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False

    return (
        parsed.version == 4
        and not parsed.is_loopback
        and not parsed.is_link_local
        and not parsed.is_unspecified
        and not parsed.is_multicast
    )


def get_active_network_info() -> tuple[str, str]:
    """Return the active interface and its IPv4 address without admin rights.

    A UDP connect asks the local routing table which interface would be used.
    It does not send application data to the remote host.
    """
    stats = psutil.net_if_stats()
    addresses = psutil.net_if_addrs()
    preferred_ip = None

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("1.1.1.1", 53))
            preferred_ip = probe.getsockname()[0]
    except OSError:
        pass

    candidates: list[tuple[str, str]] = []

    for interface, interface_addresses in addresses.items():
        interface_stats = stats.get(interface)
        if not interface_stats or not interface_stats.isup:
            continue

        for address in interface_addresses:
            if address.family != socket.AF_INET:
                continue
            if not _is_usable_ipv4(address.address):
                continue

            candidates.append((interface, address.address))

    if preferred_ip:
        for interface, address in candidates:
            if address == preferred_ip:
                return interface, address

    if candidates:
        return candidates[0]

    return "Sin conexión", "0.0.0.0"
