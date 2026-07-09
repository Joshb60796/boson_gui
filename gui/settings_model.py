"""
Versioned application settings model (Phase 4).

Plain dataclasses own the config schema. Tk variables are only a UI binding
layer via apply_to_app() / capture_from_app(). JSON load/save goes through
this module (see config_io.py).

Schema version history:
  1 — initial versioned schema (migrates pre-version config.json keys)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from gui.constants import (
    CONFIG_FILE,
    DEFAULT_DS18B20_ID,
    DEFAULT_DS18B20_THRESHOLD_C,
    DEFAULT_FRAME_RATE,
    DEFAULT_GPIO_ALARM_PIN,
    DEFAULT_PULSE_PINS,
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

# Bump when making breaking config.json changes and add a migrator below.
CONFIG_SCHEMA_VERSION = 1


@dataclass
class PulseChannelSettings:
    enabled: bool = False
    pin: int = 24
    on_time_us: int = 1000
    off_time_us: int = 1000
    pulses: int = 1
    start_delay_us: int = 0

    def clamp(self) -> "PulseChannelSettings":
        on_us = pulse_time_ms_to_us(us_to_pulse_time_ms(self.on_time_us))
        off_us = pulse_time_ms_to_us(us_to_pulse_time_ms(self.off_time_us))
        return PulseChannelSettings(
            enabled=bool(self.enabled),
            pin=int(self.pin),
            on_time_us=on_us,
            off_time_us=off_us,
            pulses=clamp_pulse_count(self.pulses),
            start_delay_us=start_delay_ms_to_us(
                us_to_start_delay_ms(self.start_delay_us)
            ),
        )

    @classmethod
    def from_dict(cls, d: dict, default_pin: int = 24) -> "PulseChannelSettings":
        on_us = int(d.get("on_time_us", 1000))
        return cls(
            enabled=bool(d.get("enabled", False)),
            pin=int(d.get("pin", default_pin)),
            on_time_us=on_us,
            off_time_us=int(d.get("off_time_us", on_us)),
            pulses=int(d.get("pulses", 1)),
            start_delay_us=int(d.get("start_delay_us", 0)),
        ).clamp()


def _default_pulse_channels() -> List[PulseChannelSettings]:
    defaults = [
        PulseChannelSettings(enabled=False, pin=DEFAULT_PULSE_PINS[0], pulses=1),
        PulseChannelSettings(enabled=False, pin=DEFAULT_PULSE_PINS[1], pulses=10),
        PulseChannelSettings(enabled=False, pin=DEFAULT_PULSE_PINS[2], pulses=1),
        PulseChannelSettings(enabled=False, pin=DEFAULT_PULSE_PINS[3], pulses=1),
    ]
    return [c.clamp() for c in defaults]


@dataclass
class AppSettings:
    """Canonical application settings (JSON + validation)."""

    schema_version: int = CONFIG_SCHEMA_VERSION

    record_frames: int = DEFAULT_RECORD_FRAMES
    save_path: str = DEFAULT_SAVE_PATH
    sync_capture: bool = False
    capture_delay_us: int = 0
    tlinear_enabled: bool = False
    physical_button_action: str = "None"
    fpn_correction_enabled: bool = False
    frame_rate: int = DEFAULT_FRAME_RATE

    temp_guard_enabled: bool = DEFAULT_TEMP_GUARD_ENABLED
    temp_guard_sensor: str = DEFAULT_TEMP_GUARD_SENSOR
    thermistor_i2c_bus: int = DEFAULT_THERMISTOR_I2C_BUS
    thermistor_i2c_addr: int = DEFAULT_THERMISTOR_I2C_ADDR
    thermistor_channel: int = DEFAULT_THERMISTOR_CHANNEL
    thermistor_threshold_v: float = DEFAULT_THERMISTOR_THRESHOLD_V
    ds18b20_id: str = DEFAULT_DS18B20_ID
    ds18b20_threshold_c: float = DEFAULT_DS18B20_THRESHOLD_C
    gpio_alarm_pin: int = DEFAULT_GPIO_ALARM_PIN

    pulse_channels: List[PulseChannelSettings] = field(
        default_factory=_default_pulse_channels
    )

    # ------------------------------------------------------------------ clamp
    def clamp(self) -> "AppSettings":
        sensor = str(self.temp_guard_sensor).lower()
        if sensor not in SENSOR_CHOICES:
            sensor = DEFAULT_TEMP_GUARD_SENSOR

        channels = list(self.pulse_channels) if self.pulse_channels else []
        while len(channels) < 4:
            idx = len(channels)
            pin = DEFAULT_PULSE_PINS[idx] if idx < len(DEFAULT_PULSE_PINS) else 24
            channels.append(PulseChannelSettings(pin=pin))
        channels = [c.clamp() for c in channels[:4]]

        try:
            t_c = float(self.ds18b20_threshold_c)
        except (TypeError, ValueError):
            t_c = DEFAULT_DS18B20_THRESHOLD_C
        t_c = max(20.0, min(80.0, t_c))

        try:
            frames = int(self.record_frames)
        except (TypeError, ValueError):
            frames = DEFAULT_RECORD_FRAMES
        frames = max(1, frames)

        return AppSettings(
            schema_version=CONFIG_SCHEMA_VERSION,
            record_frames=frames,
            save_path=str(self.save_path or DEFAULT_SAVE_PATH),
            sync_capture=bool(self.sync_capture),
            capture_delay_us=int(self.capture_delay_us or 0),
            tlinear_enabled=bool(self.tlinear_enabled),
            physical_button_action=str(self.physical_button_action or "None"),
            fpn_correction_enabled=bool(self.fpn_correction_enabled),
            frame_rate=int(self.frame_rate or DEFAULT_FRAME_RATE),
            temp_guard_enabled=bool(self.temp_guard_enabled),
            temp_guard_sensor=sensor,
            thermistor_i2c_bus=int(self.thermistor_i2c_bus),
            thermistor_i2c_addr=int(self.thermistor_i2c_addr),
            thermistor_channel=int(self.thermistor_channel) % 4,
            thermistor_threshold_v=float(self.thermistor_threshold_v),
            ds18b20_id=str(self.ds18b20_id or ""),
            ds18b20_threshold_c=t_c,
            gpio_alarm_pin=int(self.gpio_alarm_pin),
            pulse_channels=channels,
        )

    def constrain_frame_rate(self, available: Optional[List[int]]) -> "AppSettings":
        """Keep frame_rate in the camera's available list when known."""
        s = self.clamp()
        if available:
            if s.frame_rate not in available:
                s.frame_rate = available[0]
        return s

    # --------------------------------------------------------------- serialize
    def to_dict(self) -> dict:
        s = self.clamp()
        d = asdict(s)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        """Parse dict (any schema generation) and migrate to current version."""
        if not isinstance(data, dict):
            return cls()

        data = dict(data)
        version = int(data.get("schema_version", 0) or 0)
        data = _migrate(data, version)

        channels_raw = data.get("pulse_channels") or []
        channels: List[PulseChannelSettings] = []
        for i in range(4):
            default_pin = DEFAULT_PULSE_PINS[i] if i < len(DEFAULT_PULSE_PINS) else 24
            if i < len(channels_raw) and isinstance(channels_raw[i], dict):
                channels.append(
                    PulseChannelSettings.from_dict(channels_raw[i], default_pin)
                )
            else:
                pulses = 10 if i == 1 else 1
                channels.append(
                    PulseChannelSettings(pin=default_pin, pulses=pulses).clamp()
                )

        # Temp guard enable: new key or legacy thermistor_enabled
        if "temp_guard_enabled" in data:
            tg_en = bool(data["temp_guard_enabled"])
        else:
            tg_en = bool(data.get("thermistor_enabled", DEFAULT_TEMP_GUARD_ENABLED))

        sensor = str(data.get("temp_guard_sensor", DEFAULT_TEMP_GUARD_SENSOR)).lower()
        if sensor not in SENSOR_CHOICES:
            sensor = (
                SENSOR_ADS1115
                if data.get("thermistor_enabled")
                else DEFAULT_TEMP_GUARD_SENSOR
            )
        if sensor not in SENSOR_CHOICES:
            sensor = DEFAULT_TEMP_GUARD_SENSOR

        return cls(
            schema_version=CONFIG_SCHEMA_VERSION,
            record_frames=int(data.get("record_frames", DEFAULT_RECORD_FRAMES)),
            save_path=str(data.get("save_path", DEFAULT_SAVE_PATH)),
            sync_capture=bool(data.get("sync_capture", False)),
            capture_delay_us=int(data.get("capture_delay_us", 0)),
            tlinear_enabled=bool(data.get("tlinear_enabled", False)),
            physical_button_action=str(data.get("physical_button_action", "None")),
            fpn_correction_enabled=bool(data.get("fpn_correction_enabled", False)),
            frame_rate=int(data.get("frame_rate", DEFAULT_FRAME_RATE)),
            temp_guard_enabled=tg_en,
            temp_guard_sensor=sensor,
            thermistor_i2c_bus=int(
                data.get("thermistor_i2c_bus", DEFAULT_THERMISTOR_I2C_BUS)
            ),
            thermistor_i2c_addr=int(
                data.get("thermistor_i2c_addr", DEFAULT_THERMISTOR_I2C_ADDR)
            ),
            thermistor_channel=int(
                data.get("thermistor_channel", DEFAULT_THERMISTOR_CHANNEL)
            ),
            thermistor_threshold_v=float(
                data.get("thermistor_threshold_v", DEFAULT_THERMISTOR_THRESHOLD_V)
            ),
            ds18b20_id=str(data.get("ds18b20_id", DEFAULT_DS18B20_ID)),
            ds18b20_threshold_c=float(
                data.get("ds18b20_threshold_c", DEFAULT_DS18B20_THRESHOLD_C)
            ),
            gpio_alarm_pin=int(data.get("gpio_alarm_pin", DEFAULT_GPIO_ALARM_PIN)),
            pulse_channels=channels,
        ).clamp()

    # -------------------------------------------------------------- file I/O
    @classmethod
    def load(cls, path: str | Path = CONFIG_FILE) -> "AppSettings":
        path = Path(path)
        if not path.is_file():
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"WARNING: could not load {path}: {e} — using defaults")
            return cls()

    def save(self, path: str | Path = CONFIG_FILE) -> None:
        path = Path(path)
        payload = self.clamp().to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    # ----------------------------------------------------------- Tk bindings
    def apply_to_app(self, app, available_frame_rates: Optional[List[int]] = None) -> None:
        """Push settings into app tk variables (main thread)."""
        s = self.constrain_frame_rate(
            available_frame_rates
            if available_frame_rates is not None
            else (
                app.available_frame_rates()
                if hasattr(app, "available_frame_rates")
                else None
            )
        )

        app.record_frames_var.set(s.record_frames)
        app.save_path_var.set(s.save_path)
        app.sync_capture_var.set(s.sync_capture)
        app.capture_delay_us_var.set(s.capture_delay_us)
        app.tlinear_enabled_var.set(s.tlinear_enabled)
        app.physical_button_action_var.set(s.physical_button_action)
        app.fpn_correction_enabled.set(s.fpn_correction_enabled)
        app.frame_rate_var.set(s.frame_rate)

        app.temp_guard_enabled_var.set(s.temp_guard_enabled)
        app.temp_guard_sensor_var.set(s.temp_guard_sensor)
        app.thermistor_i2c_bus_var.set(s.thermistor_i2c_bus)
        app.thermistor_i2c_addr_var.set(s.thermistor_i2c_addr)
        app.thermistor_channel_var.set(s.thermistor_channel)
        app.thermistor_threshold_v_var.set(s.thermistor_threshold_v)
        app.ds18b20_id_var.set(s.ds18b20_id)
        app.ds18b20_threshold_c_var.set(s.ds18b20_threshold_c)
        app.gpio_alarm_pin_var.set(s.gpio_alarm_pin)

        for i, ch in enumerate(app.pulse_channels):
            if i >= len(s.pulse_channels):
                break
            src = s.pulse_channels[i]
            ch["enabled"].set(src.enabled)
            ch["pin"].set(src.pin)
            ch["on_time_us"].set(src.on_time_us)
            ch["off_time_us"].set(src.off_time_us)
            ch["pulses"].set(src.pulses)
            ch["start_delay_us"].set(src.start_delay_us)

    @classmethod
    def capture_from_app(cls, app) -> "AppSettings":
        """Build settings from app tk variables (main thread)."""
        channels = []
        for i, ch in enumerate(app.pulse_channels):
            default_pin = DEFAULT_PULSE_PINS[i] if i < len(DEFAULT_PULSE_PINS) else 24
            try:
                pin = int(ch["pin"].get())
            except (TypeError, ValueError):
                pin = default_pin
            channels.append(
                PulseChannelSettings(
                    enabled=bool(ch["enabled"].get()),
                    pin=pin,
                    on_time_us=int(ch["on_time_us"].get()),
                    off_time_us=int(ch["off_time_us"].get()),
                    pulses=int(ch["pulses"].get()),
                    start_delay_us=int(ch["start_delay_us"].get()),
                )
            )

        sensor = str(app.temp_guard_sensor_var.get())
        if sensor not in SENSOR_CHOICES:
            sensor = DEFAULT_TEMP_GUARD_SENSOR

        return cls(
            record_frames=int(app.record_frames_var.get()),
            save_path=str(app.save_path_var.get()),
            sync_capture=bool(app.sync_capture_var.get()),
            capture_delay_us=int(app.capture_delay_us_var.get()),
            tlinear_enabled=bool(app.tlinear_enabled_var.get()),
            physical_button_action=str(app.physical_button_action_var.get()),
            fpn_correction_enabled=bool(app.fpn_correction_enabled.get()),
            frame_rate=int(app.frame_rate_var.get()),
            temp_guard_enabled=bool(app.temp_guard_enabled_var.get()),
            temp_guard_sensor=sensor,
            thermistor_i2c_bus=int(app.thermistor_i2c_bus_var.get()),
            thermistor_i2c_addr=int(app.thermistor_i2c_addr_var.get()),
            thermistor_channel=int(app.thermistor_channel_var.get()),
            thermistor_threshold_v=float(app.thermistor_threshold_v_var.get()),
            ds18b20_id=str(app.ds18b20_id_var.get()),
            ds18b20_threshold_c=float(app.ds18b20_threshold_c_var.get()),
            gpio_alarm_pin=int(app.gpio_alarm_pin_var.get()),
            pulse_channels=channels,
        ).clamp()


def _migrate(data: dict, from_version: int) -> dict:
    """
    Migrate raw JSON dict from from_version toward CONFIG_SCHEMA_VERSION.

    version 0 = legacy unversioned config (pre–Phase 4).
    """
    d = dict(data)
    v = from_version

    # 0 → 1: normalize keys already handled in from_dict; just stamp version
    if v < 1:
        # Legacy used thermistor_enabled; leave keys for from_dict dual-read
        d["schema_version"] = 1
        v = 1

    d["schema_version"] = CONFIG_SCHEMA_VERSION
    return d
