import tkinter as tk

from app.components import theme

def create_mixput_frame(self):
    self.mixput_preferences_container = tk.Frame(
        self,
        bg=theme.CURRENT_THEME["bg_secondary"],
        highlightbackground=theme.CURRENT_THEME["border"],
        highlightthickness=2,
    )
    self.mixput_preferences_container.pack(
        fill=tk.BOTH, expand=True, padx=5, pady=5, side=tk.TOP
    )
