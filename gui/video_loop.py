"""Live video display loop and FPS metering."""

import time

import cv2
import numpy as np
from PIL import Image, ImageTk

from gui.constants import HEIGHT, WIDTH


class VideoLoop:
    """Reads frames, processes, displays, and reschedules itself on the Tk loop."""

    def __init__(self, app):
        self.app = app
        self.frame_count = 0
        self.fps_start_time = time.time()
        self.fps_history = []

    def start(self):
        self.update_frame()

    def update_frame(self):
        app = self.app

        if app.recording.is_recording:
            app.root.after(200, self.update_frame)
            return

        ret, frame = app.camera.read_frame()
        if ret:
            self.frame_count += 1
            frame = app.recording.process_frame(frame)

            display = (
                (frame - np.percentile(frame, 1))
                / (np.percentile(frame, 99) - np.percentile(frame, 1))
                * 255
            ).clip(0, 255).astype(np.uint8)

            if len(display.shape) == 2:
                display_color = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)
            else:
                display_color = display

            half = app.roi_half_var.get()
            y1, y2 = HEIGHT // 2 - half, HEIGHT // 2 + half
            x1, x2 = WIDTH // 2 - half, WIDTH // 2 + half

            temp_c = None
            try:
                avg = int(np.mean(frame[y1:y2, x1:x2]))
                temp_c = app.camera.temp_from_counts(avg)
            except Exception:
                pass

            if app.show_overlay_var.get():
                cv2.rectangle(display_color, (x1, y1), (x2, y2), (0, 255, 255), 2)
                if temp_c:
                    cv2.putText(
                        display_color,
                        f"{temp_c:.1f}°C",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 255),
                        2,
                    )

            img = Image.fromarray(cv2.cvtColor(display_color, cv2.COLOR_BGR2RGB))
            img = img.resize((900, 720), Image.BILINEAR)
            imgtk = ImageTk.PhotoImage(img)
            app.video_label.imgtk = imgtk
            app.video_label.configure(image=imgtk)

        current_time = time.time()
        if current_time - self.fps_start_time >= 5:
            fps = self.frame_count / (current_time - self.fps_start_time)
            self.fps_history.append(fps)
            if len(self.fps_history) > 3:
                self.fps_history.pop(0)
            avg_fps = sum(self.fps_history) / len(self.fps_history)
            app.fps_var.set(f"FPS: {avg_fps:.1f}")
            self.frame_count = 0
            self.fps_start_time = current_time

        app.root.after(40, self.update_frame)
