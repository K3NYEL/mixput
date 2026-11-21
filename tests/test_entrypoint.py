import tkinter
import unittest

from mixput import MainWindow, main


class ApplicationEntrypointTests(unittest.TestCase):
    def test_console_entrypoint_targets_the_desktop_application(self):
        self.assertTrue(callable(main))
        self.assertTrue(issubclass(MainWindow, tkinter.Tk))


if __name__ == "__main__":
    unittest.main()
