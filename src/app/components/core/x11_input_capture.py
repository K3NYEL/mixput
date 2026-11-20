"""Exclusive X11 grabs used while Mixput routes input to another device."""
import select
import threading


class X11GrabController:
    """Grab the local pointer and keyboard without requiring root privileges."""

    def __init__(self):
        self._desired = False
        self._stopping = threading.Event()
        self._changed = threading.Event()
        self._ready = threading.Event()
        self._applied = threading.Event()
        self._active = False
        self._error = None
        self._thread = threading.Thread(target=self._run, name="MixputX11Grab", daemon=True)
        self._thread.start()
        if not self._ready.wait(2.0):
            raise RuntimeError("The X11 input capture thread did not initialize.")
        if self._error:
            raise RuntimeError(f"X11 input capture is unavailable: {self._error}")

    def set_grab(self, enabled):
        self._desired = bool(enabled)
        self._applied.clear()
        self._changed.set()
        if not self._applied.wait(1.0):
            return False
        return self._active if self._desired else not self._active

    def close(self):
        self._stopping.set()
        self._changed.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _run(self):
        display = None
        grabbed_pointer = False
        grabbed_keyboard = False
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
                        pointer_mode=X.GrabModeAsync,
                        keyboard_mode=X.GrabModeAsync,
                        confine_to=root,
                        cursor=X.NONE,
                        time=X.CurrentTime,
                    )
                    grabbed_pointer = pointer.status == X.GrabSuccess
                    keyboard = root.grab_keyboard(
                        owner_events=False,
                        pointer_mode=X.GrabModeAsync,
                        keyboard_mode=X.GrabModeAsync,
                        time=X.CurrentTime,
                    )
                    grabbed_keyboard = keyboard.status == X.GrabSuccess
                    if not (grabbed_pointer and grabbed_keyboard):
                        if grabbed_pointer:
                            root.ungrab_pointer(X.CurrentTime)
                        if grabbed_keyboard:
                            root.ungrab_keyboard(X.CurrentTime)
                        grabbed_pointer = grabbed_keyboard = False
                    display.sync()
                elif not desired and (grabbed_pointer or grabbed_keyboard):
                    if grabbed_pointer:
                        root.ungrab_pointer(X.CurrentTime)
                    if grabbed_keyboard:
                        root.ungrab_keyboard(X.CurrentTime)
                    grabbed_pointer = grabbed_keyboard = False
                    display.sync()
                    self._active = grabbed_pointer and grabbed_keyboard
                    self._applied.set()

                if grabbed_pointer or grabbed_keyboard:
                    ready, _, _ = select.select([display.fileno()], [], [], 0.05)
                    if ready:
                        while display.pending_events():
                            display.next_event()
                else:
                    self._changed.wait(0.05)
                    self._changed.clear()
        except Exception as error:
            self._desired = False
            self._error = str(error)
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
