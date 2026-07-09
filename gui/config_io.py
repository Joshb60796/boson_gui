"""Load and save application settings from JSON."""

import json

from gui.constants import (
    CONFIG_FILE,
    DEFAULT_DS18B20_ID,
    DEFAULT_DS18B20_THRESHOLD_C,
    DEFAULT_FRAME_RATE,
    DEFAULT_GPIO_ALARM_PIN,
    DEFAULT_RECORD_FRAMES,
    DEFAULT_SAVE_PATH,
    DEFAULT_TEMP_GUARD_ENABLED,
    DEFAULT_TEMP_GUARD_SENSOR,
    DEFAULT_THERMISTOR_CHANNEL,
    DEFAULT_THERMISTOR_I2C_ADDR,
    DEFAULT_THERMISTOR_I2C_BUS,
    DEFAULT_THERMISTOR_THRESHOLD_V,
    clamp_pulse_count,
    pulse_time_ms_to_us,
    start_delay_ms_to_us,
    us_to_pulse_time_ms,
    us_to_start_delay_ms,
)
from gui.temp_guard import SENSOR_ADS1115, SENSOR_CHOICES


def load_config(app):
    """Load config.json into an app instance's tk variables."""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        app.record_frames_var.set(int(config.get("record_frames", DEFAULT_RECORD_FRAMES)))
        app.save_path_var.set(str(config.get("save_path", DEFAULT_SAVE_PATH)))
        app.sync_capture_var.set(bool(config.get("sync_capture", False)))
        app.capture_delay_us_var.set(int(config.get("capture_delay_us", 0)))
        app.tlinear_enabled_var.set(bool(config.get("tlinear_enabled", False)))
        app.physical_button_action_var.set(config.get("physical_button_action", "None"))
        app.fpn_correction_enabled.set(bool(config.get("fpn_correction_enabled", False)))

        # Temp guard keys (see gui/temp_guard.py for hardware setup):
        #   temp_guard_enabled, temp_guard_sensor (ads1115|ds18b20|gpio_alarm),
        #   thermistor_*, ds18b20_*, gpio_alarm_pin
        # Prefer new keys; migrate legacy thermistor_enabled if present.
        if "temp_guard_enabled" in config:
            enabled = bool(config["temp_guard_enabled"])
        else:
            enabled = bool(config.get("thermistor_enabled", DEFAULT_TEMP_GUARD_ENABLED))
        app.temp_guard_enabled_var.set(enabled)

        sensor = str(config.get("temp_guard_sensor", DEFAULT_TEMP_GUARD_SENSOR)).lower()
        if sensor not in SENSOR_CHOICES:
            # Old configs only had ADS1115 path
            sensor = SENSOR_ADS1115 if config.get("thermistor_enabled") else DEFAULT_TEMP_GUARD_SENSOR
        if sensor not in SENSOR_CHOICES:
            sensor = DEFAULT_TEMP_GUARD_SENSOR
        app.temp_guard_sensor_var.set(sensor)

        app.thermistor_i2c_bus_var.set(
            int(config.get("thermistor_i2c_bus", DEFAULT_THERMISTOR_I2C_BUS))
        )
        app.thermistor_i2c_addr_var.set(
            int(config.get("thermistor_i2c_addr", DEFAULT_THERMISTOR_I2C_ADDR))
        )
        app.thermistor_channel_var.set(
            int(config.get("thermistor_channel", DEFAULT_THERMISTOR_CHANNEL))
        )
        app.thermistor_threshold_v_var.set(
            float(config.get("thermistor_threshold_v", DEFAULT_THERMISTOR_THRESHOLD_V))
        )
        app.ds18b20_id_var.set(str(config.get("ds18b20_id", DEFAULT_DS18B20_ID)))
        app.ds18b20_threshold_c_var.set(
            float(config.get("ds18b20_threshold_c", DEFAULT_DS18B20_THRESHOLD_C))
        )
        app.gpio_alarm_pin_var.set(
            int(config.get("gpio_alarm_pin", DEFAULT_GPIO_ALARM_PIN))
        )

        default_fps = getattr(app, "hardware_base_fps", DEFAULT_FRAME_RATE)
        frame_rate = int(config.get("frame_rate", default_fps))
        available = app.available_frame_rates()
        if frame_rate not in available and available:
            frame_rate = available[0]
        app.frame_rate_var.set(frame_rate)

        saved_channels = config.get("pulse_channels", [])
        for i, ch in enumerate(app.pulse_channels):
            if i < len(saved_channels):
                saved = saved_channels[i]
                ch["enabled"].set(bool(saved.get("enabled", False)))
                ch["pin"].set(int(saved.get("pin", 17)))
                # Times stored as µs; enforce integer-ms limits on load
                on_us = pulse_time_ms_to_us(us_to_pulse_time_ms(saved.get("on_time_us", 1000)))
                off_us = pulse_time_ms_to_us(
                    us_to_pulse_time_ms(saved.get("off_time_us", on_us))
                )
                ch["on_time_us"].set(on_us)
                ch["off_time_us"].set(off_us)
                ch["pulses"].set(clamp_pulse_count(saved.get("pulses", 1)))
                ch["start_delay_us"].set(
                    start_delay_ms_to_us(
                        us_to_start_delay_ms(saved.get("start_delay_us", 0))
                    )
                )

    except Exception:
        pass


