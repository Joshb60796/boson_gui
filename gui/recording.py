"""Frame / stream recording, background capture, and sync-with-pulse."""

import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from gui.processing import finalize_frame, process_frame
from gui.review_window import StreamReviewWindow


class RecordingService:
    """Capture single frames, streams, and background reference frames."""

    def __init__(self, app):
        self.app = app
        self.background_frame = None
        self.is_recording = False

    def process_frame(self, frame):
        app = self.app
        return process_frame(
            frame,
            background_frame=self.background_frame,
            fpn_enabled=app.fpn_correction_enabled.get(),
        )

    def synchronized_trigger_and_capture(self, capture_func, *args):
        app = self.app
        if app.sync_capture_var.get():
            delay_us = app.capture_delay_us_var.get()
            delay_sec = delay_us / 1_000_000.0

            if delay_us > 0:
                app.pulses.trigger_pulse()
                time.sleep(delay_sec)
            elif delay_us < 0:
                capture_func(*args)
                time.sleep(-delay_sec)
                app.pulses.trigger_pulse()
                return
            else:
                app.pulses.trigger_pulse()

        capture_func(*args)

    def capture_background(self):
        app = self.app
        app.btn_background.config(text="Acquiring", state="disabled")

        def do_capture():
            try:
                # Sequential locked reads (camera owns the only VideoCapture.read)
                frames = []
                for _ in range(10):
                    ret, frame = app.camera.read_frame()
                    if ret:
                        frames.append(frame.astype(np.float32))
                    time.sleep(0.05)

                if frames:
                    self.background_frame = np.mean(frames, axis=0).astype(np.uint16)
                    print("Background frame captured and averaged.")
                    app.root.after(
                        0,
                        lambda: app.btn_background.config(
                            text="Clear Background", command=self.clear_background
                        ),
                    )
                else:
                    print("Failed to capture background frames.")
            finally:
                app.root.after(
                    0,
                    lambda: app.btn_background.config(
                        text=(
                            "Clear Background"
                            if self.background_frame is not None
                            else "-Background"
                        ),
                        state="normal",
                    ),
                )

        threading.Thread(target=do_capture, daemon=True).start()

    def clear_background(self):
        app = self.app
        self.background_frame = None
        print("Background cleared.")
        app.btn_background.config(text="-Background", command=self.capture_background)

    def record_frame(self):
        app = self.app
        if not app.temp_guard_ctrl.acquisition_allowed(show_error=True):
            return
        original_text = "Record Frame"
        app.btn_frame.config(text="Acquiring", state="disabled")

        def do_capture():
            try:
                ret, frame = app.camera.read_frame()
                if ret:
                    frame = self.process_frame(frame)
                    frame = finalize_frame(frame)
                    base_dir = Path(app.save_path_var.get())
                    base_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = base_dir / f"frame_{ts}.tiff"
                    cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_TIFF_COMPRESSION, 1])
                    print(f"Saved: {filepath}")
            finally:
                app.root.after(
                    0,
                    lambda: app.btn_frame.config(
                        text=original_text, state="normal"
                    ),
                )

        threading.Thread(
            target=lambda: self.synchronized_trigger_and_capture(do_capture),
            daemon=True,
        ).start()

    def record_raw_frame(self):
        app = self.app
        if not app.temp_guard_ctrl.acquisition_allowed(show_error=True):
            return
        original_text = "Record RAW"
        app.btn_raw.config(text="Acquiring", state="disabled")

        def do_capture():
            try:
                ret, frame = app.camera.read_frame()
                if ret:
                    frame = self.process_frame(frame)
                    frame = finalize_frame(frame)
                    base_dir = Path(app.save_path_var.get())
                    base_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = base_dir / f"raw_{ts}.tiff"
                    cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_TIFF_COMPRESSION, 1])
                    print(f"Saved RAW: {filepath}")
            finally:
                app.root.after(
                    0,
                    lambda: app.btn_raw.config(text=original_text, state="normal"),
                )

        threading.Thread(
            target=lambda: self.synchronized_trigger_and_capture(do_capture),
            daemon=True,
        ).start()

    def record_stream(self):
        app = self.app
        if not app.temp_guard_ctrl.acquisition_allowed(show_error=True):
            return
        original_text = "Record Stream"
        app.btn_stream.config(text="Acquiring", state="disabled")

        if app.sync_capture_var.get():
            delay_us = app.capture_delay_us_var.get()
            delay_sec = delay_us / 1_000_000.0

            if delay_us > 0:
                app.pulses.trigger_pulse()
                time.sleep(delay_sec)
            elif delay_us < 0:
                time.sleep(-delay_sec)
                app.pulses.trigger_pulse()
            else:
                app.pulses.trigger_pulse()

        # Pause live view (video_loop checks is_recording) while we grab
        self.is_recording = True
        num_frames = app.record_frames_var.get()

        def do_stream_capture():
            captured_frames = []
            try:
                # Each frame via CameraService.read_frame() under its lock
                raw_frames = app.camera.read_frames(num_frames)
                for frame in raw_frames:
                    frame = self.process_frame(frame)
                    frame = finalize_frame(frame)
                    captured_frames.append(frame.copy())

                if captured_frames:
                    data_3d = np.stack(captured_frames, axis=2)
                    app.root.after(
                        0,
                        lambda: StreamReviewWindow(
                            app.root, data_3d, app.save_path_var.get()
                        ),
                    )

                print(f"Recorded {len(captured_frames)} frames.")

            finally:
                self.is_recording = False
                app.root.after(
                    0,
                    lambda: app.btn_stream.config(
                        text=original_text, state="normal"
                    ),
                )

        threading.Thread(target=do_stream_capture, daemon=True).start()
