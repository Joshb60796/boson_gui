"""Physical GPIO button monitor (edge-triggered actions)."""

import threading
import time

from gui.constants import PHYSICAL_BUTTON_PIN
from gui.gpio_service import PinRole


class PhysicalButtonMonitor:
    """Polls a GPIO pin via GpioService and dispatches configured app actions."""

    def __init__(self, app, gpio, pin=PHYSICAL_BUTTON_PIN):
        self.app = app
        self.gpio = gpio
        self.pin = int(pin)
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        self.gpio.register_input(self.pin, PinRole.BUTTON, pull_down=False)
        self._stop.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self):
        app = self.app
        last_state = 1
        while not self._stop.is_set():
            try:
                state = self.gpio.read(self.pin)
            except Exception as e:
                print(f"Physical button read error: {e}")
                time.sleep(0.5)
                continue

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
        self._stop.set()
        # Pin freed when GpioService closes; optional explicit free:
        try:
            self.gpio.unregister(self.pin)
        except Exception:
            pass