def save_config(app):
    """Persist an app instance's settings to config.json."""
    sensor = app.temp_guard_sensor_var.get()
    if sensor not in SENSOR_CHOICES:
        sensor = DEFAULT_TEMP_GUARD_SENSOR

    config = {
        "record_frames": app.record_frames_var.get(),
        "save_path": app.save_path_var.get(),
        "sync_capture": app.sync_capture_var.get(),
        "capture_delay_us": app.capture_delay_us_var.get(),
        "tlinear_enabled": app.tlinear_enabled_var.get(),
        "physical_button_action": app.physical_button_action_var.get(),
        "fpn_correction_enabled": app.fpn_correction_enabled.get(),
        "frame_rate": app.frame_rate_var.get(),
        "temp_guard_enabled": app.temp_guard_enabled_var.get(),
        "temp_guard_sensor": sensor,
        "thermistor_i2c_bus": app.thermistor_i2c_bus_var.get(),
        "thermistor_i2c_addr": app.thermistor_i2c_addr_var.get(),
        "thermistor_channel": app.thermistor_channel_var.get(),
        "thermistor_threshold_v": app.thermistor_threshold_v_var.get(),
        "ds18b20_id": app.ds18b20_id_var.get(),
        "ds18b20_threshold_c": app.ds18b20_threshold_c_var.get(),
        "gpio_alarm_pin": app.gpio_alarm_pin_var.get(),
        "pulse_channels": [],
    }

    for ch in app.pulse_channels:
        # Re-clamp before write so config.json never stores out-of-range values
        on_us = pulse_time_ms_to_us(us_to_pulse_time_ms(ch["on_time_us"].get()))
        off_us = pulse_time_ms_to_us(us_to_pulse_time_ms(ch["off_time_us"].get()))
        pulses = clamp_pulse_count(ch["pulses"].get())
        delay_us = start_delay_ms_to_us(us_to_start_delay_ms(ch["start_delay_us"].get()))
        ch["on_time_us"].set(on_us)
        ch["off_time_us"].set(off_us)
        ch["pulses"].set(pulses)
        ch["start_delay_us"].set(delay_us)
        config["pulse_channels"].append({
            "enabled": ch["enabled"].get(),
            "pin": ch["pin"].get(),
            "on_time_us": on_us,
            "off_time_us": off_us,
            "pulses": pulses,
            "start_delay_us": delay_us,
        })

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
