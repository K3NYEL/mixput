# Mixput networking architecture

## Session topology

Mixput uses one host/server and up to three receiver devices (four computers total). The host owns the physical keyboard and mouse capture. It is the authority for the active input owner and increments an ownership epoch whenever control moves between adjacent devices.

Each input packet includes the source, target, ownership epoch and monotonically increasing sequence. A receiver accepts input only when the target, owner and epoch match its current session. A stale or unauthorized packet is rejected.

## Discovery and connection

- UDP **45821**: local IPv4 broadcast announcements. These contain device discovery metadata only; they do not carry pairing credentials or input.
- TCP **8080** by default: pairing, authenticated session setup, input events, topology updates and group chat. The host port can be changed in the server settings.
- Discovery is best-effort. A receiver can still connect by entering the host's LAN IPv4 address manually.
- Keep both ports available only on a trusted private LAN. Do not expose the TCP service to the public internet.

Discovery announcements are not an authorization mechanism. The host must explicitly approve a new device before it receives a persistent session credential.

## Local mode and ownership

Ctrl+Alt+M toggles local mode on the current computer. When a receiver enters local mode, it tells the host, releases any injected held input, and returns ownership to the host if that receiver was active. When local mode is turned off, the host can enter the receiver again by moving to the appropriate screen edge. When the host enters local mode while a receiver is active, it sends a release-inputs control message so modifiers and mouse buttons are not left held remotely.

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
- Keyboard layouts, modifiers, function keys, mouse buttons, movement and wheel.
- Repeated edge transitions and local-mode shortcut behavior.
- Slow Wi-Fi, packet loss, disconnect/reconnect, server shutdown and authorization revocation.
- Mixed display sizes, scaling and multi-monitor edge behavior.

No latency benchmark is claimed by these changes. Wayland input portals, vertical layouts and multi-monitor routing remain separate work.
