import ipaddress
import socket
import platform
import re
import subprocess

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



def get_network_details() -> tuple[str, str, str, str]:
    """Return active IPv4 interface, address, subnet mask and DNS servers.

    DNS values are read from the operating system's resolver configuration;
    unavailable values are reported explicitly rather than guessed.
    """
    interface, address = get_active_network_info()
    netmask = "Unavailable"
    dns_servers = []

    if address != "0.0.0.0":
        for entry in psutil.net_if_addrs().get(interface, []):
            if entry.family == socket.AF_INET and entry.address == address:
                netmask = entry.netmask or "Unavailable"
                break

    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["ipconfig", "/all"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            lines = result.stdout.splitlines()
            capture = False
            for line in lines:
                if re.search(r"DNS Servers?\s*:", line, re.IGNORECASE):
                    capture = True
                    value = line.split(":", 1)[1].strip()
                    if value and _is_usable_ipv4(value):
                        dns_servers.append(value)
                    continue
                if capture:
                    value = line.strip()
                    if value and _is_usable_ipv4(value):
                        dns_servers.append(value)
                    else:
                        capture = False
        else:
            with open("/etc/resolv.conf", encoding="utf-8") as resolver:
                for line in resolver:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "nameserver" and _is_usable_ipv4(parts[1]):
                        dns_servers.append(parts[1])
    except (OSError, subprocess.SubprocessError):
        pass

    dns_text = ", ".join(dict.fromkeys(dns_servers)) if dns_servers else "Unavailable"
    return interface, address, netmask, dns_text
