# Mixput

Mixput shares one keyboard and mouse between two laptops on the same trusted local network. After explicit device approval, control can move between the computers by crossing the configured screen edges.

## Current desktop layout

The current two-computer layout places the remote laptop to the **right** of the host:

- Move the pointer to the host's right screen edge to enter the remote laptop.
- Move the pointer to the remote laptop's left screen edge to return to the host.
- Keyboard, mouse movement, buttons, and wheel events follow the computer that currently owns control.
- Mixput releases held keys and mouse buttons during a handoff or disconnect to reduce stuck-input issues.

Both computers must run the same compatible Mixput protocol version and remain connected during a handoff. This release supports one remote peer per host session. Multi-monitor edge routing and configurable layouts are not implemented yet.

## Connect two laptops

1. Connect both laptops to the same trusted local network and open Mixput.
2. Open **Devices** to find the other Mixput instance, or enter its LAN IPv4 address.
3. On the host, choose **Start sharing**.
4. On the other laptop, choose **Request access**.
5. Approve the new device on the host when prompted.
6. Move the pointer to the host's right edge to enter the remote desktop. Move to the remote desktop's left edge to return.

The host sends UDP discovery announcements on port 45821. The authenticated input session uses the configured TCP port (default 8080). Allow both ports through the relevant firewalls on a trusted private network.

## Security

New devices must be explicitly approved on the host. Pairing uses ephemeral X25519 key agreement and HKDF to derive a wrapping key; the generated Fernet session key is transferred inside an AES-GCM authenticated-encryption message. Input sessions use authenticated encrypted transport. Approved device credentials are stored in the user's Mixput configuration directory with restrictive file permissions on Linux. The host can revoke saved device authorization.

Input events are accepted only from the authenticated peer and only by the side that currently owns control. Do not expose Mixput's TCP port to the public internet. Use it only on a trusted local network and approve devices you recognize.

## Platform notes

The input backend uses `pynput`. Windows and Linux X11 are supported targets. Wayland-only sessions are reported as unavailable because global input capture/injection requires a desktop-portal implementation. On Linux, use an X11 desktop session and grant the application the required input permissions.

## Validation and limitations

Automated tests cover encrypted transport, input protocol validation, pairing, and loopback networking. A loopback test cannot verify physical cursor movement across two desktops. Before treating this as release-ready, verify on real devices:

- Windows to Windows, Linux X11 to Linux X11, and mixed Windows/Linux sessions.
- Keyboard layouts, modifiers, function keys, mouse buttons, movement, and scroll.
- Repeated edge transitions, disconnect/reconnect, host shutdown, and revocation.
- Multi-monitor behavior and screen scaling.

The edge handoff currently assumes a single-screen horizontal arrangement with the remote laptop to the right. Multi-monitor routing, vertical arrangements, Wayland portals, and seamless handling of differing display scaling are not implemented.
