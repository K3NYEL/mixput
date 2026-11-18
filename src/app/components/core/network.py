import socket 
import psutil 

def get_active_network_info() -> tuple[str, str] | None:
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    preferred_ip = None

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            preferred_ip = s.getsockname()[0]

    except OSError:
        pass

    for iface, addr_list in addrs.items():
        iface_stats = stats.get(iface)
        if not iface_stats or not iface_stats.isup:
            continue

        for addr in addr_list:
            if addr.family == socket.AF_INET:
                ip_address = addr.address
                if preferred_ip and ip_address == preferred_ip:
                    return iface, ip_address
                elif not preferred_ip:
                    return iface, ip_address

    for iface, addr_list in addrs.items():
        iface_stats = stats.get(iface)
        if not iface_stats or not iface_stats.isup:
            continue

        for addr in addr_list:
            if addr.family == socket.AF_INET:
                return iface, addr.address

    return "Sin conexión", "0.0.0.0"