"""Cross-platform input capture and playback for explicit Mixput sessions."""
import os
import platform
import threading


class InputBackendError(RuntimeError):
    """Raised when the current desktop cannot provide input access."""


class InputBackend:
    def __init__(self, on_event=None):
        self.on_event = on_event or (lambda event: None)
        self._keyboard_listener = None
        self._mouse_listener = None
        self._controller = None
        self._pynput = None
        self._last_position = None
        self._pressed_keys = set()
        self._pressed_buttons = set()
        self._lock = threading.RLock()

    @staticmethod
    def availability():
        system = platform.system()
        if system not in ("Windows", "Linux"):
            return False, f"{system} is not supported."
        if system == "Linux" and os.environ.get("WAYLAND_DISPLAY") and os.environ.get("XDG_SESSION_TYPE", "").lower() != "x11":
            return False, "Wayland sessions are not supported yet. Select an X11 desktop session."
        try:
            import pynput  # noqa: F401
        except Exception as error:
            return False, f"Input support is unavailable: {error}"
        return True, "Ready"

    def _load(self):
        available, reason = self.availability()
        if not available:
            raise InputBackendError(reason)
        from pynput import keyboard, mouse
        self._pynput = (keyboard, mouse)

    def start_capture(self):
        """Capture local input only after a peer has authenticated."""
        with self._lock:
            if self._keyboard_listener or self._mouse_listener:
                return
            self._load()
            keyboard, mouse = self._pynput

            def key_event(kind, key):
                try:
                    value = key.char if key.char is not None else key.name
                except AttributeError:
                    value = str(key).replace("Key.", "")
                if value:
                    self.on_event({"type": kind, "key": str(value)})

            def on_move(x, y):
                position = (int(x), int(y))
                previous = self._last_position
                self._last_position = position
                if previous is not None:
                    dx, dy = position[0] - previous[0], position[1] - previous[1]
                    if dx or dy:
                        self.on_event({"type": "mouse_move", "dx": dx, "dy": dy})

            def on_click(x, y, button, pressed):
                self.on_event({
                    "type": "mouse_button",
                    "button": str(button).replace("Button.", ""),
                    "pressed": bool(pressed),
                })

            def on_scroll(x, y, dx, dy):
                self.on_event({"type": "mouse_scroll", "dx": int(dx), "dy": int(dy)})

            keyboard_listener = keyboard.Listener(
                on_press=lambda key: key_event("key_down", key),
                on_release=lambda key: key_event("key_up", key),
            )
            mouse_listener = mouse.Listener(
                on_move=on_move, on_click=on_click, on_scroll=on_scroll
            )
            self._keyboard_listener = keyboard_listener
            self._mouse_listener = mouse_listener
            keyboard_listener.start()
            mouse_listener.start()

    def stop_capture(self):
        with self._lock:
            listeners = (self._keyboard_listener, self._mouse_listener)
            self._keyboard_listener = None
            self._mouse_listener = None
            self._last_position = None
        for listener in listeners:
            if listener:
                listener.stop()

    def apply_event(self, event):
        """Apply one event received through the authenticated Mixput channel."""
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
                mouse_controller.position = (x + dx, y + dy)
            elif kind == "mouse_button":
                button_name = event.get("button")
                button = getattr(mouse.Button, button_name, None)
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
        self._controller = None
