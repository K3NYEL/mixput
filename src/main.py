import tkinter as tk
from tkinter_icons import LucideIcon #type: ignore

from components import theme

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.system_ascii()
        self.title("Mixput")
        self.windows_center(600, 400)
        self.resizable(False, False)
        self.bind("<Configure>", self.on_move)
        self.theme = theme
        self.DARK_THEME = False   
        self.CURRENT_THEME = self.theme.LIGHT_THEME
        self.create_widgets()

        self.moon_icon = LucideIcon("moon", size=20, color=self.CURRENT_THEME["text_primary"])
        self.sun_icon = LucideIcon("sun", size=20, color=self.CURRENT_THEME["text_primary"])

    def windows_center(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def on_move(self, event):
        x = self.winfo_x()
        y = self.winfo_y()
        print(f"Window position: ({x}, {y})")

    def system_ascii(self):
        print(f"System ASCII: {self.tk.call('tk', 'windowingsystem')}")

    def create_widgets(self):
        self.charge_icon_theme = LucideIcon("sun-moon", size=20, color=self.CURRENT_THEME["text_primary"])

        self.canvas = tk.Canvas(self, bg=theme.CURRENT_THEME["bg_main"], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.nav_frame = tk.Frame(self.canvas, width=200, height=200, bg=theme.CURRENT_THEME["bg_secondary"], highlightbackground=theme.CURRENT_THEME["border"], highlightthickness=1)
        self.nav_frame.pack(padx=6, pady=5, fill="x", side=tk.TOP, anchor=tk.N, )

        self.lbl_title = tk.Label(self.nav_frame, text="Mixput", font=("Arial", 16), bg=theme.CURRENT_THEME["bg_secondary"], fg=theme.CURRENT_THEME["text_primary"])
        self.lbl_title.pack(padx=5, pady=5, fill="x", side=tk.LEFT, anchor=tk.N,)

        self.theme_button = tk.Button(self.nav_frame, image=self.charge_icon_theme, width=30,  command=self.toggle_theme, bg=theme.CURRENT_THEME["bg_secondary"], fg=theme.CURRENT_THEME["text_primary"], highlightbackground=theme.CURRENT_THEME["border"])
        self.theme_button.pack(padx=5, pady=5, fill="x", side=tk.RIGHT, anchor=tk.N, )

        self.frame = tk.Frame(self.canvas, width=200, height=200, bg=theme.CURRENT_THEME["bg_secondary"], highlightbackground=theme.CURRENT_THEME["border"], highlightthickness=1)
        self.frame.pack(padx=5, fill="x", side=tk.TOP, anchor=tk.N, )

    def toggle_theme(self):
        self.DARK_THEME = not self.DARK_THEME   

        if self.DARK_THEME:
            self.CURRENT_THEME = self.theme.DARK_THEME
            self.theme_button.config(image=self.moon_icon)
            print("Theme changed to DARK_THEME")
        else:
            self.CURRENT_THEME = self.theme.LIGHT_THEME
            self.theme_button.config(image=self.sun_icon)
            print("Theme changed to LIGHT_THEME")

        self.theme_apply()

    def theme_apply(self):
        t = self.CURRENT_THEME

        self.config(bg=t["bg_main"])
        self.canvas.config(bg=t["bg_main"])
        self.frame.config(bg=t["bg_secondary"])
        self.nav_frame.config(bg=t["bg_secondary"])
        self.lbl_title.config(bg=t["bg_secondary"], fg=t["text_primary"])
        self.theme_button.config(
            bg=t["bg_secondary"],
            fg=t["text_primary"],
            activebackground=t["bg_secondary"],
            activeforeground=t["text_primary"],
        )

if __name__ == "__main__":
    app = App()
    app.mainloop()