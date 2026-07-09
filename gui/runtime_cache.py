"""
Plain-Python snapshots of settings for worker threads (Phase 3).

Tk variables must only be read on the main thread. Workers use this cache
for pulses, temp-guard checks, and recording paths.
"""

from __future__ import annotations

import threading

from gui.constants import (
    clamp_pulse_count,
    pulse_time_ms_to_us,
    start_delay_ms_to_us,
    us_to_pulse_time_ms,
    us_to_start_delay_ms,
)


class RuntimeCache:
    def __init__(self):
        self._lock = threading.RLock()
        self.button_action = "None"
        self.temp_guard_enabled = False
        self.temp_guard_sensor = "ds18b20"
        self.thermistor_threshold_v = 2.5
        self.ds18b20_threshold_c = 60.0
        self.fpn_enabled = False
        self.save_path = "data"
        self.record_frames = 256
        self.sync_capture = False
        self.capture_delay_us = 0
        # List of channel dicts with plain Python values
        self.pulse_channels = []

    def refresh_from_app(self, app) -> None:
        """
        Read settings — call only from the Tk main thread.

        Prefers AppSettings.capture_from_app when available (Phase 4);
        falls back to reading tk vars directly.
        """
        try:
            from gui.settings_model import AppSettings

            s = AppSettings.capture_from_app(app)
            self.refresh_from_settings(s, button_action=str(app.physical_button_action_var.get()))
            return
        except Exception:
            pass

        channels = []
        for ch in app.pulse_channels:
            on_us = pulse_time_ms_to_us(us_to_pulse_time_ms(ch["on_time_us"].get()))
            off_us = pulse_time_ms_to_us(us_to_pulse_time_ms(ch["off_time_us"].get()))
            pulses = clamp_pulse_count(ch["pulses"].get())
            delay_us = start_delay_ms_to_us(
                us_to_start_delay_ms(ch["start_delay_us"].get())
            )
            try:
                pin = int(ch["pin"].get())
            except (TypeError, ValueError):
                pin = 0
            channels.append({
                "enabled": bool(ch["enabled"].get()),
                "pin": pin,
                "on_time_us": on_us,
                "off_time_us": off_us,
                "pulses": pulses,
                "start_delay_us": delay_us,
            })

        with self._lock:
            self.button_action = str(app.physical_button_action_var.get())
            self.temp_guard_enabled = bool(app.temp_guard_enabled_var.get())
            self.temp_guard_sensor = str(app.temp_guard_sensor_var.get())
            self.thermistor_threshold_v = float(app.thermistor_threshold_v_var.get())
            self.ds18b20_threshold_c = float(app.ds18b20_threshold_c_var.get())
            self.fpn_enabled = bool(app.fpn_correction_enabled.get())
            self.save_path = str(app.save_path_var.get())
            self.record_frames = int(app.record_frames_var.get())
            self.sync_capture = bool(app.sync_capture_var.get())
            self.capture_delay_us = int(app.capture_delay_us_var.get())
            self.pulse_channels = channels

    def refresh_from_settings(self, settings, button_action: str | None = None) -> None:
        """Populate cache from an AppSettings instance (no Tk required)."""
        channels = []
        for ch in settings.pulse_channels:
            channels.append({
                "enabled": bool(ch.enabled),
                "pin": int(ch.pin),
                "on_time_us": int(ch.on_time_us),
                "off_time_us": int(ch.off_time_us),
                "pulses": int(ch.pulses),
                "start_delay_us": int(ch.start_delay_us),
            })
        with self._lock:
            self.button_action = str(
                button_action
                if button_action is not None
                else settings.physical_button_action
            )
            self.temp_guard_enabled = bool(settings.temp_guard_enabled)
            self.temp_guard_sensor = str(settings.temp_guard_sensor)
            self.thermistor_threshold_v = float(settings.thermistor_threshold_v)
            self.ds18b20_threshold_c = float(settings.ds18b20_threshold_c)
            self.fpn_enabled = bool(settings.fpn_correction_enabled)
            self.save_path = str(settings.save_path)
            self.record_frames = int(settings.record_frames)
            self.sync_capture = bool(settings.sync_capture)
            self.capture_delay_us = int(settings.capture_delay_us)
            self.pulse_channels = channels

    def get_button_action(self) -> str:
        with self._lock:
            return self.button_action

    def get_temp_guard_params(self) -> dict:
        with self._lock:
            return {
                "enabled": self.temp_guard_enabled,
                "sensor": self.temp_guard_sensor,
                "threshold_v": self.thermistor_threshold_v,
                "threshold_c": self.ds18b20_threshold_c,
            }

    def get_enabled_pulse_config(self) -> list:
        """Channel dicts ready for run_pulse_sequence (enabled only)."""
        with self._lock:
            out = []
            for ch in self.pulse_channels:
                if ch["enabled"]:
                    out.append({
                        "pin": ch["pin"],
                        "on_time_us": ch["on_time_us"],
                        "off_time_us": ch["off_time_us"],
                        "pulses": ch["pulses"],
                        "start_delay_us": ch["start_delay_us"],
                    })
            return out

    def get_all_pulse_pins(self) -> list:
        with self._lock:
            return [ch["pin"] for ch in self.pulse_channels]

    def snapshot_recording(self) -> dict:
        with self._lock:
            return {
                "fpn_enabled": self.fpn_enabled,
                "save_path": self.save_path,
                "record_frames": self.record_frames,
                "sync_capture": self.sync_capture,
                "capture_delay_us": self.capture_delay_us,
            }
