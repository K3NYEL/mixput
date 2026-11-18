import socket
import tkinter as tk

from app.components import theme
from app.components.core.device_info import get_device_architecture
from app.components.core.network import get_active_network_info


def create_system_preferences(self):
    self.system_preferences_container = tk.Frame(
        self,
        bg=theme.CURRENT_THEME["bg_secondary"],
        highlightbackground=theme.CURRENT_THEME["border"],
        highlightthickness=2,
    )
    self.system_preferences_container.pack(fill=tk.BOTH, padx=5, pady=5, side=tk.TOP)

    self.name_content = tk.Frame(
        self.system_preferences_container,
        bg=theme.CURRENT_THEME["bg_secondary"],
    )
    self.name_content.pack(
        fill=tk.BOTH, expand=True, side=tk.LEFT, anchor=tk.W, padx=5, pady=5
    )

    self.sep = tk.Frame(
        self.system_preferences_container,
        height=2,
        bg=theme.CURRENT_THEME["border"],
    )
    self.sep.pack(fill=tk.BOTH, side=tk.LEFT, padx=5, pady=5)

    labels = (
        ("ip_label", "IP:"),
        ("iface_label", "Interface:"),
        ("device_label", "Device Name:"),
        ("system_arch_label", "System Architecture:"),
    )

    for attribute, label_text in labels:
        label = tk.Label(
            self.name_content,
            text=label_text,
            font=("Arial", 12),
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_primary"],
        )
        label.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)
        setattr(self, attribute, label)

    self.spec_content = tk.Frame(
        self.system_preferences_container,
        bg=theme.CURRENT_THEME["bg_secondary"],
    )
    self.spec_content.pack(
        fill=tk.BOTH, expand=True, side=tk.RIGHT, anchor=tk.W, padx=5, pady=5
    )

    interface, ip_address = get_active_network_info()
    values = (
        ("ip_show", ip_address),
        ("iface_show", interface),
        ("device_show", socket.gethostname()),
        ("system_arch_show", get_device_architecture()),
    )

    for attribute, value in values:
        label = tk.Label(
            self.spec_content,
            text=value,
            font=("Arial", 12),
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_secondary"],
        )
        label.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)
        setattr(self, attribute, label)
