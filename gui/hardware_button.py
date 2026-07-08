"""Physical GPIO button monitor (edge-triggered actions)."""

import threading
import time

import lgpio

from gui.constants import PHYSICAL_BUTTON_PIN


class PhysicalButtonMonitor:
    """Polls a GPIO pin and dispatches configured app actions."""

    def __init__(self, app, pin=PHYSICAL_BUTTON_PIN):
        self.app = app
        self.pin = pin
        self.button_h = None
        self._thread = None

    def start(self):
        self.button_h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_input(self.button_h, self.pin, lgpio.SET_PULL_UP)
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self):
        app = self.app
        last_state = 1
        while True:
            state = lgpio.gpio_read(self.button_h, self.pin)
            if state == 0 and last_state == 1:
                action = app.physical_button_action_var.get()
                if action == "Trigger Pulse":
                    app.pulses.trigger_pulse()
                elif action == "Record Stream":
                    app.recording.record_stream()
                elif action == "Record Frame":
                    app.recording.record_frame()
                elif action == "Record RAW":
                    app.recording.record_raw_frame()
                time.sleep(0.2)
            last_state = state
            time.sleep(0.05)

    def close(self):
        if self.button_h is not None:
            try:
                lgpio.gpiochip_close(self.button_h)
            except Exception:
                pass
            self.button_h = None
