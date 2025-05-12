import tkinter as tk
from PIL import ImageTk

class PreviewCanvas:
    """
    Wraps a raw tk.Canvas for screenshot previews + ROI redraws.
    """
    def __init__(self, parent, controller):
        self.canvas = parent
        self.ctrl   = controller

    def show_image(self, pil_image):
        """
        Displays a PIL.Image on the canvas and fires <<PreviewUpdated>>.
        """
        # Clear old items
        self.canvas.delete("all")

        # Convert to PhotoImage and save on canvas for ROIManager to access
        photo = ImageTk.PhotoImage(pil_image)
        self.canvas.create_image(0, 0, image=photo, anchor="nw")
        self.canvas.img = photo   # <-- this is critical for ROIManager
        self.canvas.event_generate("<<PreviewUpdated>>")
