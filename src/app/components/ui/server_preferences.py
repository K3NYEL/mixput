import ipaddress
import tkinter as tk
from tkinter import messagebox

from app.components import theme
from app.components.core.input_backend import InputBackend
from app.components.core.network import get_network_details
from app.components.core.network_client import NetworkClient
from app.components.core.network_server import NetworkServer


class ServerPreferences(tk.Frame):
    """Dedicated Mixput host server controls and configuration."""

    def __init__(self, parent):
        self.colors = theme.CURRENT_THEME
        super().__init__(parent, bg=self.colors["bg_secondary"])
        self.host_input = InputBackend()
        self.remote_input = InputBackend()
        screen_size = (self.winfo_screenwidth(), self.winfo_screenheight())
        # The host is arranged to the left of the remote desktop:
        # right edge enters the remote machine; its left edge returns.
        self.host_input.configure_edge_switch("right", screen_size)
        self.remote_input.configure_edge_switch(("left", "right"), screen_size)
        self.server = NetworkServer(
            on_log=self._queue_log,
            on_status=self._queue_server_status,
            on_pairing_request=self._queue_pairing_request,
            on_chat=self._queue_chat,
            on_devices=self._queue_server_devices,
        )
        self.server.set_input_backend(self.host_input)
        self.client = NetworkClient(
            on_message=self._queue_log,
            on_status=self._queue_client_status,
            on_chat=self._queue_chat,
            on_session=self._queue_session,
            input_backend=self.remote_input,
        )
        self._server_status = "stopped"
        self._client_status = "disconnected"
        self._active_port = 8080
        self.chat_messages = []
        self.on_chat_message = lambda message: None
        self.on_state_changed = lambda state: None
        self.on_activity = lambda message: None
        self.on_sharing_changed = lambda sharing, port: None
        self._build()

    def _build(self):
        c = self.colors
        self.configure(bg=c["bg_secondary"], highlightbackground=c["border"], highlightthickness=1)
        available, reason = InputBackend.availability()
        self.backend_status = tk.Label(
            self, text=("Input control ready" if available else f"Input control unavailable: {reason}"),
            font=("Arial", 9), bg=c["bg_secondary"],
            fg=c["text_secondary"] if available else "#D65A65")
        self.backend_status.pack(anchor=tk.W, padx=16, pady=(0, 8))

        cards = tk.Frame(self, bg=c["bg_secondary"])
        cards.pack(fill=tk.X, padx=12, pady=(0, 8))
        cards.columnconfigure(0, weight=1)

        host_frame = tk.LabelFrame(
            cards, text=" SHARE THIS COMPUTER ", bg=c["bg_secondary"],
            fg=c["text_primary"], padx=12, pady=10, font=("Arial", 9, "bold")
        )
        host_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0)
        network_frame = tk.Frame(host_frame, bg=c["bg_secondary"])
        network_frame.pack(fill=tk.X, pady=(2, 10))
        self.network_value_labels = {}
        for label in ("Mixput virtual IP", "Transport IP address", "Subnet mask", "DNS servers", "Network interface"):
            row = tk.Frame(network_frame, bg=c["bg_secondary"])
            row.pack(fill=tk.X, pady=2)
            tk.Label(
                row, text=label, width=18, anchor=tk.W,
                bg=c["bg_secondary"], fg=c["text_secondary"],
                font=("Arial", 9),
            ).pack(side=tk.LEFT)
            value = tk.Label(
                row, text="Loading…", anchor=tk.W,
                bg=c["bg_secondary"], fg=c["text_primary"],
                font=("Arial", 9, "bold"),
            )
            value.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.network_value_labels[label] = value
        self.local_ip = "0.0.0.0"
        self.virtual_ip = self.server.virtual_network.host_ip
        self.local_ip_label = self.network_value_labels["Transport IP address"]
        self.refresh_network_button = self._button(
            host_frame, "Refresh network information", self.refresh_network_info
        )
        self.refresh_network_button.pack(anchor=tk.W, pady=(4, 8))
        self.refresh_network_info()

        port_row = tk.Frame(host_frame, bg=c["bg_secondary"])
        port_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(port_row, text="Port", bg=c["bg_secondary"], fg=c["text_secondary"]).pack(side=tk.LEFT)
        self.server_port = self._entry(port_row, "8080", 8)
        self.server_port.pack(side=tk.RIGHT)

        host_actions = tk.Frame(host_frame, bg=c["bg_secondary"])
        host_actions.pack(fill=tk.X, pady=(0, 10))
        self.start_button = self._button(host_actions, "Start server", self.start_server)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.stop_button = self._button(host_actions, "Stop server", self.stop_server)
        self.stop_button.configure(state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT)

        tk.Label(
            host_frame, text="Authorized devices (up to 3 connected)", bg=c["bg_secondary"],
            fg=c["text_secondary"], font=("Arial", 8, "bold")
        ).pack(anchor=tk.W)
        self.authorized_list = tk.Listbox(
            host_frame, height=4, relief=tk.FLAT, borderwidth=0,
            bg=c["bg_main"], fg=c["text_primary"],
            selectbackground=c["border"], activestyle="none",
        )
        self.authorized_list.pack(fill=tk.X, pady=(4, 5))
        self.revoke_button = self._button(host_frame, "Revoke selected device", self.revoke_selected_device)
        self.revoke_button.pack(anchor=tk.W)
        self._refresh_authorized_devices()

        tk.Label(
            self, text="This laptop will act as the Mixput host. Other laptops can discover this server on the same local network and request access.",
            bg=c["bg_secondary"], fg=c["text_secondary"], font=("Arial", 9),
            justify=tk.LEFT, wraplength=720,
        ).pack(fill=tk.X, padx=16, pady=(0, 10))

        self.status_label = tk.Label(
            self, text="Server stopped", font=("Arial", 9, "bold"),
            anchor=tk.W, bg=c["bg_main"], fg=c["text_secondary"], padx=12, pady=9
        )
        self.status_label.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.devices_label = tk.Label(
            self, text="Connected desktops: this computer · waiting for devices",
            bg=c["bg_secondary"], fg=c["text_secondary"], font=("Arial", 8),
            anchor=tk.W,
        )
        self.devices_label.pack(fill=tk.X, padx=14, pady=(0, 6))

        log_frame = tk.Frame(self, bg=c["bg_secondary"])
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.log_box = tk.Text(
            log_frame, height=4, wrap=tk.WORD, state=tk.DISABLED,
            bg=c["bg_main"], fg=c["text_secondary"],
            insertbackground=c["text_primary"], relief=tk.FLAT,
            font=("Consolas", 8), padx=8, pady=6
        )
        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scrollbar.set)
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=(0, 8))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=(0, 8))


    def _queue_chat(self, message):
        try:
            self.after(0, self._dispatch_chat, message)
        except tk.TclError:
            pass

    def _dispatch_chat(self, message):
        self.chat_messages.append(message)
        self.on_chat_message(message)

    def _queue_server_devices(self, devices):
        self._queue_session({"devices": devices, "owner": self.server._control_owner})

    def _queue_session(self, state):
        try:
            self.after(0, self._apply_session, state)
        except tk.TclError:
            pass

    def _apply_session(self, state):
        devices = state.get("devices", [])
        if not devices:
            self.devices_label.configure(text="Connected desktops: this computer · waiting for devices")
            return
        names = [str(item.get("name", "Device")) for item in sorted(devices, key=lambda d: d.get("index", 0))]
        self.devices_label.configure(text="Connected desktops: " + "  →  ".join(names))
        assigned_ip = state.get("virtual_ip")
        if assigned_ip:
            self.virtual_ip = str(assigned_ip)
            virtual_label = self.network_value_labels.get("Mixput virtual IP")
            if virtual_label is not None:
                virtual_label.configure(text=self.virtual_ip)
        self.on_state_changed({
            "devices": devices, "owner": state.get("owner", "host"),
            "server_status": self._server_status, "client_status": self._client_status,
            "port": self._active_port, "local_ip": self.local_ip,
            "virtual_ip": state.get("virtual_ip", self.virtual_ip),
        })

    def send_chat_message(self, text):
        if self._server_status in ("listening", "connected", "pairing", "authenticating"):
            return self.server.send_chat(text)
        if self._client_status == "connected":
            return self.client.send_chat(text)
        return False

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

    def _queue_pairing_request(self, request):
        try:
            self.after(0, self._ask_pairing_request, request)
        except tk.TclError:
            pass

    def _ask_pairing_request(self, request):
        approved = messagebox.askyesno(
            "Mixput device pairing",
            f'{request["name"]} ({request["ip"]}) wants to join this Mixput session and receive shared keyboard and mouse input.\\n\\nAllow this device?',
            parent=self.winfo_toplevel(),
        )
        self.server.approve_pairing(request["request_id"], approved)
        if approved:
            self._queue_log(f'[Mixput] Authorized {request["name"]} ({request["ip"]}).')
            self.after(500, self._refresh_authorized_devices)
        else:
            self._queue_log(f'[Mixput] Rejected pairing request from {request["name"]}.')

    def _refresh_authorized_devices(self):
        if not hasattr(self, "authorized_list"):
            return
        self.authorized_list.delete(0, tk.END)
        self._authorized_devices = self.server.pairings.list_authorized_clients()
        for device in self._authorized_devices:
            virtual_ip = device.get("virtual_ip", "Not assigned")
            self.authorized_list.insert(
                tk.END,
                f'{device.get("name", "Device")}  ·  Mixput {virtual_ip}  ·  {device.get("address", "")}'
            )

    def revoke_selected_device(self):
        selected = self.authorized_list.curselection()
        if not selected or selected[0] >= len(self._authorized_devices):
            messagebox.showinfo("Authorized devices", "Select a device to revoke.", parent=self)
            return
        device = self._authorized_devices[selected[0]]
        if messagebox.askyesno(
            "Revoke device",
            f'Revoke access for {device.get("name", "this device")}? It will need approval again.',
            parent=self,
        ):
            self.server.revoke_device(device["id"])
            self._refresh_authorized_devices()

    def _current_virtual_ip(self):
        if self._server_status in ("listening", "connected", "pairing", "authenticating"):
            return self.server.virtual_network.host_ip
        return self.client.virtual_ip or self.server.virtual_network.host_ip

    def refresh_network_info(self):
        interface, local_ip, subnet_mask, dns_servers = get_network_details()
        self.local_ip = local_ip
        self.virtual_ip = self._current_virtual_ip()
        values = {
            "Mixput virtual IP": self.virtual_ip,
            "Transport IP address": local_ip,
            "Subnet mask": subnet_mask,
            "DNS servers": dns_servers,
            "Network interface": interface,
        }
        for label, value in values.items():
            widget = self.network_value_labels.get(label)
            if widget is not None:
                widget.configure(text=value)
        return values

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
        self.refresh_network_info()
        local_ip = self.local_ip
        if local_ip == "0.0.0.0":
            messagebox.showerror("Network unavailable", "Connect this laptop to a local network first.", parent=self)
            return
        if self.server.start("0.0.0.0", port):
            self._active_port = port
            self.on_sharing_changed(True, port)
            self.start_button.configure(state=tk.DISABLED)
            self.stop_button.configure(state=tk.NORMAL)
            self._queue_log(f"[Mixput] Sharing is available at {local_ip}:{port}.")

    def stop_server(self):
        self.server.stop()
        self.on_sharing_changed(False, self._active_port)
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)

    def connect_discovered_device(self, address, port):
        """Connect to a discovered host without adding client controls to Connection."""
        available, reason = InputBackend.availability()
        if not available:
            messagebox.showerror("Input support unavailable", reason, parent=self)
            return False
        try:
            host = str(address).strip()
            parsed_host = ipaddress.ip_address(host)
            if parsed_host.version != 4:
                raise ValueError("Only IPv4 LAN addresses are supported currently.")
            port = int(port)
            if not 1 <= port <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
        except (TypeError, ValueError) as error:
            messagebox.showerror("Connection settings", str(error), parent=self)
            return False
        return self.client.connect(host, port)

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
            self.on_activity(str(message))
        except tk.TclError:
            pass

    def _queue_server_status(self, status):
        try:
            self.after(0, self._apply_server_status, status)
        except tk.TclError:
            pass

    def _apply_server_status(self, status):
        self._server_status = status
        active = status in ("listening", "authenticating", "connected")
        self.on_sharing_changed(active, self._active_port)
        self.start_button.configure(state=tk.DISABLED if active else tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL if active else tk.DISABLED)
        self._refresh_status()

    def _queue_client_status(self, status):
        try:
            self.after(0, self._apply_client_status, status)
        except tk.TclError:
            pass

    def _apply_client_status(self, status):
        self._client_status = status
        connected = status in ("connecting", "connected")
        # Connection is server-only; client sessions are initiated from Devices.
        if hasattr(self, "connect_button"):
            self.connect_button.configure(state=tk.DISABLED if connected else tk.NORMAL)
        if hasattr(self, "disconnect_button"):
            self.disconnect_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
        self._refresh_status()

    def _refresh_status(self):
        server_labels = {
            "stopped": "Stopped",
            "listening": "Sharing",
            "authenticating": "Approving device",
            "connected": "Sharing active",
            "error": "Sharing error",
        }
        client_labels = {
            "disconnected": "Disconnected",
            "connecting": "Requesting access",
            "connected": "Connected",
        }
        server = server_labels.get(self._server_status, self._server_status.title())
        self.status_label.configure(text=f"Mixput server: {server}")
        self.virtual_ip = self._current_virtual_ip()
        virtual_label = self.network_value_labels.get("Mixput virtual IP")
        if virtual_label is not None:
            virtual_label.configure(text=self.virtual_ip)
        devices = self.server.connected_devices if self.server.running else (
            self.client._devices if self._client_status == "connected" else [])
        owner = self.server._control_owner if self.server.running else self.client._control_owner
        self.on_state_changed({
            "devices": devices, "owner": owner,
            "server_status": self._server_status, "client_status": self._client_status,
            "port": self._active_port, "local_ip": self.local_ip,
            "virtual_ip": self.client.virtual_ip if self._client_status == "connected" else self.virtual_ip,
        })

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
                elif isinstance(child, (tk.Entry, tk.Listbox)):
                    child.configure(bg=colors["bg_main"], fg=colors["text_primary"],
                                    insertbackground=colors["text_primary"],
                                    selectbackground=colors["border"])
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
        self.on_sharing_changed(False, self._active_port)
        self.host_input.close()
        self.remote_input.close()
        super().destroy()


def create_server_preferences(parent):
    panel = ServerPreferences(parent)
    panel.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    return panel
