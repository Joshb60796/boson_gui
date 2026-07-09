"""
Boson+ radiometric viewer — application orchestrator.

Collaborators (do the real work):
  gui/gpio_service.py         — single lgpio chip + pin registry
  gui/camera.py               — Boson SDK + V4L2 (locked read_frame only)
  gui/runtime_cache.py        — plain snapshots for worker threads (Phase 3)
  gui/ui_marshal.py           — root.after helpers (Phase 3)
  gui/recording.py            — frame/stream/background capture
  gui/pulse_actions.py        — GPIO pulse trigger
  gui/hardware_button.py      — physical button monitor (GPIO-only thread)
  gui/temp_guard_controller.py — temp interlock + status
  gui/main_window.py          — main UI layout
  gui/video_loop.py           — live display
  gui/settings.py             — settings dialogs
  gui/config_io.py            — config.json load/save
"""

import threading
import tkinter as tk

from gui import settings as settings_ui
from gui.camera import CameraService
from gui.config_io import load_config, save_config
from gui.constants import (
    DEFAULT_DS18B20_ID,
    DEFAULT_DS18B20_THRESHOLD_C,
    DEFAULT_GPIO_ALARM_PIN,
    DEFAULT_PULSE_PINS,
    DEFAULT_RECORD_FRAMES,
    DEFAULT_SAVE_PATH,
    DEFAULT_TEMP_GUARD_ENABLED,
    DEFAULT_TEMP_GUARD_SENSOR,
    DEFAULT_THERMISTOR_CHANNEL,
    DEFAULT_THERMISTOR_I2C_ADDR,
    DEFAULT_THERMISTOR_I2C_BUS,
    DEFAULT_THERMISTOR_THRESHOLD_V,
)
from gui.gpio_service import GpioError, GpioService
from gui.hardware_button import PhysicalButtonMonitor
from gui.main_window import MainWindow
from gui.pulse_actions import PulseService
from gui.recording import RecordingService
from gui.runtime_cache import RuntimeCache
from gui.temp_guard_controller import TempGuardController
from gui.video_loop import VideoLoop


