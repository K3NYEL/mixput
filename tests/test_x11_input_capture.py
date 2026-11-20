import threading
import unittest

from app.components.core.x11_input_capture import X11GrabController


class X11InputDispatchTests(unittest.TestCase):
    def controller(self):
        controller = object.__new__(X11GrabController)
        controller.on_event = lambda event: self.events.append(event)
        controller.on_edge = lambda side: None
        controller.on_toggle_local = self.toggled.set
        controller._held = set()
        controller._hotkey_latched = False
        controller._key_name = lambda display, keycode: {
            1: "ctrl", 2: "alt", 3: "m", 4: "a"
        }[keycode]
        return controller

    def setUp(self):
        self.events = []
        self.toggled = threading.Event()

    def test_mouse_buttons_are_normalized(self):
        controller = self.controller()
        class Event:
            detail = 1
        controller._dispatch_mouse(Event(), True)
        controller._dispatch_mouse(Event(), False)
        self.assertEqual(self.events, [
            {"type": "mouse_button", "button": "left", "pressed": True},
            {"type": "mouse_button", "button": "left", "pressed": False},
        ])

    def test_wheel_buttons_become_scroll_events(self):
        controller = self.controller()
        class Event:
            detail = 4
        controller._dispatch_mouse(Event(), True)
        Event.detail = 5
        controller._dispatch_mouse(Event(), True)
        self.assertEqual(self.events, [
            {"type": "mouse_scroll", "dx": 0, "dy": 1},
            {"type": "mouse_scroll", "dx": 0, "dy": -1},
        ])

    def test_ctrl_alt_m_triggers_local_toggle_and_releases_modifiers(self):
        controller = self.controller()
        class Event:
            detail = 1
        controller._dispatch_key(None, Event(), True)
        Event.detail = 2
        controller._dispatch_key(None, Event(), True)
        Event.detail = 3
        controller._dispatch_key(None, Event(), True)
        self.assertTrue(self.toggled.wait(1.0))
        self.assertEqual(self.events[-2:], [
            {"type": "key_up", "key": "ctrl"},
            {"type": "key_up", "key": "alt"},
        ])
        self.assertFalse(any(event.get("key") == "m" for event in self.events))

    def test_regular_key_is_forwarded(self):
        controller = self.controller()
        class Event:
            detail = 4
        controller._dispatch_key(None, Event(), True)
        self.assertEqual(self.events, [{"type": "key_down", "key": "a"}])


if __name__ == "__main__":
    unittest.main()
