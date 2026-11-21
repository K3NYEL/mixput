"""Native X11 keyboard and pointer capture with event forwarding to Mixput."""
import select
import threading


_SPECIAL_KEYS = {
    "Shift_L": "shift", "Shift_R": "shift",
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Alt_L": "alt", "Alt_R": "alt", "Meta_L": "cmd", "Meta_R": "cmd",
    "Super_L": "cmd", "Super_R": "cmd",
    "Return": "enter", "Escape": "esc", "BackSpace": "backspace",
    "Tab": "tab", "space": "space", "Delete": "delete",
    "Insert": "insert", "Home": "home", "End": "end",
    "Prior": "page_up", "Next": "page_down",
    "Left": "left", "Right": "right", "Up": "up", "Down": "down",
    "Caps_Lock": "caps_lock",
}


class X11GrabController:
    """Owns X11 grabs and forwards grabbed events; never silently discards input."""

    def __init__(self, on_event=None, on_edge=None, on_toggle_local=None):
        self.on_event = on_event or (lambda event: None)
        self.on_edge = on_edge or (lambda side: None)
        self.on_toggle_local = on_toggle_local or (lambda: None)
        self._desired = False
        self._stopping = threading.Event()
        self._changed = threading.Event()
        self._ready = threading.Event()
        self._applied = threading.Event()
        self._active = False
        self._error = None
        self._grab_error = None
        self._edge_sides = set()
        self._screen_size = None
        self._edge_margin = 2
        self._edge_latched = False
        self._last_position = None
        self._held = set()
        self._hotkey_latched = False
        self._thread = threading.Thread(target=self._run, name="MixputX11Grab", daemon=True)
        self._thread.start()
        if not self._ready.wait(2.0):
            raise RuntimeError("The X11 input capture thread did not initialize.")
        if self._error:
            raise RuntimeError(f"X11 input capture is unavailable: {self._error}")

    def configure_edges(self, sides, screen_size, margin=2):
        self._edge_sides = set(sides or ())
        self._screen_size = tuple(screen_size) if screen_size else None
        self._edge_margin = max(1, min(int(margin), 12))
        self._edge_latched = False

    def set_grab(self, enabled):
        self._desired = bool(enabled)
        self._applied.clear()
        self._changed.set()
        if not self._applied.wait(1.0):
            return False
        return self._active if self._desired else not self._active

    @property
    def grab_error(self):
        return self._grab_error or self._error or "X11 grab failed without a reported status."

    def close(self):
        self._stopping.set()
        self._changed.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _key_name(self, display, keycode):
        from Xlib import XK
        symbol = display.keycode_to_keysym(keycode, 0)
        name = XK.keysym_to_string(symbol) if symbol else None
        if not name:
            return ""
        if name in _SPECIAL_KEYS:
            return _SPECIAL_KEYS[name]
        if len(name) == 1:
            return name.lower()
        return name.lower()

    def _dispatch_key(self, display, event, pressed):
        key = self._key_name(display, event.detail)
        if not key:
            return
        if pressed:
            self._held.add(key)
        ctrl = "ctrl" in self._held
        alt = "alt" in self._held
        if pressed and key == "m" and ctrl and alt and not self._hotkey_latched:
            self._hotkey_latched = True
            # Modifiers may already have been forwarded before the full chord was known.
            self.on_event({"type": "key_up", "key": "ctrl"})
            self.on_event({"type": "key_up", "key": "alt"})
            threading.Thread(target=self.on_toggle_local, name="MixputLocalModeToggle", daemon=True).start()
            return
        if not pressed and key == "m":
            self._hotkey_latched = False
        if not pressed:
            self._held.discard(key)
        if self._hotkey_latched:
            return
        self.on_event({"type": "key_down" if pressed else "key_up", "key": key})

    def _dispatch_mouse(self, event, pressed):
        button = int(event.detail)
        if button in (4, 5, 6, 7):
            if pressed:
                dx = -1 if button == 6 else 1 if button == 7 else 0
                dy = 1 if button == 4 else -1 if button == 5 else 0
                self.on_event({"type": "mouse_scroll", "dx": dx, "dy": dy})
            return
        names = {1: "left", 2: "middle", 3: "right"}
        name = names.get(button)
        if name:
            self.on_event({"type": "mouse_button", "button": name, "pressed": bool(pressed)})

    def _check_edge_position(self, position):
        if not self._edge_sides or not self._screen_size:
            return False
        width, height = self._screen_size
        side = (
            "right" if "right" in self._edge_sides and position[0] >= width - self._edge_margin
            else "left" if "left" in self._edge_sides and position[0] <= self._edge_margin - 1
            else None
        )
        if side is None or not 0 <= position[1] < height:
            self._edge_latched = False
            return False
        if self._edge_latched:
            return False
        self._edge_latched = True
        # The callback may change the X11 grab state. Never run it on this
        # worker, otherwise set_grab() would wait on the thread invoking it.
        threading.Thread(
            target=self.on_edge, args=(side,),
            name="MixputX11EdgeHandoff", daemon=True,
        ).start()
        return True

    def _dispatch_motion(self, event):
        position = (int(event.root_x), int(event.root_y))
        previous = self._last_position
        self._last_position = position
        if self._check_edge_position(position):
            return
        if previous is not None:
            dx, dy = position[0] - previous[0], position[1] - previous[1]
            if dx or dy:
                self.on_event({"type": "mouse_move", "dx": dx, "dy": dy})

    @staticmethod
    def _status_code(reply):
        """python-xlib versions may return a status int or a reply with .status."""
        status = getattr(reply, "status", reply)
        return int(status)

    def _run(self):
        display = None
        grabbed_pointer = grabbed_keyboard = False
        try:
            from Xlib import X, display as xdisplay
            display = xdisplay.Display()
            root = display.screen().root
            self._ready.set()
            while not self._stopping.is_set():
                desired = self._desired
                if desired and not (grabbed_pointer and grabbed_keyboard):
                    pointer = root.grab_pointer(
                        owner_events=False,
                        event_mask=X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask,
                        pointer_mode=X.GrabModeAsync, keyboard_mode=X.GrabModeAsync,
                        confine_to=root, cursor=X.NONE, time=X.CurrentTime,
                    )
                    pointer_status = self._status_code(pointer)
                    grabbed_pointer = pointer_status == X.GrabSuccess
                    keyboard = None
                    if grabbed_pointer:
                        keyboard = root.grab_keyboard(
                            owner_events=False, pointer_mode=X.GrabModeAsync,
                            keyboard_mode=X.GrabModeAsync, time=X.CurrentTime,
                        )
                        keyboard_status = self._status_code(keyboard)
                        grabbed_keyboard = keyboard_status == X.GrabSuccess
                    else:
                        grabbed_keyboard = False
                    if not (grabbed_pointer and grabbed_keyboard):
                        if grabbed_pointer:
                            root.ungrab_pointer(X.CurrentTime)
                        if grabbed_keyboard:
                            root.ungrab_keyboard(X.CurrentTime)
                        keyboard_status = (
                            self._status_code(keyboard) if keyboard is not None else None
                        )
                        status_names = {
                            X.GrabSuccess: "GrabSuccess",
                            X.AlreadyGrabbed: "AlreadyGrabbed",
                            X.InvalidTime: "InvalidTime",
                            X.NotViewable: "NotViewable",
                            X.Frozen: "Frozen",
                        }
                        self._grab_error = (
                            "X11 exclusive capture failed: "
                            f"pointer={status_names.get(pointer_status, pointer_status)}, "
                            f"keyboard={status_names.get(keyboard_status, keyboard_status)}. "
                            "Another application may own an X11 grab, or the desktop rejected it."
                        )
                        grabbed_pointer = grabbed_keyboard = False
                    else:
                        self._grab_error = None
                    display.sync()
                    self._active = grabbed_pointer and grabbed_keyboard
                    self._last_position = None
                    self._edge_latched = False
                elif not desired and (grabbed_pointer or grabbed_keyboard):
                    if grabbed_pointer:
                        root.ungrab_pointer(X.CurrentTime)
                    if grabbed_keyboard:
                        root.ungrab_keyboard(X.CurrentTime)
                    grabbed_pointer = grabbed_keyboard = False
                    display.sync()
                    self._active = False
                    self._held.clear()
                    self._last_position = None
                if self._active == desired:
                    self._applied.set()
                if grabbed_pointer or grabbed_keyboard:
                    ready, _, _ = select.select([display.fileno()], [], [], 0.05)
                    if ready:
                        while display.pending_events():
                            event = display.next_event()
                            if event.type == X.MotionNotify:
                                self._dispatch_motion(event)
                            elif event.type == X.KeyPress:
                                self._dispatch_key(display, event, True)
                            elif event.type == X.KeyRelease:
                                self._dispatch_key(display, event, False)
                            elif event.type == X.ButtonPress:
                                self._dispatch_mouse(event, True)
                            elif event.type == X.ButtonRelease:
                                self._dispatch_mouse(event, False)
                else:
                    # The active desktop intentionally has no pointer grab.
                    # Poll its root pointer so edge switching still works when
                    # pynput/XRecord cannot deliver a global motion callback.
                    try:
                        pointer = root.query_pointer()
                        self._check_edge_position((int(pointer.root_x), int(pointer.root_y)))
                    except Exception:
                        pass
                    self._changed.wait(0.015)
                    self._changed.clear()
        except Exception as error:
            self._desired = False
            self._error = str(error)
            self._grab_error = f"X11 capture thread error: {error}"
            self._ready.set()
            self._applied.set()
        finally:
            if display is not None:
                try:
                    from Xlib import X
                    root = display.screen().root
                    if grabbed_pointer:
                        root.ungrab_pointer(X.CurrentTime)
                    if grabbed_keyboard:
                        root.ungrab_keyboard(X.CurrentTime)
                    display.sync()
                    display.close()
                except Exception:
                    pass
            self._active = False
            self._applied.set()
