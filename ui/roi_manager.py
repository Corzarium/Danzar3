# ui/roi_manager.py

import mss

HANDLE = 8  # Size of the little resize handle in px

class ROIManager:
    def __init__(self, canvas, cfg):
        """
        canvas: the PreviewCanvas instance
        cfg:    the same config dict your app uses (must contain 'ocr_rois' & 'monitor_index')
        """
        self.canvas = canvas
        self.cfg    = cfg
        self.rois   = cfg.setdefault("ocr_rois", {})

        # Drag state
        self._drag = {
            "key": None,
            "x":   0,
            "y":   0,
            "mode": None,
            "orig_w": 0,
            "orig_h": 0
        }

        # Redraw ROIs every time the preview updates
        self.canvas.bind("<<PreviewUpdated>>", lambda e: self.draw_rois())

        # Bind clicks on any ROI or handle
        for tag in ("roi", "handle"):
            self.canvas.tag_bind(tag, "<Button-1>", self.on_press)

    def draw_rois(self):
        # Remove only ROI graphics (keep the background intact)
        self.canvas.delete("roi")
        self.canvas.delete("handle")

        # Scale factors: real‐screen → canvas
        mon       = mss.mss().monitors[self.cfg.get("monitor_index", 1)]
        real_w, real_h = mon["width"], mon["height"]
        img_w, img_h   = self.canvas.img.width(), self.canvas.img.height()
        to_canvas_x = img_w/real_w
        to_canvas_y = img_h/real_h

        for key, roi in self.rois.items():
            x0 = roi["left"]    * to_canvas_x
            y0 = roi["top"]     * to_canvas_y
            x1 = (roi["left"] + roi["width"])  * to_canvas_x
            y1 = (roi["top"]  + roi["height"]) * to_canvas_y

            # Main rectangle
            self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline="cyan", width=2,
                tags=("roi", key)
            )
            # Bottom‐right handle
            self.canvas.create_rectangle(
                x1-HANDLE, y1-HANDLE, x1, y1,
                fill="cyan", tags=("handle", key)
            )

    def on_press(self, ev):
        # Determine which ROI or handle
        items = self.canvas.find_withtag("current")
        if not items:
            return
        tags = self.canvas.gettags(items[0])
        key  = tags[1]

        # Store drag start state
        self._drag["key"] = key
        self._drag["x"]   = ev.x
        self._drag["y"]   = ev.y
        self._drag["mode"] = "resize" if "handle" in tags else "move"

        if self._drag["mode"] == "resize":
            roi = self.rois[key]
            self._drag["orig_w"] = roi["width"]
            self._drag["orig_h"] = roi["height"]

        # Grab all Motion / Release events on the canvas
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def on_drag(self, ev):
        key  = self._drag["key"]
        mode = self._drag["mode"]
        if not key:
            return

        # Delta on canvas coords
        dx = ev.x - self._drag["x"]
        dy = ev.y - self._drag["y"]

        # Convert canvas‐delta → real‐screen units
        mon       = mss.mss().monitors[self.cfg.get("monitor_index", 1)]
        real_w, real_h = mon["width"], mon["height"]
        img_w, img_h   = self.canvas.img.width(), self.canvas.img.height()
        to_real_x = real_w/img_w
        to_real_y = real_h/img_h

        roi = self.rois[key]
        if mode == "move":
            roi["left"] += dx * to_real_x
            roi["top"]  += dy * to_real_y
        else:  # resize
            roi["width"]  = max(10, self._drag["orig_w"] + dx * to_real_x)
            roi["height"] = max(10, self._drag["orig_h"] + dy * to_real_y)

        # Update for next event
        self._drag["x"], self._drag["y"] = ev.x, ev.y

        # Redraw overlays live
        self.draw_rois()

    def on_release(self, ev):
        # Clear drag state and unbind the canvas‐wide handlers
        self._drag["key"] = None
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
