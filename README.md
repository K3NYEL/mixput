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
forwards input in one direction; seamless cursor-edge switching is not implemented.

## Connect two laptops

1. Connect both laptops to the same trusted local network and open Mixput on both.
2. Open **Devices** to see other Mixput instances discovered on the LAN.
3. On the host laptop, choose **Start sharing** in **Connection**.
4. Select the host in **Devices** and choose **Use selected device**. Its IP and port
   are filled into the connection form.
5. Enter the pairing key shown by the host and choose **Connect**.
6. Choose **Stop** or **Disconnect** to end the session.

Mixput sends a small UDP announcement on port 45821 every two seconds and expires
devices that have not announced for eight seconds. The announcement contains only
the Mixput protocol version, a temporary device identifier, computer name, TCP port,
and whether sharing is active. It does not contain the pairing key or input events.
Manual IP entry remains available if broadcast discovery is blocked by the network.

The host listens on its network interfaces (0.0.0.0), but Mixput displays the
active interface's real LAN IPv4 address for the other laptop. The receiver must
enter that host address; 127.0.0.1 is not used as a cross-device address.

## Security

New devices must be explicitly approved on the host. Pairing uses ephemeral
X25519 key agreement and HKDF to derive a temporary wrapping key; the generated
Fernet session key is transferred inside an AES-GCM authenticated-encryption
message. Input sessions then use Fernet authentication/encryption and per-direction
sequence numbers. Approved device credentials are stored in the user's Mixput
configuration directory with restrictive file permissions on Linux. The host can
revoke any saved device authorization. Use Mixput on a trusted local network and
allow the selected TCP port through the host firewall.

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

Seamless cursor-edge transitions and Linux Wayland portal support are not
implemented. Input forwarding remains one-way: the host controls the receiver
after explicit pairing. UDP broadcast discovery can be blocked by guest Wi-Fi,
client isolation, VLAN separation, or host firewall rules; in that case, use manual
IP entry. The TCP sharing port still needs to be allowed by the firewall.
