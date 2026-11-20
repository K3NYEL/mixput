import ipaddress
import tkinter as tk
from tkinter import messagebox

from app.components import theme
from app.components.core.input_backend import InputBackend
from app.components.core.network import get_active_network_info
from app.components.core.network_client import NetworkClient
from app.components.core.network_server import NetworkServer


class ServerPreferences(tk.Frame):
    """Visible controls for sharing input between two laptops on a LAN."""

    def __init__(self, parent):
        self.colors = theme.CURRENT_THEME
        super().__init__(parent, bg=self.colors["bg_secondary"])
        self.host_input = InputBackend(on_event=lambda event: self.server._send_input(event))
        self.remote_input = InputBackend()
        self.server = NetworkServer(
            on_log=self._queue_log,
            on_status=self._queue_server_status,
            on_pairing_key=self._show_pairing_key,
        )
        self.server.set_input_backend(self.host_input)
        self.client = NetworkClient(
            on_message=self._queue_log,
            on_status=self._queue_client_status,
            input_backend=self.remote_input,
        )
        self._build()

    def _build(self):
        c = self.colors
        self.configure(bg=c["bg_secondary"], highlightbackground=c["border"], highlightthickness=1)

        header = tk.Frame(self, bg=c["bg_secondary"])
        header.pack(fill=tk.X, padx=16, pady=(14, 10))
        tk.Label(header, text="Connect your computers", font=("Arial", 15, "bold"),
                 bg=c["bg_secondary"], fg=c["text_primary"]).pack(anchor=tk.W)
        tk.Label(header, text="Use one keyboard and mouse across two laptops on the same local network.",
                 font=("Arial", 9), bg=c["bg_secondary"], fg=c["text_secondary"]).pack(anchor=tk.W, pady=(3, 0))

        available, reason = InputBackend.availability()
        self.backend_status = tk.Label(
            self, text=("Input control ready" if available else f"Input control unavailable: {reason}"),
            font=("Arial", 9), bg=c["bg_secondary"],
            fg=c["text_secondary"] if available else "#D65A65")
        self.backend_status.pack(anchor=tk.W, padx=16, pady=(0, 8))

        cards = tk.Frame(self, bg=c["bg_secondary"])
        cards.pack(fill=tk.X, padx=12, pady=(0, 8))
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)

        host_frame = tk.LabelFrame(cards, text=" SHARE THIS COMPUTER ",
                                   bg=c["bg_secondary"], fg=c["text_primary"], padx=12, pady=10,
                                   font=("Arial", 9, "bold"))
        host_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        interface, local_ip = get_active_network_info()
        self.local_ip = local_ip
        tk.Label(host_frame, text="Your local address", bg=c["bg_secondary"],
                 fg=c["text_secondary"], font=("Arial", 8)).pack(anchor=tk.W)
        self.local_ip_label = tk.Label(host_frame, text=f"{local_ip}  ·  {interface}",
                                        bg=c["bg_secondary"], fg=c["text_primary"],
                                        font=("Arial", 10, "bold"), anchor=tk.W)
        self.local_ip_label.pack(fill=tk.X, pady=(2, 10))

        port_row = tk.Frame(host_frame, bg=c["bg_secondary"])
        port_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(port_row, text="Port", bg=c["bg_secondary"], fg=c["text_secondary"]).pack(side=tk.LEFT)
        self.server_port = self._entry(port_row, "8080", 8)
        self.server_port.pack(side=tk.RIGHT)

        host_actions = tk.Frame(host_frame, bg=c["bg_secondary"])
        host_actions.pack(fill=tk.X, pady=(0, 8))
        self.start_button = self._button(host_actions, "Start sharing", self.start_server)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.stop_button = self._button(host_actions, "Stop", self.stop_server)
        self.stop_button.configure(state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT)

        tk.Label(host_frame, text="Pairing key", bg=c["bg_secondary"],
                 fg=c["text_secondary"], font=("Arial", 8)).pack(anchor=tk.W)
        key_row = tk.Frame(host_frame, bg=c["bg_secondary"])
        key_row.pack(fill=tk.X)
        self.host_key = self._entry(key_row, "", 48)
        self.host_key.configure(state="readonly")
        self.host_key.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.copy_key_button = self._button(key_row, "Copy", self.copy_pairing_key)
        self.copy_key_button.pack(side=tk.RIGHT)

        client_frame = tk.LabelFrame(cards, text=" CONNECT TO A COMPUTER ",
                                     bg=c["bg_secondary"], fg=c["text_primary"], padx=12, pady=10,
                                     font=("Arial", 9, "bold"))
        client_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Label(client_frame, text="Host local IP address", bg=c["bg_secondary"],
                 fg=c["text_secondary"], font=("Arial", 8)).pack(anchor=tk.W)
        self.client_host = self._entry(client_frame, "", 24)
        self.client_host.pack(fill=tk.X, pady=(3, 9))

        connection_fields = tk.Frame(client_frame, bg=c["bg_secondary"])
        connection_fields.pack(fill=tk.X, pady=(0, 8))
        tk.Label(connection_fields, text="Port", bg=c["bg_secondary"], fg=c["text_secondary"]).pack(side=tk.LEFT)
        self.client_port = self._entry(connection_fields, "8080", 8)
        self.client_port.pack(side=tk.RIGHT)

        tk.Label(client_frame, text="Pairing key from the host", bg=c["bg_secondary"],
                 fg=c["text_secondary"], font=("Arial", 8)).pack(anchor=tk.W)
        self.client_key = self._entry(client_frame, "", 24)
        self.client_key.pack(fill=tk.X, pady=(3, 10))

        client_actions = tk.Frame(client_frame, bg=c["bg_secondary"])
        client_actions.pack(fill=tk.X)
        self.connect_button = self._button(client_actions, "Connect", self.connect_client)
        self.connect_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.disconnect_button = self._button(client_actions, "Disconnect", self.disconnect_client)
        self.disconnect_button.configure(state=tk.DISABLED)
        self.disconnect_button.pack(side=tk.LEFT)

        self.status_label = tk.Label(self, text="Sharing stopped  ·  Not connected",
                                     font=("Arial", 9, "bold"), anchor=tk.W,
                                     bg=c["bg_main"], fg=c["text_secondary"], padx=12, pady=9)
        self.status_label.pack(fill=tk.X, padx=12, pady=(0, 8))

        log_frame = tk.Frame(self, bg=c["bg_secondary"])
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        tk.Label(log_frame, text="ACTIVITY", font=("Arial", 8, "bold"),
                 bg=c["bg_secondary"], fg=c["text_secondary"]).pack(anchor=tk.W, padx=9, pady=(7, 3))
        self.log_box = tk.Text(log_frame, height=4, wrap=tk.WORD, state=tk.DISABLED,
                               bg=c["bg_main"], fg=c["text_secondary"],
                               insertbackground=c["text_primary"], relief=tk.FLAT,
                               font=("Consolas", 8), padx=8, pady=6)
        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scrollbar.set)
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=(0, 8))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=(0, 8))

    def _entry(self, parent, value, width):
        widget = tk.Entry(
            parent, width=width, relief=tk.FLAT,
            bg=self.colors["bg_main"], fg=self.colors["text_primary"],
            insertbackground=self.colors["text_primary"],
        )
        if value:
            widget.insert(0, value)
        return widget

    def _button(self, parent, text, command):
        return tk.Button(
            parent, text=text, command=command,
            bg=self.colors["bg_main"], fg=self.colors["text_primary"],
            activebackground=self.colors["border"],
            activeforeground=self.colors["text_primary"],
            relief=tk.FLAT, padx=7,
        )

    @staticmethod
    def _read_port(entry):
        try:
            port = int(entry.get().strip())
        except ValueError as error:
            raise ValueError("Port must be a number between 1 and 65535.") from error
        if not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535.")
        return port

    def _show_pairing_key(self, key):
        try:
            self.after(0, self._set_pairing_key, key)
        except tk.TclError:
            pass

    def _set_pairing_key(self, key):
        self.host_key.configure(state=tk.NORMAL)
        self.host_key.delete(0, tk.END)
        self.host_key.insert(0, key)
        self.host_key.configure(state=tk.READONLY)

    def copy_pairing_key(self):
        key = self.host_key.get().strip()
        if not key:
            messagebox.showinfo("Pairing key", "Start sharing first to create a pairing key.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(key)
        self._queue_log("[Mixput] Pairing key copied to clipboard.")

    def start_server(self):
        available, reason = InputBackend.availability()
        if not available:
            messagebox.showerror("Input support unavailable", reason, parent=self)
            return
        try:
            port = self._read_port(self.server_port)
        except ValueError as error:
            messagebox.showerror("Invalid port", str(error), parent=self)
            return
        interface, local_ip = get_active_network_info()
        self.local_ip = local_ip
        self.local_ip_label.configure(text=f"LAN address: {local_ip}   •   Interface: {interface}")
        if local_ip == "0.0.0.0":
            messagebox.showerror("Network unavailable", "Connect this laptop to a local network first.", parent=self)
            return
        if self.server.start("0.0.0.0", port):
            self.start_button.configure(state=tk.DISABLED)
            self.stop_button.configure(state=tk.NORMAL)
            self._queue_log(f"[Mixput] Other laptop should connect to {local_ip}:{port}.")

    def stop_server(self):
        self.server.stop()
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)

    def connect_client(self):
        available, reason = InputBackend.availability()
        if not available:
            messagebox.showerror("Input support unavailable", reason, parent=self)
            return
        host = self.client_host.get().strip()
        key = self.client_key.get().strip()
        try:
            port = self._read_port(self.client_port)
            if not host:
                raise ValueError("Enter the LAN IP shown on the host laptop.")
            try:
                parsed_host = ipaddress.ip_address(host)
            except ValueError as error:
                raise ValueError("Enter the host laptop IPv4 address.") from error
            if parsed_host.version != 4:
                raise ValueError("Only IPv4 LAN addresses are supported currently.")
            if not key:
                raise ValueError("Paste the pairing key from the host laptop.")
        except ValueError as error:
            messagebox.showerror("Connection settings", str(error), parent=self)
            return
        if self.client.connect(host, port, key):
            self.connect_button.configure(state=tk.DISABLED)

    def disconnect_client(self):
        self.client.disconnect()

    def _queue_log(self, message):
        try:
            self.after(0, self._append_log, message)
        except tk.TclError:
            pass

    def _append_log(self, message):
        try:
            self.log_box.configure(state=tk.NORMAL)
            self.log_box.insert(tk.END, message + "\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state=tk.DISABLED)
        except tk.TclError:
            pass

    def _queue_server_status(self, status):
        try:
            self.after(0, self._apply_server_status, status)
        except tk.TclError:
            pass

    def _apply_server_status(self, status):
        active = status in ("listening", "authenticating", "connected")
        self.start_button.configure(state=tk.DISABLED if active else tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL if active else tk.DISABLED)
        self._refresh_status(server=status)

    def _queue_client_status(self, status):
        try:
            self.after(0, self._apply_client_status, status)
        except tk.TclError:
            pass

    def _apply_client_status(self, status):
        connected = status == "connected"
        self.connect_button.configure(state=tk.DISABLED if connected else tk.NORMAL)
        self.disconnect_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
        self._refresh_status(client=status)

    def _refresh_status(self, server=None, client=None):
        parts = self.status_label.cget("text").split("  |  ")
        server_status = server or parts[0].replace("Sharing: ", "")
        client_status = client or parts[-1].replace("Remote laptop: ", "")
        self.status_label.configure(
            text=f"Sharing: {server_status}  |  Remote laptop: {client_status}"
        )

    def apply_theme(self, colors):
        self.colors = colors
        self.configure(bg=colors["bg_secondary"], highlightbackground=colors["border"])
        self._apply_tree_theme(self, colors)

    def _apply_tree_theme(self, parent, colors):
        for child in parent.winfo_children():
            try:
                if isinstance(child, tk.Text):
                    child.configure(bg=colors["bg_main"], fg=colors["text_secondary"],
                                    insertbackground=colors["text_primary"])
                elif isinstance(child, tk.Entry):
                    child.configure(bg=colors["bg_main"], fg=colors["text_primary"],
                                    insertbackground=colors["text_primary"])
                elif isinstance(child, tk.Button):
                    child.configure(bg=colors["bg_main"], fg=colors["text_primary"],
                                    activebackground=colors["border"],
                                    activeforeground=colors["text_primary"])
                elif isinstance(child, (tk.Frame, tk.LabelFrame, tk.Label)):
                    child.configure(bg=colors["bg_secondary"])
                    if isinstance(child, (tk.Label, tk.LabelFrame)):
                        child.configure(fg=colors["text_primary"])
                self._apply_tree_theme(child, colors)
            except tk.TclError:
                continue

    def destroy(self):
        self.client.disconnect()
        self.server.stop()
        self.host_input.close()
        self.remote_input.close()
        super().destroy()


def create_server_preferences(parent):
    panel = ServerPreferences(parent)
    panel.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    return panel
