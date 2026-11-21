# Mixput

Mixput connects up to **four computers total** on the same trusted local network: one host/server and up to three remote devices. After explicit approval, devices are arranged in a horizontal row and control can move to the adjacent computer by crossing a screen edge.

## Horizontal device layout

The host occupies position 1 (leftmost). Remote devices are placed in connection order:

**Host → Device 2 → Device 3 → Device 4**

- The host's right edge enters the first remote device.
- A remote device's left edge moves to its previous neighbor; its right edge moves to its next neighbor.
- The first and last devices have only one neighboring device.
- The host is the only physical keyboard and mouse source. Its events are routed to the active desktop; each receiver applies them locally to its own desktop.
- Keyboard, mouse movement, buttons, and wheel events follow the active desktop.
- Mixput releases held keys and mouse buttons during a handoff or disconnect to reduce stuck-input issues.

All devices must run a compatible Mixput protocol version and remain connected during a handoff. The server enforces the four-device limit, counting the host.

## Connect up to four computers

1. Connect all computers to the same trusted local network and open Mixput.
2. On the host computer, choose **Start sharing**. This computer is the server and occupies the first position.
3. On each other computer, find the host under **Devices** or enter its LAN IPv4 address, then choose **Request access**.
4. Approve each new device on the host when prompted. The server rejects additional devices once four computers are connected.
5. Use the left and right screen edges to move between neighboring computers.
6. Press **Ctrl+Alt+M** on the current computer to toggle local mode. This stops shared input on that desktop; pressing it again returns the device to the shared session.
7. Open **Chat** in the main navigation to message every device in the session.

If automatic discovery does not find the host, use **Connect manually** on the Devices page and enter the host's LAN IPv4 address and TCP port.

The host sends UDP discovery announcements on port 45821. The authenticated input session uses the configured TCP port (default 8080). Allow both ports through the relevant firewalls on a trusted private network.

## Security

New devices must be explicitly approved on the host. Pairing uses ephemeral X25519 key agreement and HKDF to derive a wrapping key; the generated Fernet session key is transferred inside an AES-GCM authenticated-encryption message. Input sessions use authenticated encrypted transport. Approved device credentials are stored in the user's Mixput configuration directory with restrictive file permissions on Linux. The host can revoke saved device authorization.

Only the host captures physical keyboard and mouse input. The server routes those events to the active desktop, and each authenticated receiver applies them locally. Receiver devices do not send their own physical input back to the host. Group chat messages are relayed only among authenticated session members over their encrypted channels. Do not expose Mixput's TCP port to the public internet. Use it only on a trusted local network and approve devices you recognize.

See [docs/NETWORKING.md](docs/NETWORKING.md) for the transport architecture, pairing flow, queue/backpressure policy, reconnection behavior, and network limits.

## Platform notes

The input backend uses pynput. Windows and Linux X11 are supported targets. Wayland-only sessions are reported as unavailable because global input capture/injection requires a desktop-portal implementation. On Linux, use an X11 desktop session and grant the application the required input permissions.

## Validation and limitations

The automated suite covers encrypted bidirectional transport, replay/sequence rejection, oversized frames, bounded-queue overflow, and input-protocol validation. These tests do not verify physical cursor movement or full multi-device behavior. Before treating this as release-ready, verify on real devices:

- Windows to Windows, Linux X11 to Linux X11, and mixed Windows/Linux sessions.
- Keyboard layouts, modifiers, function keys, mouse buttons, movement, and scroll.
- Repeated edge transitions, disconnect/reconnect, host shutdown, and revocation.
- Multi-monitor behavior and screen scaling.

The edge handoff assumes a single-screen horizontal row. Multi-monitor routing, vertical arrangements, Wayland portals, and seamless handling of differing display scaling are not implemented. Physical cursor handoff and mixed display scaling still require validation on the actual computers.

The application-level virtual-IP experiment was removed: Mixput shares input over its real LAN TCP connection and does not create a VPN or configure operating-system network interfaces.

## Automatic updates

The updater displays download progress and reports the current phase: download, archive verification, extraction, installation, and restart. If an update fails, the current installation is left in place when possible and the next app launch displays the previous updater error.

Detailed updater logs are saved at:

- Windows: %LOCALAPPDATA%/Mixput/logs/update.log
- Linux: ~/.local/state/mixput/logs/update.log (or $XDG_STATE_HOME/mixput/logs/update.log when configured)

Windows installations in protected locations may request administrator approval through UAC. Linux installations in protected locations may request authorization through pkexec; per-user installations do not need elevation. If a restart does not happen, open the log above and check the last ERROR entry.
