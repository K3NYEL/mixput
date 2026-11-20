import tkinter as tk
from tkinter import messagebox

from app.components import theme
from app.components.core.network_client import NetworkClient
from app.components.core.network_server import NetworkServer


class ServerPreferences(tk.Frame):
    """Embedded Server/Client controls for Mixput Preferences."""

    def __init__(self, parent):
        self.colors = theme.CURRENT_THEME
        super().__init__(parent, bg=self.colors["bg_secondary"])
        self.server = NetworkServer(
            on_log=self._queue_log,
            on_status=self._queue_server_status,
        )
        self.client = NetworkClient(
            on_message=self._queue_log,
            on_status=self._queue_client_status,
        )
        self._build()

    def _build(self):
        c = self.colors
        self.configure(
            bg=c["bg_secondary"],
            highlightbackground=c["border"],
            highlightthickness=1,
        )

        heading = tk.Label(
            self, text="Network Server", font=("Arial", 12, "bold"),
            bg=c["bg_secondary"], fg=c["text_primary"],
        )
        heading.pack(anchor=tk.W, padx=8, pady=(6, 2))

        description = tk.Label(
            self,
            text="Host a local TCP server or connect to another Mixput server.",
            font=("Arial", 9),
            bg=c["bg_secondary"], fg=c["text_secondary"],
        )
        description.pack(anchor=tk.W, padx=8, pady=(0, 5))

        self.server_row = tk.Frame(self, bg=c["bg_secondary"])
        self.server_row.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(
            self.server_row, text="Server", width=8, anchor=tk.W,
            bg=c["bg_secondary"], fg=c["text_primary"],
        ).pack(side=tk.LEFT)
        self.server_host = self._entry(self.server_row, "127.0.0.1", width=16)
        self.server_host.pack(side=tk.LEFT, padx=(0, 5))
        self.server_port = self._entry(self.server_row, "8080", width=6)
        self.server_port.pack(side=tk.LEFT, padx=(0, 5))
        self.start_button = self._button(self.server_row, "Start", self.start_server)
        self.start_button.pack(side=tk.LEFT, padx=2)
        self.stop_button = self._button(self.server_row, "Stop", self.stop_server)
        self.stop_button.configure(state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=2)

        self.client_row = tk.Frame(self, bg=c["bg_secondary"])
        self.client_row.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(
            self.client_row, text="Client", width=8, anchor=tk.W,
            bg=c["bg_secondary"], fg=c["text_primary"],
        ).pack(side=tk.LEFT)
        self.client_host = self._entry(self.client_row, "127.0.0.1", width=16)
        self.client_host.pack(side=tk.LEFT, padx=(0, 5))
        self.client_port = self._entry(self.client_row, "8080", width=6)
        self.client_port.pack(side=tk.LEFT, padx=(0, 5))
        self.connect_button = self._button(self.client_row, "Connect", self.connect_client)
        self.connect_button.pack(side=tk.LEFT, padx=2)
        self.disconnect_button = self._button(
            self.client_row, "Disconnect", self.disconnect_client
        )
        self.disconnect_button.configure(state=tk.DISABLED)
        self.disconnect_button.pack(side=tk.LEFT, padx=2)

        self.status_label = tk.Label(
            self, text="Server: stopped  |  Client: disconnected",
            font=("Arial", 9), anchor=tk.W,
            bg=c["bg_secondary"], fg=c["text_secondary"],
        )
        self.status_label.pack(fill=tk.X, padx=8, pady=(3, 2))

        message_row = tk.Frame(self, bg=c["bg_secondary"])
        message_row.pack(fill=tk.X, padx=8, pady=2)
        self.message_entry = self._entry(message_row, "", width=40)
        self.message_entry.configure(state=tk.DISABLED)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.message_entry.bind("<Return>", lambda _event: self.send_message())
        self.send_button = self._button(message_row, "Send", self.send_message)
        self.send_button.configure(state=tk.DISABLED)
        self.send_button.pack(side=tk.RIGHT)

        log_frame = tk.Frame(self, bg=c["bg_main"])
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        self.log_box = tk.Text(
            log_frame, height=5, wrap=tk.WORD, state=tk.DISABLED,
            bg=c["bg_main"], fg=c["text_secondary"],
            insertbackground=c["text_primary"], relief=tk.FLAT,
            font=("Consolas", 9),
        )
        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scrollbar.set)
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

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

    def start_server(self):
        host = self.server_host.get().strip()
        try:
            port = self._read_port(self.server_port)
            if not host:
                raise ValueError("Enter a server host address.")
        except ValueError as error:
            messagebox.showerror("Invalid server settings", str(error), parent=self)
            return

        if self.server.start(host, port):
            self.start_button.configure(state=tk.DISABLED)
            self.stop_button.configure(state=tk.NORMAL)

    def stop_server(self):
        self.server.stop()
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)

    def connect_client(self):
        host = self.client_host.get().strip()
        try:
            port = self._read_port(self.client_port)
            if not host:
                raise ValueError("Enter the server address to connect to.")
        except ValueError as error:
            messagebox.showerror("Invalid connection settings", str(error), parent=self)
            return

        if self.client.connect(host, port):
            self.connect_button.configure(state=tk.DISABLED)

    def disconnect_client(self):
        self.client.disconnect()

    def send_message(self):
        message = self.message_entry.get().strip()
        if not message:
            return
        self.message_entry.delete(0, tk.END)
        self.client.send(message)

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
        active = status in ("listening", "connected")
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
        self.message_entry.configure(state=tk.NORMAL if connected else tk.DISABLED)
        self.send_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
        self._refresh_status(client=status)

    def _refresh_status(self, server=None, client=None):
        current = self.status_label.cget("text")
        parts = current.split("  |  ")
        server_status = server or parts[0].replace("Server: ", "")
        client_status = client or parts[-1].replace("Client: ", "")
        self.status_label.configure(
            text=f"Server: {server_status}  |  Client: {client_status}"
        )

    def apply_theme(self, colors):
        self.colors = colors
        self.configure(bg=colors["bg_secondary"], highlightbackground=colors["border"])
        for widget in (self.server_row, self.client_row):
            widget.configure(bg=colors["bg_secondary"])
        self._apply_tree_theme(self, colors)

    def _apply_tree_theme(self, parent, colors):
        for child in parent.winfo_children():
            try:
                if isinstance(child, tk.Text):
                    child.configure(
                        bg=colors["bg_main"], fg=colors["text_secondary"],
                        insertbackground=colors["text_primary"],
                    )
                elif isinstance(child, tk.Entry):
                    child.configure(
                        bg=colors["bg_main"], fg=colors["text_primary"],
                        insertbackground=colors["text_primary"],
                    )
                elif isinstance(child, tk.Button):
                    child.configure(
                        bg=colors["bg_main"], fg=colors["text_primary"],
                        activebackground=colors["border"],
                        activeforeground=colors["text_primary"],
                    )
                elif isinstance(child, (tk.Frame, tk.Label)):
                    child.configure(bg=colors["bg_secondary"])
                    if isinstance(child, tk.Label):
                        child.configure(fg=colors["text_primary"])
                self._apply_tree_theme(child, colors)
            except tk.TclError:
                continue

    def destroy(self):
        self.client.disconnect()
        self.server.stop()
        super().destroy()


def create_server_preferences(parent):
    panel = ServerPreferences(parent)
    panel.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    return panel
