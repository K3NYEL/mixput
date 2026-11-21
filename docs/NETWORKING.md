# Mixput networking architecture

## Session topology

Every running Mixput instance starts the same TCP listener and advertises itself on the local network. Devices use their persistent random identity to elect the same session coordinator deterministically: the device with the lexicographically smallest identity among the visible peers coordinates the session. The coordinator is a temporary protocol role, not a user-selected host computer. All other devices automatically connect to it, and any connected computer can own physical input and move the shared pointer between desktops.

The coordinator maintains the shared screen order and serializes cursor ownership changes. Input from a non-active computer is sent to the coordinator, which validates the authenticated sender, current target, ownership epoch and per-sender sequence before routing it to the active screen. The active computer keeps its own local input path. Stale, spoofed, out-of-order or unauthorized packets are rejected.

This is automatic coordinator election with bidirectional input routing. It is not a fully decentralized peer-to-peer mesh: the elected coordinator remains responsible for session ordering and routing. If it disappears, discovery expires it and the remaining devices elect a replacement; the replacement may request pairing approval again.

## Discovery and connection

- UDP **45821**: local IPv4 broadcast announcements. These contain discovery metadata only; they do not carry pairing credentials or input.
- TCP **8080**: every device listens on this port by default. Pairing, authenticated session setup, input events, topology updates and group chat use the elected coordinator's listener.
- Both devices must be running Mixput on the same reachable LAN. The app starts discovery and listening automatically; users do not choose a host, enter an IP address or manually connect as a client.
- Discovery is best-effort and depends on the LAN allowing broadcast traffic. Wi-Fi client isolation, guest networks and firewall rules can prevent peers from seeing each other.
- Keep both ports available only on a trusted private LAN. Do not expose the TCP service to the public internet.

Discovery announcements are not an authorization mechanism. A newly elected coordinator must explicitly approve an unknown device before it receives a persistent session credential.

## Local mode and ownership

Ctrl+Alt+M toggles local mode on the current computer. When a receiver enters local mode, it tells the host, releases any injected held input, and returns ownership to the host if that receiver was active. When local mode is turned off, the host can enter the receiver again by moving to the appropriate screen edge. When the host enters local mode while a receiver is active, it sends a release-inputs control message so modifiers and mouse buttons are not left held remotely.

## Linux desktop permissions

Linux input sharing currently requires an X11/Xorg desktop session. Mixput must run as the logged-in desktop user so it can use that session's `DISPLAY` and `XAUTHORITY` credentials. The X server must expose the XTEST extension for pointer and keyboard injection.

Mixput checks the X11 connection and XTEST availability before starting input sharing and reports actionable errors in the UI. Do not run Mixput with `sudo`, do not loosen permissions on `/dev/input`, and do not add broad device permissions: this backend uses the user's X11 session rather than reading raw input devices. Wayland is not supported by this backend yet; choose an Xorg session at login.

## Pairing and secure transport

1. A new device sends a bounded pairing request with a fresh X25519 public key and random salt.
2. The host asks the user to approve or reject that device.
3. Both peers derive a wrapping key with HKDF-SHA256.
4. The host creates a session token and transfers it inside an AES-256-GCM authenticated-encryption payload.
5. The token is stored by the pairing store and used by the Fernet-authenticated session channel.
6. Session frames carry sequence numbers; invalid, reordered or replayed frames are rejected.

The UDP discovery packet is intentionally separate from the authenticated TCP session. Never treat a discovered device name or IP address as proof of identity.

## Input transport and backpressure

The secure channel owns one bounded outbound queue and one writer thread per connection. Event-capture callbacks enqueue frames instead of calling socket.sendall() directly. This prevents a slow peer from blocking the local input-capture thread.

The queue is limited to 256 pending frames. If it fills, Mixput closes the secure connection rather than silently dropping arbitrary key/button transitions. The peer's disconnect cleanup releases held keys and mouse buttons. This is a fail-safe policy; it favors correct input state over keeping a congested session alive.

TCP uses TCP_NODELAY and SO_KEEPALIVE. Reads remain blocking after the handshake; closing the channel shuts down the socket and wakes the receiver. This avoids sharing a short socket timeout with the asynchronous writer.

## Reconnection and resource limits

The client retries a lost session using its saved pairing credential. The delay grows from 1 second to a maximum of 20 seconds. A manual disconnect cancels the retry loop.

The host limits concurrent unauthenticated handshakes to eight worker slots and enforces the four-computer session limit independently. Pairing approval can take up to 60 seconds, so the client handshake timeout allows 65 seconds.

## Validation status

The repository's unit tests cover secure bidirectional framing, replay/sequence rejection, oversized frames, bounded-queue overflow and input-protocol validation. They do not prove physical cursor handoff or end-to-end latency.

Before a release, test on real Windows and Linux X11 machines:
- Keyboard layouts, modifiers, function keys, mouse buttons, movement and wheel from every connected computer.
- Simultaneous input from more than one computer, repeated edge transitions and local-mode shortcut behavior.
- Slow Wi-Fi, packet loss, disconnect/reconnect, server shutdown and authorization revocation.
- Mixed display sizes, scaling and multi-monitor edge behavior.

No latency benchmark is claimed by these changes. Wayland input portals, vertical layouts and multi-monitor routing remain separate work.
