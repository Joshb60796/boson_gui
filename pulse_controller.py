import lgpio
import time
import threading

h = lgpio.gpiochip_open(0)


def _pulse_channel(ch):
    pin = ch["pin"]
    on_time_us = ch["on_time_us"]
    # Default off time to on time when not provided (backward compatible)
    off_time_us = ch.get("off_time_us", on_time_us)
    num_pulses = ch["pulses"]
    start_delay_us = ch["start_delay_us"]

    on_time_sec = on_time_us / 1_000_000.0
    off_time_sec = off_time_us / 1_000_000.0

    lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_write(h, pin, 0)  # Start LOW

    if start_delay_us > 0:
        time.sleep(start_delay_us / 1_000_000.0)

    for i in range(num_pulses):
        lgpio.gpio_write(h, pin, 1)  # ON
        time.sleep(on_time_sec)
        lgpio.gpio_write(h, pin, 0)  # OFF
        # Off interval only matters between pulses
        if num_pulses > 1 and i < num_pulses - 1:
            time.sleep(off_time_sec)

    lgpio.gpio_write(h, pin, 0)  # Final state = LOW
    print(f"Channel on pin {pin} finished ({num_pulses} pulses)")


def run_pulse_sequence(channels):
    if not channels:
        return

    print(f"Starting pulse sequence with {len(channels)} channel(s)...")

    threads = []
    for ch in channels:
        t = threading.Thread(target=_pulse_channel, args=(ch,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("All pulse sequences completed.")
