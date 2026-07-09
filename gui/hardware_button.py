"""
Physical GPIO button monitor (edge-triggered).

Phase 3: this thread only reads GPIO. All app/UI work is scheduled on the
Tk main thread via root.after — never touches tk vars or widgets here.
"""

import threading
import time

from gui.constants import PHYSICAL_BUTTON_PIN
from gui.gpio_service import PinRole
from gui.ui_marshal import ui_call


class PhysicalButtonMonitor:
    """Polls a GPIO pin via GpioService; dispatches actions on the UI thread."""

    def __init__(self, app, gpio, pin=PHYSICAL_BUTTON_PIN):
        self.app = app
        self.gpio = gpio
        self.pin = int(pin)
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        self.gpio.register_input(self.pin, PinRole.BUTTON, pull_down=False)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop, name="physical-button", daemon=True
        )
        self._thread.start()

    def _monitor_loop(self):
        last_state = 1
        while not self._stop.is_set():
            try:
                state = self.gpio.read(self.pin)
            except Exception as e:
                print(f"Physical button read error: {e}")
                time.sleep(0.5)
                continue

            # Active-low press edge
            if state == 0 and last_state == 1:
                # Plain string from RuntimeCache — never read tk vars here
                action = self.app.runtime_cache.get_button_action()
                if action and action != "None":
                    # Capture action in default arg to avoid late binding
                    ui_call(
                        self.app.root,
                        lambda a=action: self.app.dispatch_hardware_button(a),
                    )
                time.sleep(0.2)  # debounce
            last_state = state
            time.sleep(0.05)

    def close(self):
        self._stop.set()
        try:
            self.gpio.unregister(self.pin)
        except Exception:
            pass
