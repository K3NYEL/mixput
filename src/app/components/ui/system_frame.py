import tkinter as tk

from app.components import theme
from app.components.core.network import get_active_network_info


def create_system_preferences(self):
    self.system_preferences_container = tk.Frame(
        self,
        bg=theme.CURRENT_THEME["bg_secondary"],
        highlightbackground=theme.CURRENT_THEME["border"],
        highlightthickness=1,
    )
    self.system_preferences_container.pack(
        fill=tk.BOTH, expand=True, padx=5, pady=5, side=tk.TOP
    )

    self.ip_label = tk.Label(
        self.system_preferences_container,
        text="IP Address: ",
        font=("Arial", 12),
        bg=theme.CURRENT_THEME["bg_secondary"],
        fg=theme.CURRENT_THEME["text_primary"],
    )
    self.ip_label.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)
