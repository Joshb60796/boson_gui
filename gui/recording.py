"""
Frame / stream recording, background capture, and sync-with-pulse.

Phase 3: entry points (record_*) expect the Tk main thread for button state.
Workers use RuntimeCache + camera/gpio only; UI restores via ui_marshal.
"""

import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from gui.processing import finalize_frame, process_frame
from gui.review_window import StreamReviewWindow
from gui.ui_marshal import ui_call


class RecordingService:
    """Capture single frames, streams, and background reference frames."""

    def __init__(self, app):
        self.app = app
        self.background_frame = None
        self.is_recording = False
        self._rec_lock = threading.Lock()

    def process_frame(self, frame, fpn_enabled=None):
        if fpn_enabled is None:
            # Prefer cache when called from workers
            fpn_enabled = self.app.runtime_cache.snapshot_recording()["fpn_enabled"]
        return process_frame(
            frame,
            background_frame=self.background_frame,
            fpn_enabled=fpn_enabled,
        )

    def synchronized_trigger_and_capture(self, capture_func, snap, *args):
        """
        snap: dict from runtime_cache.snapshot_recording()
        """
        app = self.app
        if snap["sync_capture"]:
            delay_us = snap["capture_delay_us"]
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
        """Main-thread entry."""
        app = self.app
        app.sync_runtime_caches()
        app.btn_background.config(text="Acquiring", state="disabled")

        def do_capture():
            try:
                frames = []
                for _ in range(10):
                    ret, frame = app.camera.read_frame()
                    if ret:
                        frames.append(frame.astype(np.float32))
                    time.sleep(0.05)

                if frames:
                    self.background_frame = np.mean(frames, axis=0).astype(np.uint16)
                    print("Background frame captured and averaged.")
                    ui_call(
                        app.root,
                        lambda: app.btn_background.config(
                            text="Clear Background", command=self.clear_background
                        ),
                    )
                else:
                    print("Failed to capture background frames.")
            finally:
                def restore():
                    app.btn_background.config(
                        text=(
                            "Clear Background"
                            if self.background_frame is not None
                            else "-Background"
                        ),
                        state="normal",
                    )

                ui_call(app.root, restore)

        threading.Thread(target=do_capture, daemon=True, name="bg-capture").start()

    def clear_background(self):
        """Main-thread entry."""
        app = self.app
        self.background_frame = None
        print("Background cleared.")
        app.btn_background.config(text="-Background", command=self.capture_background)

    def record_frame(self):
        """Main-thread entry."""
        app = self.app
        app.sync_runtime_caches()
        if not app.temp_guard_ctrl.acquisition_allowed(show_error=True):
            return
        snap = app.runtime_cache.snapshot_recording()
        original_text = "Record Frame"
        app.btn_frame.config(text="Acquiring", state="disabled")

        def do_capture():
            try:
                ret, frame = app.camera.read_frame()
                if ret:
                    frame = self.process_frame(frame, fpn_enabled=snap["fpn_enabled"])
                    frame = finalize_frame(frame)
                    base_dir = Path(snap["save_path"])
                    base_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = base_dir / f"frame_{ts}.tiff"
                    cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_TIFF_COMPRESSION, 1])
                    print(f"Saved: {filepath}")
            finally:
                ui_call(
                    app.root,
                    lambda: app.btn_frame.config(
                        text=original_text, state="normal"
                    ),
                )

        threading.Thread(
            target=lambda: self.synchronized_trigger_and_capture(do_capture, snap),
            daemon=True,
            name="record-frame",
        ).start()

    def record_raw_frame(self):
        """Main-thread entry."""
        app = self.app
        app.sync_runtime_caches()
        if not app.temp_guard_ctrl.acquisition_allowed(show_error=True):
            return
        snap = app.runtime_cache.snapshot_recording()
        original_text = "Record RAW"
        app.btn_raw.config(text="Acquiring", state="disabled")

        def do_capture():
            try:
                ret, frame = app.camera.read_frame()
                if ret:
                    frame = self.process_frame(frame, fpn_enabled=snap["fpn_enabled"])
                    frame = finalize_frame(frame)
                    base_dir = Path(snap["save_path"])
                    base_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = base_dir / f"raw_{ts}.tiff"
                    cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_TIFF_COMPRESSION, 1])
                    print(f"Saved RAW: {filepath}")
            finally:
                ui_call(
                    app.root,
                    lambda: app.btn_raw.config(text=original_text, state="normal"),
                )

        threading.Thread(
            target=lambda: self.synchronized_trigger_and_capture(do_capture, snap),
            daemon=True,
            name="record-raw",
        ).start()

    def record_stream(self):
        """Main-thread entry."""
        app = self.app
        app.sync_runtime_caches()
        if not app.temp_guard_ctrl.acquisition_allowed(show_error=True):
            return
        snap = app.runtime_cache.snapshot_recording()
        original_text = "Record Stream"
        app.btn_stream.config(text="Acquiring", state="disabled")

        # Sync pulse timing on this thread path before worker starts
        # (delay/sleep may block UI briefly — same as before for sync mode)
        if snap["sync_capture"]:
            delay_us = snap["capture_delay_us"]
            delay_sec = delay_us / 1_000_000.0
            if delay_us > 0:
                app.pulses.trigger_pulse()
                time.sleep(delay_sec)
            elif delay_us < 0:
                time.sleep(-delay_sec)
                app.pulses.trigger_pulse()
            else:
                app.pulses.trigger_pulse()

        self.is_recording = True
        num_frames = snap["record_frames"]
        save_path = snap["save_path"]
        fpn = snap["fpn_enabled"]

        def do_stream_capture():
            captured_frames = []
            try:
                raw_frames = app.camera.read_frames(num_frames)
                for frame in raw_frames:
                    frame = self.process_frame(frame, fpn_enabled=fpn)
                    frame = finalize_frame(frame)
                    captured_frames.append(frame.copy())

                if captured_frames:
                    data_3d = np.stack(captured_frames, axis=2)
                    ui_call(
                        app.root,
                        lambda: StreamReviewWindow(app.root, data_3d, save_path),
                    )

                print(f"Recorded {len(captured_frames)} frames.")

            finally:
                self.is_recording = False
                ui_call(
                    app.root,
                    lambda: app.btn_stream.config(
                        text=original_text, state="normal"
                    ),
                )

        threading.Thread(
            target=do_stream_capture, daemon=True, name="record-stream"
        ).start()
