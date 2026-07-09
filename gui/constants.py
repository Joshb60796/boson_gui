"""Application-wide configuration constants."""

COM_PORT = "/dev/ttyACM0"
VIDEO_DEVICE_INDEX = 0
WIDTH = 640
HEIGHT = 512
DEFAULT_RECORD_FRAMES = 256
DEFAULT_SAVE_PATH = "data"
CONFIG_FILE = "config.json"
PHYSICAL_BUTTON_PIN = 17
# Common Boson+ rates; actual options depend on hardware base rate.
DEFAULT_FRAME_RATE = 60

# ---------------------------------------------------------------------------
# GPIO pulse limits (edit these to change allowed Settings range)
# Times are integer milliseconds only (no sub-ms). Applied to On/Off pulse
# widths. Start delay allows 0 ms (no delay) up to the same max.
# ---------------------------------------------------------------------------
MIN_PULSE_TIME_MS = 1  # smallest On/Off time the user may set
MAX_PULSE_TIME_MS = 2000  # 2 seconds — longest On/Off/start-delay allowed
MIN_PULSES = 1
MAX_PULSES = 100  # max pulses per channel per sequence
MIN_START_DELAY_MS = 0  # 0 = fire immediately after enable
MAX_START_DELAY_MS = MAX_PULSE_TIME_MS


def clamp_int(value, minimum, maximum, default=None):
    """Parse value to int and clamp into [minimum, maximum]."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        v = minimum if default is None else int(default)
    if v < minimum:
        return minimum
    if v > maximum:
        return maximum
    return v


def clamp_pulse_time_ms(value):
    """On/Off pulse width in ms → allowed integer ms."""
    return clamp_int(value, MIN_PULSE_TIME_MS, MAX_PULSE_TIME_MS, MIN_PULSE_TIME_MS)


def clamp_start_delay_ms(value):
    """Channel start delay in ms → allowed integer ms (0 permitted)."""
    return clamp_int(value, MIN_START_DELAY_MS, MAX_START_DELAY_MS, MIN_START_DELAY_MS)


def clamp_pulse_count(value):
    """Number of pulses → allowed integer count."""
    return clamp_int(value, MIN_PULSES, MAX_PULSES, MIN_PULSES)


def us_to_pulse_time_ms(us):
    """Convert stored microseconds to clamped On/Off ms (integer)."""
    try:
        return clamp_pulse_time_ms(int(round(float(us) / 1000.0)))
    except (TypeError, ValueError):
        return MIN_PULSE_TIME_MS


def us_to_start_delay_ms(us):
    """Convert stored microseconds to clamped start-delay ms (integer)."""
    try:
        return clamp_start_delay_ms(int(round(float(us) / 1000.0)))
    except (TypeError, ValueError):
        return MIN_START_DELAY_MS


def pulse_time_ms_to_us(ms):
    return clamp_pulse_time_ms(ms) * 1000


def start_delay_ms_to_us(ms):
    return clamp_start_delay_ms(ms) * 1000

# ---------------------------------------------------------------------------
# Temperature guard defaults (see gui/temp_guard.py for full install/wiring)
# ---------------------------------------------------------------------------
# Master switch: False → feature unused (no sensor traffic, pulses never
# blocked for temperature). User must check "Temp Guard" in Settings.
DEFAULT_TEMP_GUARD_ENABLED = False
# Which backend once enabled: "ds18b20" | "ads1115" | "gpio_alarm"
DEFAULT_TEMP_GUARD_SENSOR = "ds18b20"

# ADS1115 + thermistor divider — requires: I2C on, pip install smbus2
DEFAULT_THERMISTOR_I2C_BUS = 1  # Pi I2C bus (usually 1)
DEFAULT_THERMISTOR_I2C_ADDR = 0x48  # 72 decimal in Settings if ADDR→GND
DEFAULT_THERMISTOR_CHANNEL = 0  # AIN0..AIN3
DEFAULT_THERMISTOR_THRESHOLD_V = 2.5  # block pulses when voltage > this

# DS18B20 — requires: dtoverlay=w1-gpio, 4.7k pull-up; no pip package
DEFAULT_DS18B20_ID = ""  # empty = first 28-* sensor found under w1 devices
DEFAULT_DS18B20_THRESHOLD_C = 60.0  # UI clamps usable setpoints to 20–80 °C

# Arduino 3.3 V digital alarm (active HIGH = TEMP HIGH). BCM pin choice avoids:
#   2/3 I2C, 4 common 1-Wire, 14/15 UART, 17 physical button,
#   22/23/24/27 default pulse channels.
DEFAULT_GPIO_ALARM_PIN = 16  # BCM16 — change here or in Settings
