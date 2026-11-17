import tkinter as tk
import sys 
import os 

from components import theme, App

class MainWindows(tk.Tk):
    def __init__(self):
        super().__init__()
        self.system_ascii()
        self.create_widgets()
        self.title("Mixput")
        self.windows_center(600, 400)
        self.resizable(False, False)
        self.theme = theme
        self.DARK_THEME = False
        self.CURRENT_THEME = self.theme.LIGHT_THEME

    def resource_path(self, relative_path):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)

    def system_ascii(self):
        print(f"System ASCII: {self.tk.call('tk', 'windowingsystem')}")

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
