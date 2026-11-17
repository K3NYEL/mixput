import tkinter as tk
import sys 
from pathlib import Path

from app.components import theme, App

class MainWindows(tk.Tk):
    def __init__(self):
        super().__init__()
        self.create_widgets()
        self.title("Mixput")
        self.windows_center(600, 400)
        self.resizable(False, False)
        self.theme = theme
        self.DARK_THEME = False
        self.CURRENT_THEME = self.theme.LIGHT_THEME

    def resource_path(self, relative_path: str) -> Path:
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return base_path / relative_path

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
