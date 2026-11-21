"""Authenticated multi-device Mixput hub (maximum four devices including host)."""
import base64
import socket
import threading
import uuid
from cryptography.fernet import Fernet
from app.components.core.input_protocol import PROTOCOL_VERSION, EVENT_TYPES, ProtocolError
from app.components.core.pairing_handshake import (
    PAIRING_VERSION, send_control, receive_control, new_ephemeral_key,
    derive_pairing_key, encrypt_session_token,
)
from app.components.core.pairing_store import PairingStore
from app.components.core.secure_transport import SecureChannel
from app.components.core.input_ownership import InputOwnership

MAX_DEVICES = 4
MAX_CHAT_LENGTH = 1000


class NetworkServer:
    def __init__(self, on_log=None, on_status=None, on_pairing_request=None,
                 on_chat=None, on_devices=None, pairing_store=None):
        self.on_log = on_log or (lambda message: None)
        self.on_status = on_status or (lambda status: None)
        self.on_pairing_request = on_pairing_request or (lambda request: None)
        self.on_chat = on_chat or (lambda message: None)
        self.on_devices = on_devices or (lambda devices: None)
        self.pairings = pairing_store or PairingStore()
        self.running = False
        self._server_socket = None
        self._thread = None
        self._lock = threading.RLock()
        # Bound unauthenticated handshakes so LAN scans cannot spawn unbounded threads.
        self._handshake_slots = threading.BoundedSemaphore(8)
        self._capture = None
        self._pending = {}
        self._peers = {}
        self._ownership = InputOwnership("host")
        self._local_mode = False
        self._host_name = socket.gethostname()[:64]

    @property
    def _control_owner(self):
        return self._ownership.owner

    @_control_owner.setter
    def _control_owner(self, device_id):
        self._ownership.force(device_id)

    @property
    def _ownership_epoch(self):
        return self._ownership.epoch

    @property
    def connected_devices(self):
        with self._lock:
            return self._device_snapshot_locked()

    def _device_snapshot_locked(self):
        return [{"id": "host", "device_id": self.pairings.device_id,
                 "name": self._host_name, "index": 0, "host": True}] + [
            {"id": p["id"], "device_id": p["id"], "name": p["name"],
             "index": p["index"], "host": False}
            for p in sorted(self._peers.values(), key=lambda item: item["index"])
        ]

    def start(self, host="0.0.0.0", port=8080):
        with self._lock:
            if self.running or (self._thread and self._thread.is_alive()):
                return False
            self.running = True
            self._thread = threading.Thread(target=self._run, args=(host, port),
                                            daemon=True, name="MixputServer")
            self._thread.start()
        return True

    def set_input_backend(self, backend):
        self._capture = backend
        backend.on_event = self._send_input
        backend.on_edge = self._on_local_edge
        backend.on_toggle_local = self.toggle_local_mode

    @property
    def local_mode(self):
        with self._lock:
            return self._local_mode

    def toggle_local_mode(self):
        return self.set_local_mode(not self.local_mode)

    def set_local_mode(self, enabled):
        enabled = bool(enabled)
        with self._lock:
            if self._local_mode == enabled:
                return False
            self._local_mode = enabled
        with self._lock:
            active_peer = self._peers.get(self._control_owner)
        if enabled and active_peer:
            try:
                active_peer["channel"].send({
                    "version": PROTOCOL_VERSION,
                    "kind": "release_inputs",
                })
            except (OSError, ProtocolError, ValueError):
                pass
        if self._capture:
            self._capture.release_all()
            self._capture.set_exclusive_capture(not enabled and self._control_owner != "host")
            if not enabled and self._control_owner != "host":
                self._capture.park_cursor()
        self.on_log(f"[Mixput] Local mode {'enabled' if enabled else 'disabled'}.")
        return True

    def _notify_devices(self):
        with self._lock:
            devices = self._device_snapshot_locked()
            owner = self._control_owner
            epoch = self._ownership_epoch
            peers = list(self._peers.values())
        self.on_devices(devices)
        for peer in peers:
            self._send_state(peer, devices, owner, ownership_epoch=epoch)

    def _send_state(self, peer, devices=None, owner=None, enter_edge=None, ownership_epoch=None):
        if devices is None:
            with self._lock:
                devices = self._device_snapshot_locked()
                owner = self._control_owner
                ownership_epoch = self._ownership_epoch
        elif ownership_epoch is None:
            ownership_epoch = self._ownership_epoch
        try:
            peer["channel"].send({"version": PROTOCOL_VERSION, "kind": "session_state",
                                  "devices": devices, "owner": owner, "enter_edge": enter_edge,
                                  "ownership_epoch": ownership_epoch})
        except (OSError, ProtocolError, ValueError):
            pass

    def _broadcast_state(self):
        self._notify_devices()

    def _send_to_owner(self, message):
        with self._lock:
            owner = self._control_owner
            peer = self._peers.get(owner)
        if owner == "host":
            return False
        if peer is None:
            return False
        try:
            peer["channel"].send(message)
            return True
        except (OSError, ProtocolError, ValueError):
            return False

    def _set_owner(self, device_id, enter_edge=None):
        with self._lock:
            if device_id != "host" and (
                device_id not in self._peers
                or self._peers[device_id].get("local_mode", False)
            ):
                return False
            allowed = {"host", *self._peers.keys()}
            transfer = self._ownership.transfer(device_id, allowed)
            if transfer is None:
                return False
            old, epoch = transfer
            peers = list(self._peers.values())
            devices = self._device_snapshot_locked()
        if self._capture:
            self._capture.release_all()
            exclusive_ok = self._capture.set_exclusive_capture(
                device_id != "host" and not self.local_mode
            )
            if device_id != "host" and not self.local_mode and not exclusive_ok:
                with self._lock:
                    self._ownership.force(old)
                    rollback_epoch = self._ownership_epoch
                    rollback_devices = self._device_snapshot_locked()
                    rollback_peers = list(self._peers.values())
                self._capture.set_relative_mode(old != "host")
                self._capture.set_exclusive_capture(old != "host" and not self.local_mode)
                for rollback_peer in rollback_peers:
                    self._send_state(rollback_peer, rollback_devices, old, ownership_epoch=rollback_epoch)
                self.on_log("[Mixput] Could not obtain exclusive input capture; control transfer was cancelled.")
                return False
            self._capture.set_relative_mode(device_id != "host")
            if device_id == "host" and enter_edge:
                self._capture.warp_to_edge(enter_edge)
            elif device_id != "host":
                self._capture.park_cursor()
        self.on_devices(devices)
        for peer in peers:
            self._send_state(peer, devices, device_id, enter_edge, epoch)
        self.on_log(f"[Mixput] Control: {self._device_name(old)} → {self._device_name(device_id)}.")
        return True

    def _device_name(self, device_id):
        if device_id == "host":
            return self._host_name
        with self._lock:
            peer = self._peers.get(device_id)
            return peer["name"] if peer else "Disconnected device"

    def _on_local_edge(self, side):
        if side != "right":
            return
        with self._lock:
            if self._local_mode or self._control_owner != "host":
                return
            next_peer = next((p for p in sorted(self._peers.values(), key=lambda x: x["index"])
                              if p["index"] == 1), None)
        if next_peer:
            self._set_owner(next_peer["id"], "left")

    def _send_input(self, event):
        if not isinstance(event, dict) or event.get("type") not in EVENT_TYPES:
            return
        with self._lock:
            if self._local_mode:
                return
            target_id = self._control_owner
            epoch = self._ownership_epoch
            peer = self._peers.get(target_id)
        if target_id == "host" or peer is None or peer.get("local_mode", False):
            return False
        try:
            with self._lock:
                if self._control_owner != target_id or self._ownership_epoch != epoch:
                    return False
                self._input_sequence = getattr(self, "_input_sequence", 0) + 1
                sequence = self._input_sequence
            return bool(peer["channel"].send({
                "version": PROTOCOL_VERSION, "kind": "input",
                "source_id": "host", "target_id": target_id,
                "ownership_epoch": epoch, "sequence": sequence, "event": event,
            }))
        except (OSError, ProtocolError, ValueError) as error:
            self.on_log(f"[Mixput] Could not transmit input: {error}")
            return False

    def _route_peer_input(self, source_peer, message):
        """Validate a peer's input and route it to the active screen."""
        event = message.get("event")
        epoch = message.get("ownership_epoch")
        sequence = message.get("sequence")
        if not isinstance(event, dict) or event.get("type") not in EVENT_TYPES:
            return False
        if not isinstance(epoch, int) or isinstance(epoch, bool):
            return False
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            return False
        with self._lock:
            source_id = source_peer["id"]
            current = self._peers.get(source_id)
            target_id = self._control_owner
            if (
                current is not source_peer
                or source_peer.get("local_mode", False)
                or source_id == target_id
                or epoch != self._ownership_epoch
                or message.get("target_id") != target_id
                or sequence <= source_peer.get("input_sequence", 0)
            ):
                return False
            source_peer["input_sequence"] = sequence
            target_peer = self._peers.get(target_id)
            if target_id != "host" and (target_peer is None or target_peer.get("local_mode", False)):
                return False
        routed = {
            "version": PROTOCOL_VERSION,
            "kind": "input",
            "source_id": source_id,
            "target_id": target_id,
            "ownership_epoch": epoch,
            "sequence": sequence,
            "event": event,
        }
        if target_id == "host":
            backend = self._capture
            return bool(backend and backend.apply_event(event))
        try:
            return bool(target_peer["channel"].send(routed))
        except (OSError, ProtocolError, ValueError):
            return False

    def send_chat(self, text):
        if not isinstance(text, str):
            return False
        text = text.strip()
        if not text or len(text) > MAX_CHAT_LENGTH:
            return False
        message = {"version": PROTOCOL_VERSION, "kind": "chat",
                   "sender_id": "host", "sender": self._host_name, "text": text}
        with self._lock:
            peers = list(self._peers.values())
        if not peers:
            return False
        delivered = False
        for peer in peers:
            try:
                delivered = bool(peer["channel"].send(message)) or delivered
            except (OSError, ProtocolError, ValueError):
                continue
        if delivered:
            self.on_chat(message)
        return delivered

    def approve_pairing(self, request_id, approved):
        with self._lock:
            pending = self._pending.get(request_id)
            if pending is None:
                return False
            pending["approved"] = bool(approved)
            pending["event"].set()
            return True

    def revoke_device(self, device_id):
        revoked = self.pairings.revoke_client(device_id)
        if revoked:
            with self._lock:
                peer = self._peers.get(device_id)
            if peer:
                peer["channel"].close()
            self.on_log("[Mixput] Device authorization revoked.")
        return revoked

    def _run(self, host, port):
        server = None
        final_status = "stopped"
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(8)
            server.settimeout(0.5)
            with self._lock:
                self._server_socket = server
            self.on_status("listening")
            self.on_log(f"[Mixput] Multi-device server ready on port {port} (maximum {MAX_DEVICES} devices).")
            while self.running:
                try:
                    connection, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.running:
                        raise
                    break
                if not self._handshake_slots.acquire(blocking=False):
                    try:
                        connection.close()
                    except OSError:
                        pass
                    continue
                try:
                    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except OSError:
                    pass
                threading.Thread(
                    target=self._handle_peer_guarded,
                    args=(connection, address),
                    daemon=True,
                    name="MixputPeer",
                ).start()
        except OSError as error:
            if self.running:
                self.on_log(f"[Mixput] Server error: {error}")
                final_status = "error"
        finally:
            self._close_all_peers()
            if server:
                try:
                    server.close()
                except OSError:
                    pass
            with self._lock:
                self._server_socket = None
                self.running = False
            self.on_status(final_status)

    def _request_approval(self, request):
        request_id = uuid.uuid4().hex
        pending = {"event": threading.Event(), "approved": False}
        with self._lock:
            self._pending[request_id] = pending
        self.on_pairing_request({**request, "request_id": request_id})
        try:
            return pending["event"].wait(60) and pending["approved"]
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def _handle_peer_guarded(self, connection, address):
        try:
            self._handle_peer(connection, address)
        finally:
            self._handshake_slots.release()

    def _handle_peer(self, connection, address):
        channel = None
        client_id = None
        try:
            connection.settimeout(8.0)
            control = receive_control(connection)
            client_id = control.get("device_id")
            if control.get("version") != PAIRING_VERSION or not isinstance(client_id, str) or len(client_id) != 32:
                raise ProtocolError("Invalid device identity or pairing protocol.")
            if client_id == self.pairings.device_id:
                raise ProtocolError("This device is already the Mixput server identity.")
            if control.get("type") == "resume":
                record = self.pairings.get_authorized_client(client_id) if control.get("host_id") == self.pairings.device_id else None
                if record:
                    send_control(connection, {"type": "resume_ok", "version": PAIRING_VERSION})
                    channel = SecureChannel(connection, record["token"])
                else:
                    send_control(connection, {"type": "pair_required", "version": PAIRING_VERSION})
                    control = receive_control(connection)
            if channel is None:
                if control.get("type") != "pair_request":
                    raise ProtocolError("A pairing request is required.")
                name, ephemeral, salt_text = control.get("name"), control.get("public_key"), control.get("nonce")
                if not isinstance(name, str) or not name.strip() or len(name) > 64 or not isinstance(ephemeral, str) or not isinstance(salt_text, str):
                    raise ProtocolError("Invalid pairing request.")
                try:
                    salt = base64.b64decode(salt_text, validate=True)
                except ValueError as error:
                    raise ProtocolError("Invalid pairing nonce.") from error
                if len(salt) != 32:
                    raise ProtocolError("Invalid pairing nonce.")
                with self._lock:
                    full = len(self._peers) >= MAX_DEVICES - 1
                if full:
                    send_control(connection, {"type": "pair_denied", "version": PAIRING_VERSION, "reason": "server_full"})
                    return
                self.on_status("pairing")
                approved = self._request_approval({"device_id": client_id, "name": name.strip(), "ip": address[0]})
                if not approved or not self.running:
                    send_control(connection, {"type": "pair_denied", "version": PAIRING_VERSION})
                    return
                private, public_text = new_ephemeral_key()
                key = derive_pairing_key(private, ephemeral, salt)
                token = Fernet.generate_key().decode("ascii")
                nonce, ciphertext = encrypt_session_token(key, token)
                self.pairings.authorize_client(client_id, name.strip(), address[0], token)
                send_control(connection, {"type": "pair_accept", "version": PAIRING_VERSION,
                    "host_id": self.pairings.device_id, "host_name": self._host_name,
                    "public_key": public_text, "nonce": nonce, "ciphertext": ciphertext})
                channel = SecureChannel(connection, token)
            with self._lock:
                if not self.running or len(self._peers) >= MAX_DEVICES - 1 or client_id in self._peers:
                    raise ProtocolError("The Mixput server is full or this device is already connected.")
            self.on_status("authenticating")
            hello = channel.receive()
            if not hello or hello.get("version") != PROTOCOL_VERSION or hello.get("kind") != "hello":
                raise ProtocolError("Invalid peer handshake.")
            with self._lock:
                index = len(self._peers) + 1
                peer = {"id": client_id, "name": (name.strip() if 'name' in locals() else self.pairings.get_authorized_client(client_id)["name"]),
                        "channel": channel, "socket": connection, "index": index,
                        "address": address[0], "local_mode": False, "input_sequence": 0}
                self._peers[client_id] = peer
                owner = self._control_owner
                devices = self._device_snapshot_locked()
            channel.send({"version": PROTOCOL_VERSION, "kind": "hello_ack"})
            self._send_state(peer, devices, owner)
            connection.settimeout(None)
            if self._capture and len(devices) == 2:
                self._capture.start_capture()
                self._capture.set_capture_enabled(True)
            self.on_status("connected")
            self.on_log(f"[Mixput] Connected: {peer['name']} ({address[0]}).")
            self._notify_devices()
            while self.running:
                try:
                    message = channel.receive()
                except socket.timeout:
                    continue
                if message is None:
                    break
                if message.get("version") != PROTOCOL_VERSION:
                    raise ProtocolError("Unsupported peer protocol.")
                kind = message.get("kind")
                if kind == "disconnect":
                    break
                if kind == "input":
                    if not self._route_peer_input(peer, message):
                        self.on_log(f"[Mixput] Rejected input from {peer['name']}: stale, unauthorized, or invalid event.")
                elif kind == "local_mode":
                    enabled = message.get("enabled")
                    if not isinstance(enabled, bool):
                        raise ProtocolError("Invalid local-mode state.")
                    with self._lock:
                        current_peer = self._peers.get(client_id)
                        valid = current_peer is peer
                        if valid:
                            current_peer["local_mode"] = enabled
                            return_to_host = enabled and self._control_owner == client_id
                        else:
                            return_to_host = False
                    if not valid:
                        break
                    self.on_log(
                        f"[Mixput] {peer['name']} {'entered local mode' if enabled else 'returned to shared mode'}."
                    )
                    if return_to_host:
                        self._set_owner("host", "right")
                    else:
                        self._notify_devices()
                elif kind == "control_switch":
                    side = message.get("side")
                    requested_epoch = message.get("ownership_epoch")
                    with self._lock:
                        devices_now = self._device_snapshot_locked()
                        current_index = next((d["index"] for d in devices_now if d["id"] == client_id), -1)
                        target_index = current_index + (1 if side == "right" else -1 if side == "left" else 0)
                        target = next((d for d in devices_now if d["index"] == target_index), None)
                        allowed = (
                            self._control_owner == client_id
                            and not peer.get("local_mode", False)
                            and isinstance(requested_epoch, int)
                            and not isinstance(requested_epoch, bool)
                            and requested_epoch == self._ownership_epoch
                            and side in ("left", "right")
                        )
                    if allowed and target:
                        self._set_owner(target["id"], "left" if side == "right" else "right")
                elif kind == "chat":
                    text = message.get("text")
                    if isinstance(text, str) and 0 < len(text.strip()) <= MAX_CHAT_LENGTH:
                        chat = {"version": PROTOCOL_VERSION, "kind": "chat", "sender_id": client_id,
                                "sender": peer["name"], "text": text.strip()}
                        self.on_chat(chat)
                        with self._lock:
                            peers = list(self._peers.values())
                        for recipient in peers:
                            if recipient["id"] != client_id:
                                try:
                                    recipient["channel"].send(chat)
                                except (OSError, ProtocolError, ValueError):
                                    pass
        except (OSError, ProtocolError, ValueError, KeyError, RuntimeError, TypeError) as error:
            if self.running:
                self.on_log(f"[Mixput] Peer session ended: {error}")
        finally:
            if channel:
                channel.close()
            else:
                try:
                    connection.close()
                except OSError:
                    pass
            removed = False
            with self._lock:
                if client_id and client_id in self._peers and self._peers[client_id].get("channel") is channel:
                    del self._peers[client_id]
                    removed = True
                    if self._control_owner == client_id:
                        self._control_owner = "host"
                    for index, peer_item in enumerate(sorted(self._peers.values(), key=lambda p: p["index"]), 1):
                        peer_item["index"] = index
            if removed:
                if self._capture:
                    self._capture.release_all()
                    if self._peers:
                        self._capture.set_capture_enabled(True)
                        self._capture.set_relative_mode(self._control_owner != "host")
                        self._capture.set_exclusive_capture(self._control_owner != "host" and not self.local_mode)
                    else:
                        self._capture.set_exclusive_capture(False)
                        self._capture.set_relative_mode(False)
                        self._capture.stop_capture()
                self._notify_devices()
                self.on_log("[Mixput] A device disconnected.")
            if self.running:
                with self._lock:
                    has_peers = bool(self._peers)
                self.on_status("connected" if has_peers else "listening")

    def _close_all_peers(self):
        with self._lock:
            peers = list(self._peers.values())
            self._peers.clear()
            pending = list(self._pending.values())
            self._control_owner = "host"
        for item in pending:
            item["approved"] = False
            item["event"].set()
        for peer in peers:
            peer["channel"].close()
        if self._capture:
            self._capture.set_exclusive_capture(False)
            self._capture.set_relative_mode(False)
            self._capture.stop_capture()
            self._capture.release_all()
        with self._lock:
            host_devices = self._device_snapshot_locked()
        self.on_devices(host_devices)

    def stop(self):
        with self._lock:
            self.running = False
            server = self._server_socket
            thread = self._thread
        self._close_all_peers()
        if server:
            try:
                server.close()
            except OSError:
                pass
        if thread and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            if thread is None or not thread.is_alive():
                self._thread = None
        self.on_status("stopped")
        self.on_log("[Mixput] Sharing stopped.")
