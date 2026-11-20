# Mixput

![Mixput](mixput.png)

Mixput is a cross-platform desktop application for sharing one keyboard and mouse
between multiple laptops on the same local network.

## Project direction

- Windows to Windows
- Linux to Linux
- Windows to Linux
- Linux to Windows

The application is being developed around an explicit host-and-client session:
the user starts sharing on the laptop with the physical keyboard and mouse, then
connects the second laptop from its Mixput client.

## Platform support

The input backend uses `pynput` for desktop input events. Windows and Linux
(X11) are the initial targets. Wayland-only desktop sessions are not yet supported
by the current global input backend and will be handled through desktop portal
integration in a later stage.

Input sharing is an active, user-controlled session. It must remain visible and
easy to stop. Do not expose the service to untrusted networks.

## Development status

The network diagnostic controls and the first input backend/protocol modules are
in place. End-to-end input streaming, secure peer pairing, and real two-laptop
testing are still in progress; this project does not yet claim complete input
sharing functionality.
