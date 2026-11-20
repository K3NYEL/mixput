"""Cross-platform input capture/playback with left/right edge handoff."""
import os
import platform
import threading


class InputBackendError(RuntimeError):
    pass


class InputBackend:
    def __init__(self, on_event=None, on_edge=None):
        self.on_event = on_event or (lambda event: None)
        self.on_edge = on_edge or (lambda side: None)
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

            def is_enabled():
                with self._lock:
                    return self._capture_enabled

            def key_event(kind, key):
                if not is_enabled():
                    return
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
                if not is_enabled():
                    return
                if self._suppress_move:
                    self._suppress_move = False
                    return
                if self._edge_sides and self._screen_size and not self._edge_latched:
                    width, height = self._screen_size
                    side = "right" if "right" in self._edge_sides and position[0] >= width - self._edge_margin else (
                        "left" if "left" in self._edge_sides and position[0] <= self._edge_margin - 1 else None)
                    if side and 0 <= position[1] < height:
                        self._edge_latched = True
                        with self._lock:
                            self._capture_enabled = False
                        self.on_edge(side)
                        return
                if previous is not None:
                    dx, dy = position[0] - previous[0], position[1] - previous[1]
                    if dx or dy:
                        self.on_event({"type": "mouse_move", "dx": dx, "dy": dy})

            def on_click(x, y, button, pressed):
                if is_enabled():
                    self.on_event({"type": "mouse_button", "button": str(button).replace("Button.", ""), "pressed": bool(pressed)})

            def on_scroll(x, y, dx, dy):
                if is_enabled():
                    self.on_event({"type": "mouse_scroll", "dx": int(dx), "dy": int(dy)})

            self._keyboard_listener = keyboard.Listener(on_press=lambda key: key_event("key_down", key),
                                                        on_release=lambda key: key_event("key_up", key))
            self._mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
            self._capture_enabled = True
            self._edge_latched = False
            self._keyboard_listener.start()
            self._mouse_listener.start()

    def set_capture_enabled(self, enabled):
        with self._lock:
            self._capture_enabled = bool(enabled)
            self._edge_latched = False
            self._last_position = None

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
            return True
        except (InputBackendError, OSError, ValueError, TypeError):
            return False

    def stop_capture(self):
        with self._lock:
            listeners = (self._keyboard_listener, self._mouse_listener)
            self._keyboard_listener = None
            self._mouse_listener = None
            self._capture_enabled = False
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
                mouse_controller.position = (x + dx, y + dy)
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