class BosonApp:
    """
    Thin orchestrator: owns tk root/vars and wires collaborator services.

    Settings and config_io still receive this object so they can read/write
    tk variables and call a few delegated methods (apply_video_mode, etc.).
    """

    def __init__(self):
        # ---- shared GPIO (must exist before button / alarm / pulses) ----
        self.gpio = GpioService()
        try:
            self.gpio.open()
        except GpioError as e:
            print(f"WARNING: GPIO unavailable: {e}")
            print("Pulse, button, and GPIO temp-alarm will not work until lgpio is fixed.")

        # Plain settings snapshot for worker threads (Phase 3)
        self.runtime_cache = RuntimeCache()
        self._button_action_inflight = False
        self._button_inflight_lock = threading.Lock()

        # ---- collaborators ----
        self.camera = CameraService(self)
        self.recording = RecordingService(self)
        self.pulses = PulseService(self)
        self.temp_guard_ctrl = TempGuardController(self)
        self.physical_button = PhysicalButtonMonitor(self, self.gpio)
        self.main_window = MainWindow(self)
        self.video_loop = VideoLoop(self)

        # ---- hardware + UI bootstrap ----
        self.camera.connect()

        self.root = tk.Tk()
        self.root.title("Boson+ Radiometric Viewer")
        self.root.geometry("1280x800")

        self._init_variables()
        load_config(self)
        self.sync_runtime_caches()

        self.camera.apply_video_mode()
        self.camera.apply_frame_rate()

        try:
            self.pulses.sync_pulse_pins()
        except GpioError as e:
            print(f"WARNING: pulse pin setup: {e}")

        self.temp_guard_ctrl.reconfigure()
        self.sync_runtime_caches()

        try:
            self.physical_button.start()
        except GpioError as e:
            print(f"WARNING: physical button not started: {e}")

        self.main_window.build()

        # Keep button-action cache in sync when the combobox changes
        try:
            self.physical_button_action_var.trace_add(
                "write", lambda *_: self.sync_runtime_caches()
            )
        except Exception:
            pass

    # ------------------------------------------------------------------ vars
    def _init_variables(self):
        self.record_frames_var = tk.IntVar(value=DEFAULT_RECORD_FRAMES)
        self.show_overlay_var = tk.BooleanVar(value=False)
        self.roi_half_var = tk.IntVar(value=30)
        self.save_path_var = tk.StringVar(value=DEFAULT_SAVE_PATH)
        self.sync_capture_var = tk.BooleanVar(value=False)
        self.capture_delay_us_var = tk.IntVar(value=0)
        self.tlinear_enabled_var = tk.BooleanVar(value=False)
        self.physical_button_action_var = tk.StringVar(value="None")
        self.fpn_correction_enabled = tk.BooleanVar(value=False)
        self.frame_rate_var = tk.IntVar(value=self.camera.hardware_base_fps)
        self.fps_var = tk.StringVar(value="FPS: --")

        self.temp_guard_enabled_var = tk.BooleanVar(value=DEFAULT_TEMP_GUARD_ENABLED)
        self.temp_guard_sensor_var = tk.StringVar(value=DEFAULT_TEMP_GUARD_SENSOR)
        self.thermistor_i2c_bus_var = tk.IntVar(value=DEFAULT_THERMISTOR_I2C_BUS)
        self.thermistor_i2c_addr_var = tk.IntVar(value=DEFAULT_THERMISTOR_I2C_ADDR)
        self.thermistor_channel_var = tk.IntVar(value=DEFAULT_THERMISTOR_CHANNEL)
        self.thermistor_threshold_v_var = tk.DoubleVar(
            value=DEFAULT_THERMISTOR_THRESHOLD_V
        )
        self.ds18b20_id_var = tk.StringVar(value=DEFAULT_DS18B20_ID)
        self.ds18b20_threshold_c_var = tk.DoubleVar(value=DEFAULT_DS18B20_THRESHOLD_C)
        self.gpio_alarm_pin_var = tk.IntVar(value=DEFAULT_GPIO_ALARM_PIN)
        self.temp_guard_status_var = tk.StringVar(value="Temp Guard: off")

        self.pulse_channels = [
            {
                "enabled": tk.BooleanVar(value=False),
                "pin": tk.IntVar(value=DEFAULT_PULSE_PINS[0]),
                "on_time_us": tk.IntVar(value=1000),
                "off_time_us": tk.IntVar(value=1000),
                "pulses": tk.IntVar(value=1),
                "start_delay_us": tk.IntVar(value=0),
            },
            {
                "enabled": tk.BooleanVar(value=False),
                "pin": tk.IntVar(value=DEFAULT_PULSE_PINS[1]),
                "on_time_us": tk.IntVar(value=1000),
                "off_time_us": tk.IntVar(value=1000),
                "pulses": tk.IntVar(value=10),
                "start_delay_us": tk.IntVar(value=0),
            },
            {
                "enabled": tk.BooleanVar(value=False),
                "pin": tk.IntVar(value=DEFAULT_PULSE_PINS[2]),
                "on_time_us": tk.IntVar(value=1000),
                "off_time_us": tk.IntVar(value=1000),
                "pulses": tk.IntVar(value=1),
                "start_delay_us": tk.IntVar(value=0),
            },
            {
                "enabled": tk.BooleanVar(value=False),
                "pin": tk.IntVar(value=DEFAULT_PULSE_PINS[3]),
                "on_time_us": tk.IntVar(value=1000),
                "off_time_us": tk.IntVar(value=1000),
                "pulses": tk.IntVar(value=1),
                "start_delay_us": tk.IntVar(value=0),
            },
        ]

    def sync_runtime_caches(self):
        """
        Snapshot tk settings into RuntimeCache.

        Call from the Tk main thread only (after load_config, settings close,
        before starting record/pulse from UI).
        """
        self.runtime_cache.refresh_from_app(self)

    def dispatch_hardware_button(self, action: str):
        """
        Handle physical button actions on the Tk main thread only.
        Debounced: ignores edges while a previous action is still running.
        """
        with self._button_inflight_lock:
            if self._button_action_inflight:
                return
            self._button_action_inflight = True

        try:
            self.sync_runtime_caches()
            if action == "Trigger Pulse":
                self.pulses.trigger_pulse_button_action()
            elif action == "Record Stream":
                self.recording.record_stream()
            elif action == "Record Frame":
                self.recording.record_frame()
            elif action == "Record RAW":
                self.recording.record_raw_frame()
        finally:
            # Release debounce after a short delay so multi-second records
            # don't stack, but quick pulses aren't blocked forever.
            def _clear():
                with self._button_inflight_lock:
                    self._button_action_inflight = False

            try:
                self.root.after(400, _clear)
            except Exception:
                _clear()

    # -------- compatibility surface for settings.py / config_io.py --------
    @property
    def hardware_base_fps(self):
        return self.camera.hardware_base_fps

    @property
    def myCam(self):
        return self.camera.myCam

    # Phase 2: no public app.cap — use app.camera.read_frame() only.

    @property
    def temp_guard(self):
        return self.temp_guard_ctrl.temp_guard

    @property
    def is_recording(self):
        return self.recording.is_recording

    @property
    def background_frame(self):
        return self.recording.background_frame

    def available_frame_rates(self):
        return self.camera.available_frame_rates()

    def apply_video_mode(self):
        self.camera.apply_video_mode()

    def apply_frame_rate(self):
        self.camera.apply_frame_rate()

    def reconfigure_temp_guard(self):
        self.temp_guard_ctrl.reconfigure()
        self.sync_runtime_caches()

    def _refresh_temp_guard_status(self):
        self.temp_guard_ctrl.refresh_status()

    def open_settings(self):
        settings_ui.open_settings(self)

    def open_camera_settings(self):
        settings_ui.open_camera_settings(self)

    # -------------------------------------------------------------- lifecycle
    def on_closing(self):
        save_config(self)
        try:
            self.temp_guard_ctrl.close()
        except Exception:
            pass
        try:
            self.physical_button.close()
        except Exception:
            pass
        try:
            self.gpio.close()
        except Exception:
            pass
        try:
            self.camera.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.sync_runtime_caches()
        self.video_loop.start()
        self.temp_guard_ctrl.schedule_status()
        self.root.mainloop()


def main():
    app = BosonApp()
    app.run()


if __name__ == "__main__":
    main()
