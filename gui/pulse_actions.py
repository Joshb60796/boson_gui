"""
GPIO pulse trigger actions (channel config → pulse_controller).

Phase 3: worker threads use RuntimeCache snapshots only — no tk vars.
Widget updates go through ui_marshal.
"""

import threading

from pulse_controller import run_pulse_sequence

from gui.gpio_service import GpioError
from gui.ui_marshal import ui_call, ui_call_later


class PulseService:
    """Builds clamped channel configs and fires pulse sequences."""

    def __init__(self, app):
        self.app = app

    def sync_pulse_pins(self):
        """Claim configured channel pins as pulse outputs (main thread)."""
        app = self.app
        app.sync_runtime_caches()
        pins = app.runtime_cache.get_all_pulse_pins()
        if pins:
            app.gpio.ensure_pulse_pins(pins)

    def trigger_pulse(self):
        """
        Fire enabled pulse channels.

        Safe from worker threads: uses RuntimeCache for channel config and
        temp-guard parameters. Does not touch widgets.
        """
        app = self.app
        if not app.temp_guard_ctrl.pulse_allowed(show_error=True):
            return False

        config = app.runtime_cache.get_enabled_pulse_config()
        if not config:
            return True

        pins = [ch["pin"] for ch in config]
        try:
            app.gpio.ensure_pulse_pins(pins)
        except GpioError as e:
            print(f"Pulse pin claim failed: {e}")
            from tkinter import messagebox

            ui_call(app.root, lambda m=str(e): messagebox.showerror("GPIO", m))
            return False

        threading.Thread(
            target=run_pulse_sequence,
            args=(config, app.gpio),
            daemon=True,
            name="pulse-sequence",
        ).start()
        return True

    def trigger_pulse_button_action(self):
        """UI button handler — must run on main thread."""
        app = self.app
        app.sync_runtime_caches()

        original_text = "Trigger Pulse"
        if getattr(app, "btn_trigger", None) is not None:
            app.btn_trigger.config(text="Acquiring", state="disabled")

        def do_pulse():
            try:
                self.trigger_pulse()
            finally:
                ui_call_later(
                    app.root,
                    400,
                    lambda: app.btn_trigger.config(
                        text=original_text, state="normal"
                    )
                    if getattr(app, "btn_trigger", None) is not None
                    else None,
                )

        threading.Thread(target=do_pulse, daemon=True, name="pulse-btn").start()
