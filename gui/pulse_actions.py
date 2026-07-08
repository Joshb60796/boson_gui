"""GPIO pulse trigger actions (channel config → pulse_controller)."""

import threading

from pulse_controller import run_pulse_sequence

from gui.constants import (
    clamp_pulse_count,
    pulse_time_ms_to_us,
    start_delay_ms_to_us,
    us_to_pulse_time_ms,
    us_to_start_delay_ms,
)


class PulseService:
    """Builds clamped channel configs and fires pulse sequences."""

    def __init__(self, app):
        self.app = app

    def clamp_channel_timing(self, ch):
        """Enforce integer-ms pulse limits on a channel's tk variables."""
        on_us = pulse_time_ms_to_us(us_to_pulse_time_ms(ch["on_time_us"].get()))
        off_us = pulse_time_ms_to_us(us_to_pulse_time_ms(ch["off_time_us"].get()))
        pulses = clamp_pulse_count(ch["pulses"].get())
        delay_us = start_delay_ms_to_us(us_to_start_delay_ms(ch["start_delay_us"].get()))
        ch["on_time_us"].set(on_us)
        ch["off_time_us"].set(off_us)
        ch["pulses"].set(pulses)
        ch["start_delay_us"].set(delay_us)
        return on_us, off_us, pulses, delay_us

    def trigger_pulse(self):
        app = self.app
        if not app.temp_guard_ctrl.pulse_allowed(show_error=True):
            return False

        config = []
        for ch in app.pulse_channels:
            if ch["enabled"].get():
                on_us, off_us, pulses, delay_us = self.clamp_channel_timing(ch)
                config.append({
                    "pin": ch["pin"].get(),
                    "on_time_us": on_us,
                    "off_time_us": off_us,
                    "pulses": pulses,
                    "start_delay_us": delay_us,
                })
        if config:
            threading.Thread(
                target=run_pulse_sequence, args=(config,), daemon=True
            ).start()
        return True

    def trigger_pulse_button_action(self):
        app = self.app
        original_text = "Trigger Pulse"
        app.btn_trigger.config(text="Acquiring", state="disabled")

        def do_pulse():
            try:
                self.trigger_pulse()
            finally:
                app.root.after(
                    400,
                    lambda: app.btn_trigger.config(
                        text=original_text, state="normal"
                    ),
                )

        threading.Thread(target=do_pulse, daemon=True).start()
