"""
Temp Guard UI / interlock controller.

Sensor backends and wiring notes: gui/temp_guard/SETUP.md

Phase 3: pulse/acquisition checks use RuntimeCache (safe off UI thread).
Widget updates and messageboxes always go through ui_marshal.
"""

import time

from tkinter import messagebox

from gui.temp_guard import SENSOR_DS18B20, SENSOR_GPIO_ALARM, TempGuard
from gui.ui_marshal import on_ui_thread, ui_call


class TempGuardController:
    """Wraps TempGuard with app tk-vars, status label, and pulse/acq gates."""

    def __init__(self, app):
        self.app = app
        gpio = getattr(app, "gpio", None)
        self.guard = TempGuard(gpio=gpio)
        self._last_alert = 0.0

    @property
    def temp_guard(self):
        """Alias used by settings UI (app.temp_guard)."""
        return self.guard

    def reconfigure(self):
        """Call from main thread only (reads tk vars)."""
        app = self.app
        gpio = getattr(app, "gpio", None)
        if self.guard is None:
            self.guard = TempGuard(gpio=gpio)
        self.guard.configure(
            sensor_type=app.temp_guard_sensor_var.get(),
            i2c_bus=app.thermistor_i2c_bus_var.get(),
            i2c_address=app.thermistor_i2c_addr_var.get(),
            channel=app.thermistor_channel_var.get(),
            ds18b20_id=app.ds18b20_id_var.get(),
            gpio_alarm_pin=app.gpio_alarm_pin_var.get(),
            gpio=gpio,
        )
        self.refresh_status()

    def refresh_status(self):
        """Update status label — must run on Tk main thread."""
        app = self.app
        if not on_ui_thread(app.root):
            ui_call(app.root, self.refresh_status)
            return

        label = getattr(app, "temp_guard_status_label", None)

        def set_color(color):
            if label is not None:
                label.config(fg=color)

        if not app.temp_guard_enabled_var.get():
            app.temp_guard_status_var.set("Temp Guard: off")
            set_color("#666666")
            return
        if self.guard is None:
            app.temp_guard_status_var.set("Temp Guard: not init")
            set_color("#cc6600")
            return

        sensor = app.temp_guard_sensor_var.get()
        value, _unit = self.guard.read_current(sensor)
        if value is None:
            app.temp_guard_status_var.set("Temp Guard: READ FAIL")
            set_color("#cc0000")
            return

        if sensor == SENSOR_GPIO_ALARM:
            over = int(value) != 0
            text = "TEMP HIGH" if over else "Temp OK (alarm LOW)"
        elif sensor == SENSOR_DS18B20:
            limit = app.ds18b20_threshold_c_var.get()
            over = value > limit
            text = f"{'OVER TEMP' if over else 'Temp OK'}: {value:.1f}°C"
        else:
            limit = app.thermistor_threshold_v_var.get()
            over = value > limit
            text = f"{'OVER TEMP' if over else 'Temp OK'}: {value:.2f}V"

        app.temp_guard_status_var.set(text)
        set_color("#cc0000" if over else "#007700")

    def _show_error(self, message):
        app = self.app
        now = time.time()
        if now - self._last_alert > 2.0:
            self._last_alert = now
            ui_call(
                app.root,
                lambda m=message: messagebox.showerror("Temp Guard", m),
            )

    def pulse_allowed(self, show_error=True):
        """
        Safe from any thread: uses RuntimeCache for settings, hardware for sensor.
        UI updates are marshaled to the main thread.
        """
        app = self.app
        params = app.runtime_cache.get_temp_guard_params()
        if self.guard is None or not params["enabled"]:
            return True

        allowed, message, _reading = self.guard.check_allows_pulse(
            enabled=True,
            sensor_type=params["sensor"],
            threshold_v=params["threshold_v"],
            threshold_c=params["threshold_c"],
        )
        ui_call(app.root, self.refresh_status)

        if allowed:
            return True

        print(message or "Pulse blocked by temp guard")
        if show_error and message:
            self._show_error(message)
        return False

    def acquisition_allowed(self, show_error=True):
        """
        Frame acquisition blocked while Temp Guard is enabled.
        Safe from any thread (uses cache).
        """
        app = self.app
        if not app.runtime_cache.get_temp_guard_params()["enabled"]:
            return True
        msg = (
            "Frame acquisition is disabled while Temp Guard is enabled.\n"
            "Turn off Temp Guard in Settings to record frames/streams."
        )
        print(msg)
        if show_error:
            self._show_error(msg)
        return False

    def schedule_status(self):
        """Periodic main-UI status refresh."""
        app = self.app
        try:
            if app.temp_guard_enabled_var.get():
                self.refresh_status()
            else:
                app.temp_guard_status_var.set("Temp Guard: off")
                label = getattr(app, "temp_guard_status_label", None)
                if label is not None:
                    label.config(fg="#666666")
        except Exception:
            pass
        try:
            app.root.after(1000, self.schedule_status)
        except Exception:
            pass

    def close(self):
        if self.guard is not None:
            self.guard.close()
