# Mixput

Mixput is a cross-platform desktop application for sharing a keyboard and mouse
between laptops on the same local network.

## Supported connection direction

The current input-sharing session has one host and one receiver:

- Windows host to Windows receiver
- Linux host to Linux receiver (X11)
- Windows host to Linux receiver (X11)
- Linux host (X11) to Windows receiver

The host laptop captures its local keyboard and mouse. The receiver laptop applies
the events locally after a successful pairing handshake. This first implementation
forwards input in one direction; seamless cursor-edge switching and automatic
network discovery are not implemented yet.

## Connect two laptops

1. Connect both laptops to the same trusted local network.
2. On the host laptop, open Mixput Preferences and choose **Start sharing**.
3. Share the displayed LAN IPv4 address, port, and pairing key with the receiver.
4. On the receiver, enter the host LAN IP and pairing key, then choose **Connect**.
5. Choose **Stop sharing** or **Disconnect** to end the session.

The host listens on its network interfaces (0.0.0.0), but Mixput displays the
active interface's real LAN IPv4 address for the other laptop. The receiver must
enter that host address; 127.0.0.1 is not used as a cross-device address.

## Security

Pairing uses a freshly generated high-entropy Fernet key. The handshake and input
events are authenticated and encrypted, with per-direction sequence numbers to
reject replayed frames. Only share the key with a device you trust. Stop the
session when finished and use a trusted local network; firewall rules may need
to allow the selected TCP port.

## Platform notes

The input backend uses `pynput`. Windows and Linux X11 are the initial desktop
targets. Wayland-only sessions are currently reported as unavailable because
global input capture/injection needs a desktop-portal implementation.

## Validation and limitations

The repository includes automated tests for encrypted transport, protocol input
validation, and a loopback host-to-receiver session. CI runs these tests on both
Windows and Linux before packaging.

A loopback test does not replace testing with two physical laptops. Before
treating a release as stable, verify the following on real devices:

- Windows to Windows, Linux X11 to Linux X11, and mixed Windows/Linux sessions.
- Keyboard layout, modifiers, function keys, mouse buttons, movement, and scroll.
- Disconnect/reconnect behavior and recovery after the host stops sharing.
- Firewall prompts, LAN address selection, and installer behavior on clean systems.

Automatic device discovery, seamless cursor-edge transitions, and Linux Wayland
portal support are not implemented. Input forwarding remains one-way: the host
controls the receiver after explicit pairing.
