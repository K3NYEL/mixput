import tkinter as tk
import sys
from pathlib import Path
from PIL import Image, ImageTk

from app.components import theme, App


class MainWindows(tk.Tk):
    def __init__(self):
        super().__init__()
        self.create_widgets()
        self.title("Mixput")
        self.windows_center(700, 500)
        self.resizable(False, False)
        self.theme = theme
        self.DARK_THEME = False
        self.CURRENT_THEME = self.theme.LIGHT_THEME
        self._set_window_icon()

    def resource_path(self, relative_path: str) -> Path:
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return base_path / relative_path

    def _set_window_icon(self):
        icon_file = self.resource_path("public/assets/mixput-ico.png")

        if icon_file.exists():
            with Image.open(icon_file) as img:
                self._icon_photo = ImageTk.PhotoImage(img.copy())
                self.iconphoto(True, self._icon_photo)

    def windows_center(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def create_widgets(self):
        self.app = App()
        self.app.pack(fill=tk.BOTH, expand=True)


if __name__ == "__main__":
    app = MainWindows()
    app.mainloop()
