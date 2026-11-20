import socket
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

from app.components import theme
from .ui.mixput_frame import create_mixput_frame
from .core.device_info import get_device_architecture
from .core.network import get_active_network_info
from .core.device_discovery import DeviceDiscovery
from .core.updater import (
    obtain_version,
    check_for_update,
    download_and_stage,
    apply_update_and_restart,
    get_update_log_path,
    consume_update_diagnostics,
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
        self.discovered_devices = []
        self.discovery = DeviceDiscovery(on_devices=self._queue_discovered_devices)

        self._build_shell()
        self._build_pages()
        self.connection_panel.server_preferences.on_sharing_changed = self._set_discovery_sharing
        self.discovery.start()
        self.show_page("home")
        self.after(1500, self.check_for_updates)
        self.after(1800, self._show_update_diagnostics)

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
        brand.pack(side=tk.LEFT, padx=16, pady=9)

        # Keep the app mark beside the product name in the top navigation.
        self._brand_icon = None
        icon_root = Path(
            getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])
        )
        icon_path = icon_root / "public" / "assets" / "mixput-ico.png"
        if icon_path.is_file():
            try:
                with Image.open(icon_path) as source:
                    icon_image = source.convert("RGBA")
                    icon_image.thumbnail((36, 36), Image.Resampling.LANCZOS)
                    self._brand_icon = ImageTk.PhotoImage(icon_image)
                tk.Label(
                    brand, image=self._brand_icon,
                    bg=c["bg_secondary"], bd=0,
                ).pack(side=tk.LEFT, padx=(0, 10))
            except (OSError, tk.TclError):
                self._brand_icon = None

        brand_text = tk.Frame(brand, bg=c["bg_secondary"])
        brand_text.pack(side=tk.LEFT, anchor=tk.CENTER)
        tk.Label(
            brand_text, text="MIXPUT", font=("Arial", 16, "bold"),
            bg=c["bg_secondary"], fg=c["text_primary"],
        ).pack(anchor=tk.W)
        tk.Label(
            brand_text, text=f"Version {self.current_version}",
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

    def _heading(self, parent, title, subtitle=None):
        c = self.CURRENT_THEME
        tk.Label(
            parent, text=title, font=("Arial", 20, "bold"),
            bg=c["bg_main"], fg=c["text_primary"],
        ).pack(anchor=tk.W, pady=(12, 14))

    def _card(self, parent, title, detail):
        c = self.CURRENT_THEME
        card = tk.Frame(
            parent, bg=c["bg_secondary"],
            highlightbackground=c["border"], highlightthickness=1,
        )
        tk.Label(
            card, text=title, font=("Arial", 11, "bold"),
            bg=c["bg_secondary"], fg=c["text_primary"],
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
        self._card(
            home, "Connection status",
            "No remote computer is connected yet. Open Connection to start sharing or join another laptop.",
        ).pack(fill=tk.X, pady=(0, 10))

        cards = tk.Frame(home, bg=c["bg_main"])
        cards.pack(fill=tk.X)
        self._card(
            cards, "This computer",
            f"{socket.gethostname()}\\nThis is the computer that can share its input.",
        ).pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self._card(
            cards, "Other computer",
            "Select another laptop and request access. New devices must be approved on the host.",
        ).pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        tk.Button(
            home, text="Open connection setup",
            command=lambda: self.show_page("connection"),
            relief=tk.FLAT, cursor="hand2", padx=16, pady=10,
            bg=c["border"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        ).pack(anchor=tk.W, pady=16)

        connection = self._page("connection")
        self._heading(
            connection, "Connection",
            "Choose which laptop shares its keyboard and mouse, or connect as the receiver.",
        )
        self.connection_panel = create_mixput_frame(connection)

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

        nearby = tk.Frame(devices, bg=c["bg_main"])
        nearby.pack(fill=tk.BOTH, expand=True, pady=(18, 0))
        tk.Label(
            nearby, text="Nearby Mixput devices", font=("Arial", 14, "bold"),
            bg=c["bg_main"], fg=c["text_primary"],
        ).pack(anchor=tk.W, pady=(0, 4))
        self.discovery_status = tk.Label(
            nearby, text="Searching this local network…",
            font=("Arial", 9), bg=c["bg_main"], fg=c["text_secondary"],
        )
        self.discovery_status.pack(anchor=tk.W, pady=(0, 8))
        list_frame = tk.Frame(
            nearby, bg=c["bg_secondary"],
            highlightbackground=c["border"], highlightthickness=1,
        )
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.devices_list = tk.Listbox(
            list_frame, height=7, relief=tk.FLAT, borderwidth=0,
            bg=c["bg_secondary"], fg=c["text_primary"],
            selectbackground=c["border"], selectforeground=c["text_primary"],
            activestyle="none", font=("Arial", 10),
        )
        self.devices_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.devices_list.bind("<<ListboxSelect>>", self._select_discovered_device)
        actions = tk.Frame(nearby, bg=c["bg_main"])
        actions.pack(fill=tk.X, pady=(8, 0))
        self.use_device_button = tk.Button(
            actions, text="Use selected device",
            command=self._use_selected_device, state=tk.DISABLED,
            relief=tk.FLAT, cursor="hand2", padx=14, pady=8,
            bg=c["border"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        )
        self.use_device_button.pack(side=tk.LEFT)
        tk.Label(
            actions, text="Only devices currently sharing are connectable.",
            font=("Arial", 8), bg=c["bg_main"], fg=c["text_secondary"],
        ).pack(side=tk.LEFT, padx=10)

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


    def _queue_discovered_devices(self, devices):
        try:
            self.after(0, self._apply_discovered_devices, devices)
        except tk.TclError:
            pass

    def _apply_discovered_devices(self, devices):
        previous_devices = self.discovered_devices
        selected = self.devices_list.curselection()
        selected_id = None
        if selected and selected[0] < len(previous_devices):
            selected_id = previous_devices[selected[0]]["id"]
        self.discovered_devices = devices
        self.devices_list.delete(0, tk.END)
        self.use_device_button.configure(state=tk.DISABLED)
        for device in devices:
            state = "Sharing" if device["sharing"] else "Available"
            self.devices_list.insert(
                tk.END, f'{device["name"]}    {device["ip"]}    ·    {state}'
            )
        if not devices:
            self.discovery_status.configure(
                text="No other Mixput devices found. Keep both apps open on the same LAN."
            )
            self.use_device_button.configure(state=tk.DISABLED)
            return
        self.discovery_status.configure(
            text=f"{len(devices)} Mixput device(s) detected on this network."
        )
        if selected_id:
            for index, device in enumerate(devices):
                if device["id"] == selected_id:
                    self.devices_list.selection_set(index)
                    self._select_discovered_device()
                    break

    def _select_discovered_device(self, _event=None):
        selected = self.devices_list.curselection()
        if not selected or selected[0] >= len(self.discovered_devices):
            self.use_device_button.configure(state=tk.DISABLED)
            return
        device = self.discovered_devices[selected[0]]
        self.use_device_button.configure(
            state=tk.NORMAL if device["sharing"] else tk.DISABLED
        )

    def _use_selected_device(self):
        selected = self.devices_list.curselection()
        if not selected or selected[0] >= len(self.discovered_devices):
            return
        device = self.discovered_devices[selected[0]]
        if not device["sharing"]:
            return
        panel = self.connection_panel.server_preferences
        panel.set_discovered_device(device["ip"], device["port"])
        self.show_page("connection")

    def _set_discovery_sharing(self, sharing, port):
        self.discovery.set_endpoint(tcp_port=port, sharing=sharing)

    def show_page(self, page_id):
        if page_id not in self._pages:
            return
        for page in self._pages.values():
            page.pack_forget()
        self._pages[page_id].pack(fill=tk.BOTH, expand=True)
        self.current_page = page_id
        for key, button in self._nav_buttons.items():
            button.configure(
                bg=self.CURRENT_THEME["border"] if key == page_id
                else self.CURRENT_THEME["bg_secondary"],
                fg=self.CURRENT_THEME["text_primary"],
            )

    def toggle_theme(self):
        self.DARK_THEME = not self.DARK_THEME
        self.CURRENT_THEME = (
            self.theme.DARK_THEME if self.DARK_THEME else self.theme.LIGHT_THEME
        )
        theme.CURRENT_THEME = self.CURRENT_THEME
        self.theme_apply()

    def theme_apply(self):
        """Recolor widgets in place; never tear down an active network session."""
        c = self.CURRENT_THEME
        self.configure(bg=c["bg_main"])
        self._recolor_tree(self, c)
        self.theme_button.configure(
            bg=c["bg_main"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        )
        self.update_button.configure(
            bg=c["bg_main"], fg=c["text_primary"],
            activebackground=c["border"], activeforeground=c["text_primary"],
        )
        for key, button in self._nav_buttons.items():
            button.configure(
                bg=c["border"] if key == self.current_page else c["bg_secondary"],
                fg=c["text_primary"], activebackground=c["border"],
                activeforeground=c["text_primary"],
            )
        if hasattr(self, "connection_panel"):
            panel = getattr(self.connection_panel, "server_preferences", None)
            if panel is not None:
                panel.apply_theme(c)

    def _recolor_tree(self, parent, colors):
        surface_frames = {
            self.topbar, self.sidebar,
        }
        main_frames = {
            self, self.shell, self.body, self.page_host,
            *self._pages.values(),
        }
        for child in parent.winfo_children():
            try:
                if isinstance(child, tk.Frame):
                    bg = colors["bg_main"] if child in main_frames else colors["bg_secondary"]
                    child.configure(
                        bg=bg, highlightbackground=colors["border"],
                    )
                elif isinstance(child, tk.Label):
                    parent_bg = child.master.cget("bg")
                    child.configure(
                        bg=parent_bg,
                        fg=colors["text_secondary"] if child.cget("fg") in
                        (self.theme.LIGHT_THEME["text_secondary"], self.theme.DARK_THEME["text_secondary"])
                        else colors["text_primary"],
                    )
                elif isinstance(child, tk.Button):
                    child.configure(
                        bg=colors["bg_secondary"], fg=colors["text_primary"],
                        activebackground=colors["border"],
                        activeforeground=colors["text_primary"],
                    )
                elif isinstance(child, tk.Entry):
                    child.configure(
                        bg=colors["bg_main"], fg=colors["text_primary"],
                        insertbackground=colors["text_primary"],
                    )
                elif isinstance(child, tk.Text):
                    child.configure(
                        bg=colors["bg_main"], fg=colors["text_secondary"],
                        insertbackground=colors["text_primary"],
                    )
                self._recolor_tree(child, colors)
            except tk.TclError:
                continue

    def destroy(self):
        if hasattr(self, "discovery"):
            self.discovery.stop()
        super().destroy()

    def _show_update_diagnostics(self):
        details = consume_update_diagnostics()
        if not details:
            return
        log_path = get_update_log_path()
        messagebox.showwarning(
            "Previous update did not complete",
            "Mixput detected an error during the previous update attempt. "
            "The current installed copy was opened.\n\n"
            + details + "\n\nFull log: " + str(log_path),
            parent=self.winfo_toplevel(),
        )

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

    def _show_update_progress(self, version):
        colors = self.CURRENT_THEME
        window = tk.Toplevel(self.winfo_toplevel())
        window.title("Updating Mixput")
        window.transient(self.winfo_toplevel())
        window.resizable(False, False)
        window.configure(bg=colors["bg_main"])
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        frame = tk.Frame(window, bg=colors["bg_main"], padx=22, pady=18)
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(frame, text=f"Installing Mixput {version}", font=("Arial", 14, "bold"),
                 bg=colors["bg_main"], fg=colors["text_primary"]).pack(anchor=tk.W)
        self._update_status = tk.Label(frame, text="Preparing download…", font=("Arial", 9),
                                       bg=colors["bg_main"], fg=colors["text_secondary"])
        self._update_status.pack(anchor=tk.W, pady=(10, 7))
        self._update_progressbar = ttk.Progressbar(frame, length=420, mode="indeterminate", maximum=100)
        self._update_progressbar.pack(fill=tk.X, pady=(0, 8))
        self._update_percent = tk.Label(frame, text="Waiting for server", font=("Arial", 8),
                                        bg=colors["bg_main"], fg=colors["text_secondary"])
        self._update_percent.pack(anchor=tk.E)
        self._update_log = tk.Text(frame, height=5, width=58, state=tk.DISABLED,
                                   relief=tk.FLAT, bg=colors["bg_secondary"],
                                   fg=colors["text_secondary"], font=("Consolas", 8), wrap=tk.WORD)
        self._update_log.pack(fill=tk.X, pady=(12, 0))
        self._update_window = window
        window.update_idletasks()
        window.geometry("+%d+%d" % (self.winfo_rootx() + 80, self.winfo_rooty() + 80))

    def _update_progress(self, phase, downloaded=0, total=0, message=""):
        if not hasattr(self, "_update_window") or not self._update_window.winfo_exists():
            return
        labels = {
            "download": "Downloading update…", "verify": "Verifying downloaded files…",
            "extract": "Extracting update…", "ready": "Download verified.",
            "install": "Installing update…", "restart": "Restarting Mixput…",
            "error": "Update failed.",
        }
        self._update_status.configure(text=labels.get(phase, phase.title()))
        if phase == "download" and total > 0:
            self._update_progressbar.stop()
            self._update_progressbar.configure(mode="determinate", maximum=total, value=downloaded)
            self._update_percent.configure(text=f"{downloaded / total * 100:.0f}%")
        elif phase == "download":
            self._update_progressbar.configure(mode="indeterminate")
            self._update_progressbar.start(12)
            self._update_percent.configure(text="Downloading…")
        elif phase in ("verify", "extract", "install"):
            self._update_progressbar.configure(mode="indeterminate")
            self._update_progressbar.start(12)
            self._update_percent.configure(text="Please wait…")
        elif phase in ("ready", "restart"):
            self._update_progressbar.stop()
            self._update_progressbar.configure(mode="determinate", maximum=1, value=1)
            self._update_percent.configure(text="100%")
        if message:
            self._update_log.configure(state=tk.NORMAL)
            self._update_log.insert(tk.END, message + "\n")
            self._update_log.see(tk.END)
            self._update_log.configure(state=tk.DISABLED)

    def _queue_update_progress(self, phase, downloaded=0, total=0, message=""):
        try:
            self.after(0, self._update_progress, phase, downloaded, total, message)
        except tk.TclError:
            pass

    def _download_update(self, info):
        if self._update_install_running:
            return
        self._update_install_running = True
        self.update_button.configure(state=tk.DISABLED)
        self._show_update_progress(info.get("version", "new version"))
        self._queue_update_progress("download", 0, 0, "Starting secure HTTPS download.")

        def worker():
            try:
                staged_dir = download_and_stage(
                    info["url"], info["name"], progress_callback=self._queue_update_progress
                )
                self.after(0, lambda: self._apply_staged_update(staged_dir))
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda: self._update_install_failed(error))

        threading.Thread(target=worker, daemon=True, name="MixputUpdaterDownload").start()

    def _apply_staged_update(self, staged_dir):
        try:
            self._update_progress("install", 0, 0, "Launching the platform update helper.")
            apply_update_and_restart(staged_dir, progress_callback=self._queue_update_progress)
        except Exception as exc:
            self._update_install_failed(str(exc))

    def _update_install_failed(self, error):
        self._update_install_running = False
        self.update_button.configure(state=tk.NORMAL)
        self._update_progress("error", 0, 0, "Update failed: " + error)
        if hasattr(self, "_update_window") and self._update_window.winfo_exists():
            self._update_status.configure(text="Update failed. Your current version is still installed.")
            self._update_percent.configure(text="See details below")
            self._update_progressbar.stop()
            self._update_progressbar.configure(mode="determinate", maximum=1, value=0)
            tk.Button(self._update_window, text="Close", command=self._update_window.destroy,
                      relief=tk.FLAT, padx=14, pady=6).pack(pady=(8, 0), anchor=tk.E)
        messagebox.showerror(
            "Update error", f"Could not install the update:\n{error}",
            parent=self.winfo_toplevel(),
        )
