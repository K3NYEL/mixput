import unittest

from app.components.core.x11_input_capture import X11GrabController


class X11GrabStatusTests(unittest.TestCase):
    def test_status_code_accepts_python_xlib_integer_result(self):
        self.assertEqual(X11GrabController._status_code(0), 0)
        self.assertEqual(X11GrabController._status_code(1), 1)

    def test_status_code_accepts_reply_object(self):
        class Reply:
            status = 2

        self.assertEqual(X11GrabController._status_code(Reply()), 2)


if __name__ == "__main__":
    unittest.main()
