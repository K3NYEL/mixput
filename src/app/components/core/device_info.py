import platform


def get_device_architecture() -> str:
    """Return a stable, human-readable CPU architecture label."""
    machine = platform.machine().strip().lower()

    aliases = {
        "amd64": "x64",
        "x86_64": "x64",
        "x64": "x64",
        "i386": "x86",
        "i486": "x86",
        "i586": "x86",
        "i686": "x86",
        "x86": "x86",
        "aarch64": "ARM64",
        "arm64": "ARM64",
        "armv7l": "ARM",
        "armv6l": "ARM",
    }

    return aliases.get(machine, machine.upper() or "Desconocida")
