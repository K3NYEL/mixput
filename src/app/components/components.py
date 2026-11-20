
import tkinter as tk
import threading
from tkinter import messagebox
from tkinter_icons import LucideIcon

from app.components import theme
from .ui.system_frame import create_system_preferences, apply_system_theme
from .ui.mixput_frame import create_mixput_frame
from .core.updater import (
    obtain_version,
    check_for_update,
    download_and_stage,
    apply_update_and_restart,
)



class App(tk.Canvas):
    def __init__(self):
        super().__init__()

        self.current_version = obtain_version()
        self.theme = theme
        self.DARK_THEME = False
        self.CURRENT_THEME = self.theme.LIGHT_THEME

        self._update_check_running = False
        self._update_install_running = False

        self.create_widgets()
        self.create_main_content()

        self.moon_icon = LucideIcon(
            "moon", size=20, color=self.CURRENT_THEME["text_primary"]
        )
        self.sun_icon = LucideIcon(
            "sun", size=20, color=self.CURRENT_THEME["text_primary"]
        )

        # Comprobar actualizaciones después de inicializar la interfaz.
        self.after(1500, self.check_for_updates)

    def check_for_updates(self, manual=True):
        """Inicia la comprobación sin bloquear la interfaz."""
        if self._update_check_running or self._update_install_running:
            return

        self._update_check_running = True
        self.update_button.config(state=tk.DISABLED)

        def worker():
            try:
                info = check_for_update()
                self.after(
                    0,
                    lambda: self._finish_update_check(info, manual),
                )
            except Exception as exc:
                error = str(exc)
                self.after(
                    0,
                    lambda: self._finish_update_check(
                        None, manual, error
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check(self, info, manual, error=None):
        self._update_check_running = False
        self.update_button.config(state=tk.NORMAL)

        if error:
            if manual:
                messagebox.showerror(
                    "Update error",
                    f"Could not check for updates:\n{error}",
                    parent=self.winfo_toplevel(),
                )
            return

        if not info:
            if manual:
                messagebox.showinfo(
                    "Mixput",
                    "You are using the latest available version.",
                    parent=self.winfo_toplevel(),
                )
            return

        self._ask_to_install_update(info)

    def _ask_to_install_update(self, info):
        version = info.get("version", "unknown")

        confirmed = messagebox.askyesno(
            "Update available",
            (
                f"A new Mixput version is available: {version}\n\n"
                f"Current version: {self.current_version}\n\n"
                "Do you want to download and install this update?\n"
                "Mixput will close and restart after the download."
            ),
            parent=self.winfo_toplevel(),
        )

        if not confirmed:
            return

        self._download_update(info)

    def _download_update(self, info):
        """Descarga y prepara la actualización en segundo plano."""
        if self._update_install_running:
            return

        self._update_install_running = True
        self.update_button.config(state=tk.DISABLED)

        def worker():
            try:
                staged_dir = download_and_stage(info["url"])

                # La aplicación del update debe ejecutarse en el hilo
                # principal: apply_update_and_restart puede cerrar la app.
                self.after(
                    0,
                    lambda: self._apply_staged_update(staged_dir),
                )
            except Exception as exc:
                error = str(exc)
                self.after(
                    0,
                    lambda: self._update_install_failed(error),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _apply_staged_update(self, staged_dir):
        try:
            apply_update_and_restart(staged_dir)
        except Exception as exc:
            self._update_install_failed(str(exc))

    def _update_install_failed(self, error):
        self._update_install_running = False
        self.update_button.config(state=tk.NORMAL)

        messagebox.showerror(
            "Update error",
            f"Could not install the update:\n{error}",
            parent=self.winfo_toplevel(),
        )

    def create_widgets(self):
        self.charge_icon_theme = LucideIcon(
            "sun-moon", size=20, color=self.CURRENT_THEME["text_primary"]
        )

        self.canvas = tk.Canvas(
            self,
            bg=theme.CURRENT_THEME["bg_main"],
            highlightthickness=0,
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
            side=tk.RIGHT,
            anchor=tk.N,
        )

        self.update_button = tk.Button(
            self.nav_frame,
            text="Updates",
            command=lambda: self.check_for_updates(manual=True),
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_primary"],
            activebackground=theme.CURRENT_THEME["bg_secondary"],
            activeforeground=theme.CURRENT_THEME["text_primary"],
            highlightbackground=theme.CURRENT_THEME["border"],
            relief=tk.FLAT,
            cursor="hand2",
        )
        self.update_button.pack(
            padx=5,
            pady=5,
            side=tk.RIGHT,
            anchor=tk.N,
        )

    def create_main_content(self):
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

        self.header_frame = tk.Frame(
            self.main_content,
            bg=theme.CURRENT_THEME["bg_secondary"],
        )
        self.header_frame.pack(
            fill="x",
            padx=5,
            pady=(5, 0),
            side=tk.TOP,
        )

        self.system_preferences_label = tk.Label(
            self.header_frame,
            text="Device & Network",
            font=("Arial", 14),
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_primary"],
        )
        self.system_preferences_label.pack(side=tk.LEFT, anchor=tk.W)

        self.system = create_system_preferences(self.main_content)

        self.mixput_preferences_label = tk.Label(
            self.main_content,
            text="Keyboard & Mouse Sharing",
            font=("Arial", 14),
            bg=theme.CURRENT_THEME["bg_secondary"],
            fg=theme.CURRENT_THEME["text_primary"],
        )
        self.mixput_preferences_label.pack(
            side=tk.TOP,
            anchor=tk.W,
            padx=5,
            pady=5,
        )

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
        theme.CURRENT_THEME = t

        self.config(bg=t["bg_main"])
        self.canvas.config(bg=t["bg_main"])
        self.nav_frame.config(bg=t["bg_secondary"])
        self.main_content.config(bg=t["bg_secondary"])

        self.lbl_title.config(
            bg=t["bg_secondary"],
            fg=t["text_primary"],
        )
        self.header_frame.config(bg=t["bg_secondary"])

        self.system_preferences_label.config(
            bg=t["bg_secondary"],
            fg=t["text_primary"],
        )
        self.mixput_preferences_label.config(
            bg=t["bg_secondary"],
            fg=t["text_primary"],
        )

        self.theme_button.config(
            bg=t["bg_secondary"],
            fg=t["text_primary"],
            activebackground=t["bg_secondary"],
            activeforeground=t["text_primary"],
        )

        self.update_button.config(
            bg=t["bg_secondary"],
            fg=t["text_primary"],
            activebackground=t["bg_secondary"],
            activeforeground=t["text_primary"],
        )
