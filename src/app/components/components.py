import socket
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter_icons import LucideIcon

from app.components import theme
from .ui.mixput_frame import create_mixput_frame
from .core.device_info import get_device_architecture
from .core.network import get_active_network_info
from .core.updater import (
    obtain_version,
    check_for_update,
    download_and_stage,
    apply_update_and_restart,
)


class App(tk.Canvas):
    """Main Mixput window with a compact, page-based desktop layout."""

    NAV_ITEMS = (
        ("home", "Home"),
        ("connection", "Connection"),
        ("devices", "Devices"),
        ("settings", "Settings"),
    )

    def __init__(self):
        super().__init__()
        self.current_version = obtain_version()
        self.theme = theme
        self.DARK_THEME = False
        self.CURRENT_THEME = self.theme.LIGHT_THEME
        self._update_check_running = False
        self._update_install_running = False
        self._pages = {}
        self._nav_buttons = {}
        self.current_page = "home"

        self._build_shell()
        self._build_pages()
        self.show_page("home")

        self.after(1500, self.check_for_updates)

    def _build_shell(self):
        c = self.CURRENT_THEME
        self.configure(bg=c["bg_main"], highlightthickness=0)

        self.shell = tk.Frame(self, bg=c["bg_main"])
        self.shell.pack(fill=tk.BOTH, expand=True)

        self.topbar = tk.Frame(
            self.shell, bg=c["bg_secondary"],
            highlightbackground=c["border"], highlightthickness=1,
        )
        self.topbar.pack(fill=tk.X, padx=12, pady=(12, 8))

        brand = tk.Frame(self.topbar, bg=c["bg_secondary"])
        brand.pack(side=tk.LEFT, padx=16, pady=11)
        tk.Label(
            brand, text="MIXPUT", font=("Arial", 16, "bold"),
            bg=c["bg_secondary"], fg=c["text_primary"],
        ).pack(anchor=tk.W)
        tk.Label(
            brand, text=f"Version {self.current_version}",
            font=("Arial", 9), bg=c["bg_secondary"],
            fg=c["text_secondary"],
        ).pack(anchor=tk.W, pady=(1, 0))

        self.update_button = tk.Button(
            self.topbar, text="Check for updates",
            command=lambda: self.check_for_updates(manual=True),
            relief=tk.FLAT, cursor="hand2", padx=12, pady=7,
            bg=c["bg_main"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        )
        self.update_button.pack(side=tk.RIGHT, padx=(4, 12), pady=12)

        self.theme_button = tk.Button(
            self.topbar, text="Light / Dark",
            command=self.toggle_theme, relief=tk.FLAT, cursor="hand2",
            padx=12, pady=7, bg=c["bg_main"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        )
        self.theme_button.pack(side=tk.RIGHT, padx=4, pady=12)

        self.body = tk.Frame(self.shell, bg=c["bg_main"])
        self.body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.sidebar = tk.Frame(
            self.body, width=178, bg=c["bg_secondary"],
            highlightbackground=c["border"], highlightthickness=1,
        )
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.sidebar.pack_propagate(False)

        tk.Label(
            self.sidebar, text="WORKSPACE", font=("Arial", 8, "bold"),
            bg=c["bg_secondary"], fg=c["text_secondary"],
        ).pack(anchor=tk.W, padx=14, pady=(18, 9))

        for page_id, label in self.NAV_ITEMS:
            button = tk.Button(
                self.sidebar, text=label, anchor=tk.W,
                command=lambda key=page_id: self.show_page(key),
                relief=tk.FLAT, bd=0, padx=14, pady=10,
                cursor="hand2", font=("Arial", 10),
                bg=c["bg_secondary"], fg=c["text_primary"],
                activebackground=c["border"],
                activeforeground=c["text_primary"],
            )
            button.pack(fill=tk.X, padx=7, pady=2)
            self._nav_buttons[page_id] = button

        self.page_host = tk.Frame(self.body, bg=c["bg_main"])
        self.page_host.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _page(self, page_id):
        frame = tk.Frame(self.page_host, bg=self.CURRENT_THEME["bg_main"])
        self._pages[page_id] = frame
        return frame

    def _heading(self, parent, title, subtitle):
        c = self.CURRENT_THEME
        tk.Label(
            parent, text=title, font=("Arial", 20, "bold"),
            bg=c["bg_main"], fg=c["text_primary"],
        ).pack(anchor=tk.W, pady=(8, 2))
        tk.Label(
            parent, text=subtitle, font=("Arial", 10),
            bg=c["bg_main"], fg=c["text_secondary"],
            wraplength=760, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 16))

    def _card(self, parent, title, detail, accent=None):
        c = self.CURRENT_THEME
        card = tk.Frame(
            parent, bg=c["bg_secondary"],
            highlightbackground=c["border"], highlightthickness=1,
        )
        tk.Label(
            card, text=title, font=("Arial", 11, "bold"),
            bg=c["bg_secondary"], fg=accent or c["text_primary"],
        ).pack(anchor=tk.W, padx=14, pady=(13, 4))
        tk.Label(
            card, text=detail, font=("Arial", 9),
            bg=c["bg_secondary"], fg=c["text_secondary"],
            justify=tk.LEFT, wraplength=280,
        ).pack(anchor=tk.W, padx=14, pady=(0, 13))
        return card

    def _build_pages(self):
        c = self.CURRENT_THEME

        home = self._page("home")
        self._heading(
            home, "Welcome to Mixput",
            "Use one keyboard and mouse across two computers on your local network.",
        )
        status = self._card(
            home, "Connection status", "No remote computer is connected yet.",
        )
        status.pack(fill=tk.X, pady=(0, 10))
        cards = tk.Frame(home, bg=c["bg_main"])
        cards.pack(fill=tk.X)
        self._card(
            cards, "This computer",
            f"{socket.gethostname()}\\nThis is the computer that can share its input.",
        ).pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self._card(
            cards, "Other computer",
            "Connect another laptop using its LAN address and pairing key.",
        ).pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        action = tk.Button(
            home, text="Open connection setup",
            command=lambda: self.show_page("connection"),
            relief=tk.FLAT, cursor="hand2", padx=16, pady=10,
            bg=c["border"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        )
        action.pack(anchor=tk.W, pady=16)

        connection = self._page("connection")
        self._heading(
            connection, "Connection",
            "Choose which laptop shares its keyboard and mouse, or connect as the receiver.",
        )
        self.connection_panel = create_mixput_frame(connection)
        self.connection_panel.pack(fill=tk.BOTH, expand=True)

        devices = self._page("devices")
        self._heading(
            devices, "Devices & network",
            "Network and system information for this computer.",
        )
        interface, ip_address = get_active_network_info()
        details = (
            ("Computer name", socket.gethostname()),
            ("Local IP address", ip_address),
            ("Network interface", interface),
            ("Platform / architecture", get_device_architecture()),
        )
        for label, value in details:
            row = tk.Frame(
                devices, bg=c["bg_secondary"],
                highlightbackground=c["border"], highlightthickness=1,
            )
            row.pack(fill=tk.X, pady=4)
            tk.Label(
                row, text=label, font=("Arial", 9),
                bg=c["bg_secondary"], fg=c["text_secondary"],
            ).pack(anchor=tk.W, padx=13, pady=(9, 1))
            tk.Label(
                row, text=value, font=("Arial", 11, "bold"),
                bg=c["bg_secondary"], fg=c["text_primary"],
            ).pack(anchor=tk.W, padx=13, pady=(0, 9))

        settings = self._page("settings")
        self._heading(
            settings, "Settings",
            "Manage the application appearance and software updates.",
        )
        self._card(
            settings, "Appearance",
            "Switch between the light and dark interface themes.",
        ).pack(fill=tk.X, pady=(0, 8))
        tk.Button(
            settings, text="Toggle light / dark theme",
            command=self.toggle_theme, relief=tk.FLAT, cursor="hand2",
            padx=13, pady=9, bg=c["bg_secondary"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        ).pack(anchor=tk.W, pady=(0, 16))
        self._card(
            settings, "Software updates",
            f"Installed version: {self.current_version}. Check for a newer release.",
        ).pack(fill=tk.X, pady=(0, 8))
        tk.Button(
            settings, text="Check for updates",
            command=lambda: self.check_for_updates(manual=True),
            relief=tk.FLAT, cursor="hand2", padx=13, pady=9,
            bg=c["bg_secondary"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        ).pack(anchor=tk.W)

    def show_page(self, page_id):
        if page_id not in self._pages:
            return
        for page in self._pages.values():
            page.pack_forget()
        self._pages[page_id].pack(fill=tk.BOTH, expand=True)
        self.current_page = page_id
        for key, button in self._nav_buttons.items():
            selected = key == page_id
            button.configure(
                bg=self.CURRENT_THEME["border"] if selected else self.CURRENT_THEME["bg_secondary"],
                fg=self.CURRENT_THEME["text_primary"],
            )

    def toggle_theme(self):
        self.DARK_THEME = not self.DARK_THEME
        self.CURRENT_THEME = (
            self.theme.DARK_THEME if self.DARK_THEME else self.theme.LIGHT_THEME
        )
        theme.CURRENT_THEME = self.CURRENT_THEME
        self._rebuild_interface()

    def _rebuild_interface(self):
        # Rebuilding keeps every page consistent with the selected palette.
        for child in self.winfo_children():
            child.destroy()
        self._pages.clear()
        self._nav_buttons.clear()
        self._build_shell()
        self._build_pages()
        self.show_page(self.current_page)

    def check_for_updates(self, manual=True):
        if self._update_check_running or self._update_install_running:
            return
        self._update_check_running = True
        self.update_button.configure(state=tk.DISABLED)

        def worker():
            try:
                info = check_for_update()
                self.after(0, lambda: self._finish_update_check(info, manual))
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda: self._finish_update_check(None, manual, error))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check(self, info, manual, error=None):
        self._update_check_running = False
        self.update_button.configure(state=tk.NORMAL)
        if error:
            if manual:
                messagebox.showerror(
                    "Update error", f"Could not check for updates:\\n{error}",
                    parent=self.winfo_toplevel(),
                )
            return
        if not info:
            if manual:
                messagebox.showinfo(
                    "Mixput", "You are using the latest available version.",
                    parent=self.winfo_toplevel(),
                )
            return
        version = info.get("version", "unknown")
        if messagebox.askyesno(
            "Update available",
            f"A new Mixput version is available: {version}\\n\\n"
            f"Current version: {self.current_version}\\n\\n"
            "Download and install this update? Mixput will restart.",
            parent=self.winfo_toplevel(),
        ):
            self._download_update(info)

    def _download_update(self, info):
        if self._update_install_running:
            return
        self._update_install_running = True
        self.update_button.configure(state=tk.DISABLED)

        def worker():
            try:
                staged_dir = download_and_stage(info["url"])
                self.after(0, lambda: self._apply_staged_update(staged_dir))
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda: self._update_install_failed(error))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_staged_update(self, staged_dir):
        try:
            apply_update_and_restart(staged_dir)
        except Exception as exc:
            self._update_install_failed(str(exc))

    def _update_install_failed(self, error):
        self._update_install_running = False
        self.update_button.configure(state=tk.NORMAL)
        messagebox.showerror(
            "Update error", f"Could not install the update:\\n{error}",
            parent=self.winfo_toplevel(),
        )
