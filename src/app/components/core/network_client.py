import socket
import threading


class NetworkClient:
    """TCP client with a background receive loop."""

    def __init__(self, on_message=None, on_status=None):
        self.on_message = on_message or (lambda message: None)
        self.on_status = on_status or (lambda status: None)
        self.running = False
        self.sock = None
        self._thread = None
        self._send_lock = threading.Lock()

    def connect(self, host="127.0.0.1", port=8080):
        if self.running:
            return False
        self.running = True
        self._thread = threading.Thread(
            target=self._run, args=(host, port), daemon=True
        )
        self._thread.start()
        return True

    def _run(self, host, port):
        connection = None
        try:
            self.on_message(f"[Client] Connecting to {host}:{port}...")
            connection = socket.create_connection((host, port), timeout=5)
            connection.settimeout(0.5)
            self.sock = connection
            self.on_status("connected")
            self.on_message(f"[Client] Connected to {host}:{port}")

            while self.running:
                try:
                    data = connection.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                message = data.decode("utf-8", errors="replace").strip()
                if message:
                    self.on_message(f"[Server] {message}")

        except OSError as error:
            if self.running:
                self.on_message(f"[Client] Connection error: {error}")
        finally:
            self.running = False
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            if self.sock is connection:
                self.sock = None
            self.on_status("disconnected")

    def send(self, message):
        connection = self.sock
        if not connection or not self.running:
            self.on_message("[Client] Not connected.")
            return False
        try:
            with self._send_lock:
                connection.sendall(message.encode("utf-8"))
            self.on_message(f"[You] {message}")
            return True
        except OSError as error:
            self.on_message(f"[Client] Send failed: {error}")
            self.disconnect()
            return False

    def disconnect(self):
        self.running = False
        connection = self.sock
        self.sock = None
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass
        self.on_status("disconnected")
