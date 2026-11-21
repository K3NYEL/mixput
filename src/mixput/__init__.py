"""Mixput desktop application entry point."""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from PIL import Image, ImageTk

from app.components import App, theme


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app = App()
        self.app.pack(fill=tk.BOTH, expand=True)
        self.title("Mixput")
        self.state("normal")
        self.theme = theme
        self.DARK_THEME = False
        self.CURRENT_THEME = self.theme.LIGHT_THEME
        self._set_window_icon()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.app.shutdown()
            self.destroy()

    def _set_window_icon(self):
        if getattr(sys, "_MEIPASS", None):
            root = Path(sys._MEIPASS)
        else:
            root = Path(__file__).resolve().parents[2]
        icon_file = root / "public" / "assets" / "mixput-ico.png"
        if icon_file.is_file():
            try:
                with Image.open(icon_file) as source:
                    self._icon_photo = ImageTk.PhotoImage(source.copy())
                self.iconphoto(True, self._icon_photo)
            except (OSError, tk.TclError):
                self._icon_photo = None


def main() -> None:
    """Launch the actual Mixput desktop UI (not the old scaffold placeholder)."""
    window = MainWindow()
    window.mainloop()


__all__ = ["MainWindow", "main"]
