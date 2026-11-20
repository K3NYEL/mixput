import socket
import threading


class NetworkServer:
    """Small TCP server used by Mixput Preferences."""

    def __init__(self, on_log=None, on_status=None):
        self.on_log = on_log or (lambda message: None)
        self.on_status = on_status or (lambda status: None)
        self.running = False
        self._server_socket = None
        self._client_socket = None
        self._thread = None
        self._lock = threading.RLock()

    def start(self, host="127.0.0.1", port=8080):
        with self._lock:
            if self.running:
                return False
            self.running = True
            self._thread = threading.Thread(
                target=self._run, args=(host, port), daemon=True
            )
            self._thread.start()
        return True

    def _run(self, host, port):
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(5)
            server.settimeout(0.5)
            with self._lock:
                self._server_socket = server

            self.on_status("listening")
            self.on_log(f"[Server] Listening on {host}:{port}")

            while self.running:
                try:
                    client, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.running:
                        raise
                    break

                with self._lock:
                    self._client_socket = client
                client.settimeout(0.5)
                self.on_status("connected")
                self.on_log(f"[Server] Client connected: {address[0]}:{address[1]}")

                try:
                    while self.running:
                        try:
                            data = client.recv(4096)
                        except socket.timeout:
                            continue
                        if not data:
                            break
                        message = data.decode("utf-8", errors="replace").strip()
                        if message:
                            self.on_log(f"[Client] {message}")
                            client.sendall(f"Server received: {message}".encode("utf-8"))
                except OSError as error:
                    if self.running:
                        self.on_log(f"[Server] Client connection error: {error}")
                finally:
                    try:
                        client.close()
                    except OSError:
                        pass
                    with self._lock:
                        if self._client_socket is client:
                            self._client_socket = None
                    if self.running:
                        self.on_status("listening")
                        self.on_log("[Server] Waiting for a client")

        except OSError as error:
            self.on_log(f"[Server] Could not start: {error}")
            self.on_status("error")
        finally:
            self._close_sockets()
            with self._lock:
                self.running = False
            self.on_status("stopped")

    def stop(self):
        with self._lock:
            self.running = False
        self._close_sockets()
        self.on_log("[Server] Stop requested")

    def _close_sockets(self):
        with self._lock:
            sockets = (self._client_socket, self._server_socket)
            self._client_socket = None
            self._server_socket = None

        for sock in sockets:
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass
