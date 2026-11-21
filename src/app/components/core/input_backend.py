"""Cross-platform input capture/playback with left/right edge handoff."""
import os
import platform
import threading

from app.components.core.diagnostics import get_logger

_LOG = get_logger("input")


class InputBackendError(RuntimeError):
    pass


class InputBackend:
    def __init__(self, on_event=None, on_edge=None):
        self.on_event = on_event or (lambda event: None)
        self.on_edge = on_edge or (lambda side: None)
        self.on_toggle_local = lambda: None
        self._hotkey_keys = set()
        self._hotkey_latched = False
        self._keyboard_listener = None
        self._mouse_listener = None
        self._controller = None
        self._pynput = None
        self._last_position = None
        self._pressed_keys = set()
        self._pressed_buttons = set()
        self._lock = threading.RLock()
        self._capture_enabled = False
        self._edge_sides = set()
        self._screen_size = None
        self._edge_margin = 2
        self._edge_latched = False
        self._suppress_move = False
        self._relative_mode = False
        self._exclusive_enabled = False
        self._x11_grabber = None

    @staticmethod
    def availability():
        system = platform.system()
        if system not in ("Windows", "Linux"):
            return False, f"{system} is not supported."
        if system == "Linux" and os.environ.get("WAYLAND_DISPLAY") and os.environ.get("XDG_SESSION_TYPE", "").lower() != "x11":
            return False, "Wayland sessions are not supported yet. Select an X11 desktop session."
        try:
            import pynput  # noqa: F401
            if system == "Linux":
                from Xlib import X, display as xdisplay  # noqa: F401
                if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
                    return False, (
                        "Wayland input permission is not available yet. "
                        "Log out and choose an X11/Xorg session, then start Mixput again."
                    )
                if not os.environ.get("DISPLAY"):
                    return False, (
                        "Mixput cannot find the Linux desktop display (DISPLAY is empty). "
                        "Launch it from your logged-in graphical X11 session, not with sudo."
                    )
                try:
                    display = xdisplay.Display()
                    try:
                        if not display.has_extension("XTEST"):
                            return False, (
                                "The X11 server does not provide XTEST input access. "
                                "Enable the XTEST extension or use a supported Xorg session."
                            )
                    finally:
                        display.close()
                except Exception as error:
                    return False, (
                        "Mixput cannot access your X11 desktop. Run it as your normal "
                        "logged-in user so it can use the desktop session's Xauthority. "
                        f"Details: {error}"
                    )
        except Exception as error:
            return False, f"Native input capture is unavailable: {error}"
        return True, "Linux desktop input access ready" if system == "Linux" else "Ready"

    def configure_edge_switch(self, side, screen_size, on_edge=None, margin=2):
        sides = {side} if isinstance(side, str) else set(side or ())
        if not sides.issubset({"left", "right"}):
            raise ValueError("Edge sides must contain only 'left' and/or 'right'.")
        width, height = screen_size
        if int(width) < 2 or int(height) < 2:
            raise ValueError("Invalid screen dimensions.")
        self._edge_sides = sides
        self._screen_size = (int(width), int(height))
        self._edge_margin = max(1, min(int(margin), 12))
        if on_edge is not None:
            self.on_edge = on_edge
        if self._x11_grabber:
            self._x11_grabber.configure_edges(self._edge_sides, self._screen_size, self._edge_margin)

    def _on_x11_event(self, event):
        with self._lock:
            if not self._capture_enabled or not self._exclusive_enabled:
                return
        self.on_event(event)

    def _on_x11_edge(self, side):
        # Edge handoff is needed on the active desktop too, when exclusive
        # capture is deliberately released. The X11 monitor invokes this from
        # its own worker, so session changes never block the Xlib event loop.
        with self._lock:
            if not self._capture_enabled or self._relative_mode:
                return
        # X11GrabController owns the edge latch and rearms it after the pointer
        # leaves the boundary; do not maintain a second latch here.
        self.on_edge(side)

    def _edge_for_position(self, position):
        """Detect an active-screen edge and re-arm after leaving the boundary."""
        if self._relative_mode or not self._edge_sides or not self._screen_size:
            return None
        width, height = self._screen_size
        x, y = position
        side = (
            "right" if "right" in self._edge_sides and x >= width - self._edge_margin
            else "left" if "left" in self._edge_sides and x <= self._edge_margin - 1
            else None
        )
        if side is None or not 0 <= y < height:
            self._edge_latched = False
            return None
        if self._edge_latched:
            return None
        self._edge_latched = True
        return side

    def _load(self):
        available, reason = self.availability()
        if not available:
            raise InputBackendError(reason)
        from pynput import keyboard, mouse
        self._pynput = (keyboard, mouse)

    def start_capture(self):
        with self._lock:
            if self._keyboard_listener and self._mouse_listener:
                self._capture_enabled = True
                self._edge_latched = False
                return
            self._load()
            keyboard, mouse = self._pynput
            if platform.system() == "Linux" and self._x11_grabber is None:
                from app.components.core.x11_input_capture import X11GrabController
                self._x11_grabber = X11GrabController(
                    on_event=self._on_x11_event,
                    on_edge=self._on_x11_edge,
                    on_toggle_local=self.on_toggle_local,
                )
                # The coordinator can be the active desktop from the instant
                # the first peer joins; configure edge monitoring before any
                # ownership transfer occurs.
                edge_sides = set() if self._relative_mode else self._edge_sides
                self._x11_grabber.configure_edges(
                    edge_sides, self._screen_size, self._edge_margin
                )

            def is_enabled():
                with self._lock:
                    return self._capture_enabled

            def key_event(kind, key):
                try:
                    value = key.char if key.char is not None else key.name
                except AttributeError:
                    value = str(key).replace("Key.", "")
                value = str(value) if value else ""
                identity = value.lower()
                toggle = False
                with self._lock:
                    if kind == "key_down":
                        self._hotkey_keys.add(identity)
                        has_ctrl = any(item in self._hotkey_keys for item in ("ctrl", "ctrl_l", "ctrl_r"))
                        has_alt = any(item in self._hotkey_keys for item in ("alt", "alt_l", "alt_r"))
                        if identity == "m" and has_ctrl and has_alt and not self._hotkey_latched:
                            self._hotkey_latched = True
                            toggle = True
                    elif kind == "key_up":
                        self._hotkey_keys.discard(identity)
                        if identity == "m":
                            self._hotkey_latched = False
                if toggle:
                    # Ctrl and Alt may already have been forwarded before M completed the chord.
                    if self._exclusive_enabled:
                        self.on_event({"type": "key_up", "key": "ctrl"})
                        self.on_event({"type": "key_up", "key": "alt"})
                    self.on_toggle_local()
                    return
                with self._lock:
                    chord_held = self._hotkey_latched
                if chord_held or not is_enabled() or not self._exclusive_enabled:
                    return
                if value:
                    self.on_event({"type": kind, "key": value})

            def on_move(x, y):
                position = (int(x), int(y))
                previous = self._last_position
                self._last_position = position
                if not is_enabled():
                    return
                if self._suppress_move:
                    self._suppress_move = False
                    return
                # Linux edge handoff is monitored by the native X11
                # controller, which works even when pointer capture is released.
                side = self._edge_for_position(position) if platform.system() == "Windows" else None
                if side:
                    self.on_edge(side)
                    return
                if previous is not None and self._exclusive_enabled:
                    dx, dy = position[0] - previous[0], position[1] - previous[1]
                    if dx or dy:
                        self.on_event({"type": "mouse_move", "dx": dx, "dy": dy})
                    if self._relative_mode and self._screen_size:
                        # Keep the source cursor parked while forwarding relative motion.
                        # This is cursor confinement, not OS-level input suppression:
                        # the native backend must still intercept clicks and key presses.
                        width, height = self._screen_size
                        center = (max(2, width // 2), max(2, height // 2))
                        self._suppress_move = True
                        if self._controller is None:
                            from pynput import keyboard
                            self._controller = (keyboard.Controller(), mouse.Controller())
                        self._controller[1].position = center
                        self._last_position = center

            def on_click(x, y, button, pressed):
                if is_enabled() and self._exclusive_enabled:
                    self.on_event({"type": "mouse_button", "button": str(button).replace("Button.", ""), "pressed": bool(pressed)})

            def on_scroll(x, y, dx, dy):
                if is_enabled() and self._exclusive_enabled:
                    self.on_event({"type": "mouse_scroll", "dx": int(dx), "dy": int(dy)})

            def windows_filter(listener, data, injected_mask):
                # Do not swallow input synthesized by pynput itself. In
                # relative mode Windows must accept the injected recenter
                # movement; suppressing it leaves the physical cursor pinned
                # at the edge and makes both desktops appear frozen.
                flags = int(getattr(data, "flags", 0) or 0)
                if flags & injected_mask:
                    return True
                with self._lock:
                    should_suppress = self._capture_enabled and self._exclusive_enabled
                if should_suppress:
                    try:
                        listener.suppress_event()
                    except Exception:
                        _LOG.exception("Windows hook could not suppress an input event")
                return True

            keyboard_options = {}
            mouse_options = {}
            if platform.system() == "Windows":
                # KBDLLHOOKSTRUCT: LLKHF_INJECTED / LLKHF_LOWER_IL_INJECTED.
                # MSLLHOOKSTRUCT: LLMHF_INJECTED / LLMHF_LOWER_IL_INJECTED.
                keyboard_options["win32_event_filter"] = (
                    lambda _msg, data: windows_filter(self._keyboard_listener, data, 0x12)
                )
                mouse_options["win32_event_filter"] = (
                    lambda _msg, data: windows_filter(self._mouse_listener, data, 0x03)
                )
            self._keyboard_listener = keyboard.Listener(
                on_press=lambda key: key_event("key_down", key),
                on_release=lambda key: key_event("key_up", key),
                **keyboard_options,
            )
            self._mouse_listener = mouse.Listener(
                on_move=on_move, on_click=on_click, on_scroll=on_scroll,
                **mouse_options,
            )
            self._capture_enabled = True
            self._edge_latched = False
            try:
                self._keyboard_listener.start()
                self._mouse_listener.start()
            except Exception:
                _LOG.exception("Failed to start native keyboard/mouse listeners")
                self._capture_enabled = False
                self._exclusive_enabled = False
                for listener in (self._keyboard_listener, self._mouse_listener):
                    try:
                        if listener:
                            listener.stop()
                    except Exception:
                        _LOG.exception("Failed to stop a partially initialized input listener")
                self._keyboard_listener = None
                self._mouse_listener = None
                raise

    def set_capture_enabled(self, enabled):
        with self._lock:
            self._capture_enabled = bool(enabled)
            self._edge_latched = False
            self._last_position = None
            if not self._capture_enabled:
                self._exclusive_enabled = False
                if self._x11_grabber:
                    self._x11_grabber.set_grab(False)

    def set_exclusive_capture(self, enabled):
        with self._lock:
            requested = bool(enabled and self._capture_enabled)
            if self._x11_grabber and not self._x11_grabber.set_grab(requested):
                self._exclusive_enabled = False
                return False
            self._exclusive_enabled = requested
            if self._x11_grabber:
                edge_sides = set() if self._relative_mode else self._edge_sides
                self._x11_grabber.configure_edges(edge_sides, self._screen_size, self._edge_margin)
            return True

    def set_relative_mode(self, enabled):
        with self._lock:
            self._relative_mode = bool(enabled)
            self._last_position = None
            if self._x11_grabber:
                edge_sides = set() if self._relative_mode else self._edge_sides
                self._x11_grabber.configure_edges(edge_sides, self._screen_size, self._edge_margin)

    def park_cursor(self):
        try:
            if self._pynput is None:
                self._load()
            _, mouse = self._pynput
            if self._controller is None:
                from pynput import keyboard
                self._controller = (keyboard.Controller(), mouse.Controller())
            width, height = self._screen_size or (1920, 1080)
            position = (max(2, width // 2), max(2, height // 2))
            self._suppress_move = True
            self._controller[1].position = position
            self._last_position = position
            return True
        except (InputBackendError, OSError, ValueError, TypeError):
            _LOG.exception("Could not park the local cursor")
            return False

    def warp_to_edge(self, side):
        if side not in ("left", "right"):
            return False
        try:
            if self._pynput is None:
                self._load()
            _, mouse = self._pynput
            if self._controller is None:
                from pynput import keyboard
                self._controller = (keyboard.Controller(), mouse.Controller())
            width, height = self._screen_size or (1920, 1080)
            x = 2 if side == "left" else max(2, width - 3)
            self._suppress_move = True
            self._controller[1].position = (x, max(1, height // 2))
            self._last_position = (x, max(1, height // 2))
            self._edge_latched = False
            return True
        except (InputBackendError, OSError, ValueError, TypeError):
            _LOG.exception("Could not warp the cursor to the incoming screen edge")
            return False

    def stop_capture(self):
        with self._lock:
            listeners = (self._keyboard_listener, self._mouse_listener)
            self._keyboard_listener = None
            self._mouse_listener = None
            self._capture_enabled = False
            self._exclusive_enabled = False
            if self._x11_grabber:
                self._x11_grabber.set_grab(False)
            self._last_position = None
        for listener in listeners:
            if listener:
                listener.stop()
        self.release_all()

    def apply_event(self, event):
        if not isinstance(event, dict):
            return False
        kind = event.get("type")
        try:
            if self._pynput is None:
                self._load()
            keyboard, mouse = self._pynput
            if self._controller is None:
                self._controller = (keyboard.Controller(), mouse.Controller())
            key_controller, mouse_controller = self._controller
            if kind in ("key_down", "key_up"):
                key_name = event.get("key")
                if not isinstance(key_name, str) or not 0 < len(key_name) <= 32:
                    return False
                key = getattr(keyboard.Key, key_name, None)
                if key is None:
                    if len(key_name) != 1:
                        return False
                    key = key_name
                if kind == "key_down":
                    key_controller.press(key)
                    self._pressed_keys.add(key)
                else:
                    key_controller.release(key)
                    self._pressed_keys.discard(key)
            elif kind == "mouse_move":
                dx, dy = int(event.get("dx", 0)), int(event.get("dy", 0))
                if abs(dx) > 2000 or abs(dy) > 2000:
                    return False
                x, y = mouse_controller.position
                next_x, next_y = x + dx, y + dy
                mouse_controller.position = (next_x, next_y)
                if self._edge_sides and self._screen_size and not self._edge_latched:
                    width, height = self._screen_size
                    side = "right" if "right" in self._edge_sides and next_x >= width - self._edge_margin else (
                        "left" if "left" in self._edge_sides and next_x <= self._edge_margin - 1 else None)
                    if side and 0 <= next_y < height:
                        self._edge_latched = True
                        self.on_edge(side)
                elif self._relative_mode and self._screen_size:
                    width, height = self._screen_size
                    if next_x <= 1 or next_x >= width - 2 or next_y <= 1 or next_y >= height - 2:
                        center = (max(2, width // 2), max(2, height // 2))
                        self._suppress_move = True
                        mouse_controller.position = center
            elif kind == "mouse_button":
                button = getattr(mouse.Button, event.get("button"), None)
                if button is None:
                    return False
                if event.get("pressed") is True:
                    mouse_controller.press(button)
                    self._pressed_buttons.add(button)
                else:
                    mouse_controller.release(button)
                    self._pressed_buttons.discard(button)
            elif kind == "mouse_scroll":
                dx, dy = int(event.get("dx", 0)), int(event.get("dy", 0))
                if abs(dx) > 20 or abs(dy) > 20:
                    return False
                mouse_controller.scroll(dx, dy)
            else:
                return False
            return True
        except (InputBackendError, OSError, ValueError, TypeError):
            _LOG.exception("Could not apply remote input event: %r", event)
            return False

    def release_all(self):
        if self._controller is None:
            return
        keyboard_controller, mouse_controller = self._controller
        for key in tuple(self._pressed_keys):
            try:
                keyboard_controller.release(key)
            except Exception:
                pass
        for button in tuple(self._pressed_buttons):
            try:
                mouse_controller.release(button)
            except Exception:
                pass
        self._pressed_keys.clear()
        self._pressed_buttons.clear()

    def close(self):
        self.stop_capture()
        self.release_all()
        if self._x11_grabber:
            self._x11_grabber.close()
            self._x11_grabber = None
        self._exclusive_enabled = False
        self._controller = None
