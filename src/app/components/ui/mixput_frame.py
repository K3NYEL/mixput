import tkinter as tk

from app.components import theme
from .server_preferences import create_server_preferences


def create_mixput_frame(parent):
    container = tk.Frame(
        parent,
        bg=theme.CURRENT_THEME["bg_secondary"],
        highlightbackground=theme.CURRENT_THEME["border"],
        highlightthickness=2,
    )
    container.pack(
        fill=tk.BOTH, expand=True, padx=5, pady=5, side=tk.TOP
    )

    container.server_preferences = create_server_preferences(container)
    return container
