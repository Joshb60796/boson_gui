"""
GPIO multi-channel pulse sequences.

Does not open a gpiochip. Pass a GpioService from gui.gpio_service so the
app owns a single chip handle (Phase 1).
"""

import threading
import time


def _pulse_channel(ch, gpio):
    pin = int(ch["pin"])
    on_time_us = ch["on_time_us"]
    off_time_us = ch.get("off_time_us", on_time_us)
    num_pulses = ch["pulses"]
    start_delay_us = ch["start_delay_us"]

    on_time_sec = on_time_us / 1_000_000.0
    off_time_sec = off_time_us / 1_000_000.0

    # Pin must already be registered as a PULSE output by the caller.
    gpio.write(pin, 0)

    if start_delay_us > 0:
        time.sleep(start_delay_us / 1_000_000.0)

    for i in range(num_pulses):
        gpio.write(pin, 1)
        time.sleep(on_time_sec)
        gpio.write(pin, 0)
        if num_pulses > 1 and i < num_pulses - 1:
            time.sleep(off_time_sec)

    gpio.write(pin, 0)
    print(f"Channel on pin {pin} finished ({num_pulses} pulses)")


def run_pulse_sequence(channels, gpio):
    """
    Run pulse channels in parallel.

    Parameters
    ----------
    channels : list[dict]
        Each dict: pin, on_time_us, off_time_us, pulses, start_delay_us
    gpio : GpioService
        Shared GPIO service (pins already claimed as outputs).
    """
    if not channels:
        return
    if gpio is None:
        raise RuntimeError("run_pulse_sequence requires a GpioService instance")

    print(f"Starting pulse sequence with {len(channels)} channel(s)...")

    threads = []
    for ch in channels:
        t = threading.Thread(
            target=_pulse_channel, args=(ch, gpio), daemon=True
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("All pulse sequences completed.")
