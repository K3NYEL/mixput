import tkinter as tk
from tkinter import messagebox
import sys
from pathlib import Path
from PIL import Image, ImageTk

from app.components import theme, App

class MainWindows(tk.Tk):
    def __init__(self):
        super().__init__()
        self.create_widgets()
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

    def resource_path(self, relative_path: str) -> Path:
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return base_path / relative_path

    def _set_window_icon(self):
        icon_file = self.resource_path("public/assets/mixput-ico.png")

        if icon_file.exists():
            with Image.open(icon_file) as img:
                self._icon_photo = ImageTk.PhotoImage(img.copy())
                self.iconphoto(True, self._icon_photo)


    def create_widgets(self):
        self.app = App()
        self.app.pack(fill=tk.BOTH, expand=True)

if __name__ == "__main__":
    app = MainWindows()
    app.mainloop()
