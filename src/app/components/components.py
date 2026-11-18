import tkinter as tk
import threading
from tkinter_icons import LucideIcon

from app.components import theme
from .ui.system_frame import create_system_preferences
from .ui.mixput_frame import create_mixput_frame
from .core.updater import *
from .core.updater import obtain_version

class App(tk.Canvas):
    def __init__(self):
        super().__init__()
        self.current_version = obtain_version()
        self.theme = theme
        self.DARK_THEME = False
        self.CURRENT_THEME = self.theme.LIGHT_THEME
        self.create_widgets()
        self.create_main_content()
        self.moon_icon = LucideIcon(
            "moon", size=20, color=self.CURRENT_THEME["text_primary"]
        )
        self.sun_icon = LucideIcon(
            "sun", size=20, color=self.CURRENT_THEME["text_primary"]
        )

    def start_update_check(self, on_update_available):
        self.check_update = check_for_update()

        def worker():
            info = self.check_update
            if info:
                self.after(0, lambda: on_update_available(info))

        threading.Thread(target=worker, daemon=True).start()

    def create_widgets(self):
        self.charge_icon_theme = LucideIcon(
            "sun-moon", size=20, color=self.CURRENT_THEME["text_primary"]
        )

        self.canvas = tk.Canvas(
            self, bg=theme.CURRENT_THEME["bg_main"], highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.nav_frame = tk.Frame(
            self.canvas,
            width=200,
            height=200,
            bg=theme.CURRENT_THEME["bg_secondary"],
            highlightbackground=theme.CURRENT_THEME["border"],
            highlightthickness=1,
        )
        self.nav_frame.pack(
            padx=6,
            pady=5,
            fill="x",
            side=tk.TOP,
            anchor=tk.N,
        )

        self.lbl_title = tk.Label(
            self.nav_frame,
            text=f"Mixput v{self.current_version}",
            font=("Arial", 16),
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_primary"],
        )
        self.lbl_title.pack(
            padx=5,
            pady=5,
            fill="x",
            side=tk.LEFT,
            anchor=tk.N,
        )

        self.theme_button = tk.Button(
            self.nav_frame,
            image=self.charge_icon_theme,
            width=30,
            command=self.toggle_theme,
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_primary"],
            highlightbackground=theme.CURRENT_THEME["border"],
        )
        self.theme_button.pack(
            padx=5,
            pady=5,
            fill="x",
            side=tk.RIGHT,
            anchor=tk.N,
        )

    def create_main_content(self):
        
        # Contenedor principal
        self.main_content = tk.Frame(
            self.canvas,
            bg=theme.CURRENT_THEME["bg_secondary"],
            highlightbackground=theme.CURRENT_THEME["border"],
            highlightthickness=2,
        )
        self.main_content.pack(
            padx=5,
            pady=5,
            fill=tk.BOTH,
            expand=True,
            side=tk.TOP,
            anchor=tk.N,
        )

        # 1. Encabezado arriba
        self.header_frame = tk.Frame(
            self.main_content,
            bg=theme.CURRENT_THEME["bg_secondary"],
        )
        self.header_frame.pack(fill="x", padx=5, pady=(5, 0), side=tk.TOP)

        self.system_preferences_label = tk.Label(
            self.header_frame,
            text="System Preferences",
            font=("Arial", 14),
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_primary"],
        )
        self.system_preferences_label.pack(side=tk.LEFT, anchor=tk.W)
        self.system = create_system_preferences(self.main_content)

        self.mixput_preferences_label = tk.Label(
            self.main_content,
            text="Mixput Preferences",
            font=("Arial", 14),
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_primary"],
        )
        self.mixput_preferences_label.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=5)
        self.mixput = create_mixput_frame(self.main_content)

    def toggle_theme(self):
        self.DARK_THEME = not self.DARK_THEME

        if self.DARK_THEME:
            self.CURRENT_THEME = self.theme.DARK_THEME
            self.theme_button.config(image=self.moon_icon)
        else:
            self.CURRENT_THEME = self.theme.LIGHT_THEME
            self.theme_button.config(image=self.sun_icon)

        self.theme_apply()

    def theme_apply(self):
        t = self.CURRENT_THEME

        self.config(bg=t["bg_main"])
        self.canvas.config(bg=t["bg_main"])
        self.nav_frame.config(bg=t["bg_secondary"])
        self.main_content.config(bg=t["bg_secondary"])
        self.lbl_title.config(bg=t["bg_secondary"], fg=t["text_primary"])
        self.header_frame.config(bg=t["bg_secondary"])
        self.system_preferences_label.config(bg=t["bg_secondary"], fg=t["text_primary"])
        self.mixput_preferences_label.config(bg=t["bg_secondary"], fg=t["text_primary"])
        self.theme_button.config(
            bg=t["bg_secondary"],
            fg=t["text_primary"],
            activebackground=t["bg_secondary"],
            activeforeground=t["text_primary"],
        )
