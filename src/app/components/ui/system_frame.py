import tkinter as tk
import socket
import psutil

from app.components import theme
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
        self.system_preferences_container, height=2, bg=theme.CURRENT_THEME["border"]
    )
    self.sep.pack(fill=tk.BOTH, side=tk.LEFT, padx=5, pady=5)
    self.ip_label = tk.Label(
        self.name_content,
        text="IP: ",
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_primary"],
    )
    self.ip_label.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)

    self.iface_label = tk.Label(
        self.name_content,
        text="Interface: ",
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_primary"],
    )
    self.iface_label.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)

    self.device_label = tk.Label(
        self.name_content,
        text="Device Name: ",
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_primary"],
    )
    self.device_label.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)

    self.system_arch_label = tk.Label(
        self.name_content,
        text="System Architecture: ",
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_primary"],
    )
    self.system_arch_label.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)

    self.spec_content = tk.Frame(
        self.system_preferences_container,
        bg=theme.CURRENT_THEME["bg_secondary"],
    )
    self.spec_content.pack(
        fill=tk.BOTH, expand=True, side=tk.RIGHT, anchor=tk.W, padx=5, pady=5
    )

    iface, ip = get_active_network_info()

    self.ip_show = tk.Label(
        self.spec_content,
        text=ip,
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_secondary"],
    )
    self.ip_show.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)

    self.iface_show = tk.Label(
        self.spec_content,
        text=iface,
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_secondary"],
    )
    self.iface_show.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)

    self.device_show = tk.Label(
        self.spec_content,
        text=socket.gethostname(),
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_secondary"],
    )
    self.device_show.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)

    self.system_arch_show = tk.Label(
        self.spec_content,
        text=socket.getfqdn(),
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_secondary"],
    )
    self.system_arch_show.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)
