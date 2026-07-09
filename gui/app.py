"""
Boson+ radiometric viewer — application orchestrator.

Collaborators (do the real work):
  gui/camera.py               — Boson SDK + V4L2
  gui/recording.py            — frame/stream/background capture
  gui/pulse_actions.py        — GPIO pulse trigger
  gui/hardware_button.py      — physical button monitor
  gui/temp_guard_controller.py — temp interlock + status
  gui/main_window.py          — main UI layout
  gui/video_loop.py           — live display
  gui/settings.py             — settings dialogs
  gui/config_io.py            — config.json load/save
"""

import tkinter as tk

from gui import settings as settings_ui
from gui.camera import CameraService
from gui.config_io import load_config, save_config
from gui.constants import (
    DEFAULT_DS18B20_ID,
    DEFAULT_DS18B20_THRESHOLD_C,
    DEFAULT_GPIO_ALARM_PIN,
    DEFAULT_RECORD_FRAMES,
    DEFAULT_SAVE_PATH,
    DEFAULT_TEMP_GUARD_ENABLED,
    DEFAULT_TEMP_GUARD_SENSOR,
    DEFAULT_THERMISTOR_CHANNEL,
    DEFAULT_THERMISTOR_I2C_ADDR,
    DEFAULT_THERMISTOR_I2C_BUS,
    DEFAULT_THERMISTOR_THRESHOLD_V,
)
from gui.hardware_button import PhysicalButtonMonitor
from gui.main_window import MainWindow
from gui.pulse_actions import PulseService
from gui.recording import RecordingService
from gui.temp_guard_controller import TempGuardController
from gui.video_loop import VideoLoop


class BosonApp:
    """
    Thin orchestrator: owns tk root/vars and wires collaborator services.

    Settings and config_io still receive this object so they can read/write
    tk variables and call a few delegated methods (apply_video_mode, etc.).
    """

    def __init__(self):
        # ---- collaborators (created early; some need vars after init) ----
        self.camera = CameraService(self)
        self.recording = RecordingService(self)
        self.pulses = PulseService(self)
        self.temp_guard_ctrl = TempGuardController(self)
        self.physical_button = PhysicalButtonMonitor(self)
        self.main_window = MainWindow(self)
        self.video_loop = VideoLoop(self)

        # ---- hardware + UI bootstrap ----
        self.camera.connect()

        self.root = tk.Tk()
        self.root.title("Boson+ Radiometric Viewer")
        self.root.geometry("1280x800")

        self._init_variables()
        load_config(self)

        self.camera.apply_video_mode()
        self.camera.apply_frame_rate()
        self.temp_guard_ctrl.reconfigure()
        self.physical_button.start()
        self.main_window.build()

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

        # Times as µs (always integer ms * 1000 after clamp). Limits in constants.
        self.pulse_channels = [
            {
                "enabled": tk.BooleanVar(value=False),
                "pin": tk.IntVar(value=24),
                "on_time_us": tk.IntVar(value=1000),
                "off_time_us": tk.IntVar(value=1000),
                "pulses": tk.IntVar(value=1),
                "start_delay_us": tk.IntVar(value=0),
            },
            {
                "enabled": tk.BooleanVar(value=False),
                "pin": tk.IntVar(value=27),
                "on_time_us": tk.IntVar(value=1000),
                "off_time_us": tk.IntVar(value=1000),
                "pulses": tk.IntVar(value=10),
                "start_delay_us": tk.IntVar(value=0),
            },
            {
                "enabled": tk.BooleanVar(value=False),
                "pin": tk.IntVar(value=22),
                "on_time_us": tk.IntVar(value=1000),
                "off_time_us": tk.IntVar(value=1000),
                "pulses": tk.IntVar(value=1),
                "start_delay_us": tk.IntVar(value=0),
            },
            {
                "enabled": tk.BooleanVar(value=False),
                "pin": tk.IntVar(value=23),
                "on_time_us": tk.IntVar(value=1000),
                "off_time_us": tk.IntVar(value=1000),
                "pulses": tk.IntVar(value=1),
                "start_delay_us": tk.IntVar(value=0),
            },
        ]

    # -------- compatibility surface for settings.py / config_io.py --------
    @property
    def hardware_base_fps(self):
        return self.camera.hardware_base_fps

    @property
    def myCam(self):
        return self.camera.myCam

    @property
    def cap(self):
        return self.camera.cap

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

    def _refresh_temp_guard_status(self):
        self.temp_guard_ctrl.refresh_status()

    def open_settings(self):
        settings_ui.open_settings(self)

    def open_camera_settings(self):
        settings_ui.open_camera_settings(self)

    # -------------------------------------------------------------- lifecycle
    def on_closing(self):
        save_config(self)
        self.temp_guard_ctrl.close()
        self.physical_button.close()
        self.camera.close()
        self.root.destroy()

    def run(self):
        self.video_loop.start()
        self.temp_guard_ctrl.schedule_status()
        self.root.mainloop()


def main():
    app = BosonApp()
    app.run()


if __name__ == "__main__":
    main()
