import tkinter as tk 

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.system_ascii()
        self.title("Mixput")
        self.windows_center(600, 400)
        self.resizable(False, False)
        self.bind("<Configure>", self.on_move)

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

    
if __name__ == "__main__":
    app = App()
    app.mainloop()