"""
Single-owner GPIO access for the Boson app (Phase 1 architecture).

All lgpio chip open/claim/read/write for button, pulse outputs, and digital
temp-alarm input go through GpioService. No other module should call
gpiochip_open.

Pin roles cannot collide. Bus pins (I2C / 1-Wire / UART) are reserved.
"""

from __future__ import annotations

import threading
from enum import Enum

from gui.constants import (
    DEFAULT_GPIO_ALARM_PIN,
    DEFAULT_PULSE_PINS,
    PHYSICAL_BUTTON_PIN,
    RESERVED_BUS_PINS,
)


class PinRole(str, Enum):
    BUTTON = "button"
    PULSE = "pulse"
    TEMP_ALARM = "temp_alarm"


class PinMode(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class GpioError(Exception):
    """Raised when a pin cannot be registered or used."""


class GpioService:
    """One gpiochip handle + pin registry for the whole application."""

    def __init__(self, chip: int = 0):
        self._chip_id = chip
        self._h = None
        self._lock = threading.RLock()
        # pin -> {"role": PinRole, "mode": PinMode}
        self._registry: dict[int, dict] = {}
        self._lgpio = None

    @property
    def is_open(self) -> bool:
        return self._h is not None

    def open(self) -> None:
        with self._lock:
            if self._h is not None:
                return
            try:
                import lgpio

                self._lgpio = lgpio
                self._h = lgpio.gpiochip_open(self._chip_id)
                print(f"GpioService: opened gpiochip {self._chip_id}")
            except ImportError as e:
                raise GpioError(
                    "lgpio not installed (pip install lgpio or apt python3-lgpio)"
                ) from e
            except Exception as e:
                self._h = None
                raise GpioError(f"Failed to open gpiochip {self._chip_id}: {e}") from e

    def close(self) -> None:
        with self._lock:
            if self._h is None:
                return
            lgpio = self._lgpio
            for pin in list(self._registry.keys()):
                try:
                    if lgpio is not None:
                        lgpio.gpio_free(self._h, pin)
                except Exception:
                    pass
            self._registry.clear()
            try:
                if lgpio is not None:
                    lgpio.gpiochip_close(self._h)
            except Exception:
                pass
            self._h = None
            print("GpioService: closed")

    def _ensure_open(self) -> None:
        if self._h is None:
            self.open()

    def _check_reserved(self, pin: int) -> None:
        pin = int(pin)
        if pin in RESERVED_BUS_PINS:
            raise GpioError(
                f"BCM{pin} is reserved for a system bus (I2C/1-Wire/UART) "
                f"and cannot be used for GPIO app roles."
            )

    def register_input(self, pin: int, role: PinRole, pull_down: bool = False) -> None:
        """
        Claim pin as input. Idempotent if same role already registered.
        pull_down=True → SET_PULL_DOWN; False → SET_PULL_UP.
        """
        pin = int(pin)
        with self._lock:
            self._ensure_open()
            self._check_reserved(pin)
            existing = self._registry.get(pin)
            if existing is not None:
                if existing["role"] == role and existing["mode"] == PinMode.INPUT:
                    return
                raise GpioError(
                    f"BCM{pin} already registered as {existing['role'].value}/"
                    f"{existing['mode'].value}; cannot register as {role.value}/input"
                )

            lgpio = self._lgpio
            flags = lgpio.SET_PULL_DOWN if pull_down else lgpio.SET_PULL_UP
            try:
                lgpio.gpio_claim_input(self._h, pin, flags)
            except Exception as e:
                raise GpioError(f"Failed to claim BCM{pin} as input: {e}") from e

            self._registry[pin] = {"role": role, "mode": PinMode.INPUT}
            print(f"GpioService: BCM{pin} input ({role.value})")

    def register_output(self, pin: int, role: PinRole, initial: int = 0) -> None:
        """Claim pin as output. Idempotent if same role already registered."""
        pin = int(pin)
        initial = 1 if initial else 0
        with self._lock:
            self._ensure_open()
            self._check_reserved(pin)
            existing = self._registry.get(pin)
            if existing is not None:
                if existing["role"] == role and existing["mode"] == PinMode.OUTPUT:
                    return
                raise GpioError(
                    f"BCM{pin} already registered as {existing['role'].value}/"
                    f"{existing['mode'].value}; cannot register as {role.value}/output"
                )

            lgpio = self._lgpio
            try:
                lgpio.gpio_claim_output(self._h, pin)
                lgpio.gpio_write(self._h, pin, initial)
            except Exception as e:
                raise GpioError(f"Failed to claim BCM{pin} as output: {e}") from e

            self._registry[pin] = {"role": role, "mode": PinMode.OUTPUT}
            print(f"GpioService: BCM{pin} output ({role.value})")

    def unregister(self, pin: int) -> None:
        pin = int(pin)
        with self._lock:
            if self._h is None or pin not in self._registry:
                return
            try:
                self._lgpio.gpio_free(self._h, pin)
            except Exception:
                pass
            del self._registry[pin]
            print(f"GpioService: freed BCM{pin}")

    def ensure_pulse_pins(self, pins) -> None:
        """
        Register each pin as a PULSE output (LOW). Safe to call repeatedly.
        Also frees former PULSE pins that are no longer in the list.
        """
        wanted = {int(p) for p in pins}
        with self._lock:
            # Free pulse pins no longer needed
            for pin, info in list(self._registry.items()):
                if info["role"] == PinRole.PULSE and pin not in wanted:
                    self.unregister(pin)
            for pin in wanted:
                self.register_output(pin, PinRole.PULSE, initial=0)

    def read(self, pin: int) -> int:
        pin = int(pin)
        with self._lock:
            self._ensure_open()
            if pin not in self._registry:
                raise GpioError(f"BCM{pin} is not registered")
            try:
                return int(self._lgpio.gpio_read(self._h, pin))
            except Exception as e:
                raise GpioError(f"Read BCM{pin} failed: {e}") from e

    def write(self, pin: int, level: int) -> None:
        pin = int(pin)
        level = 1 if level else 0
        with self._lock:
            self._ensure_open()
            info = self._registry.get(pin)
            if info is None:
                raise GpioError(f"BCM{pin} is not registered")
            if info["mode"] != PinMode.OUTPUT:
                raise GpioError(f"BCM{pin} is not an output")
            try:
                self._lgpio.gpio_write(self._h, pin, level)
            except Exception as e:
                raise GpioError(f"Write BCM{pin} failed: {e}") from e

    def role_of(self, pin: int):
        info = self._registry.get(int(pin))
        return info["role"] if info else None

    def validate_app_pin(self, pin: int, role: PinRole) -> str | None:
        """
        Return an error message if pin is illegal for role, else None.
        Does not claim the pin. Used by Settings validation.
        """
        try:
            pin = int(pin)
        except (TypeError, ValueError):
            return "Pin must be an integer BCM number."
        if pin < 0 or pin > 27:
            return f"BCM{pin} is out of typical range (0–27)."
        if pin in RESERVED_BUS_PINS:
            return (
                f"BCM{pin} is reserved for I2C/1-Wire/UART and cannot be used."
            )
        # Cross-role defaults (soft check against known fixed roles)
        if role == PinRole.PULSE:
            if pin == PHYSICAL_BUTTON_PIN:
                return f"BCM{pin} is the physical button pin."
            if pin == DEFAULT_GPIO_ALARM_PIN:
                # Only warn if alarm is the default; runtime registry is authoritative
                pass
        if role == PinRole.TEMP_ALARM and pin == PHYSICAL_BUTTON_PIN:
            return f"BCM{pin} is the physical button pin."
        if role == PinRole.BUTTON and pin == DEFAULT_GPIO_ALARM_PIN:
            pass
        with self._lock:
            existing = self._registry.get(pin)
            if existing is not None and existing["role"] != role:
                return (
                    f"BCM{pin} is already used as {existing['role'].value}."
                )
        return None

    def validate_pin_set(
        self,
        pulse_pins: list[int],
        alarm_pin: int | None = None,
        button_pin: int = PHYSICAL_BUTTON_PIN,
    ) -> list[str]:
        """Return list of human-readable conflict messages (empty if OK)."""
        errors = []
        seen: dict[int, str] = {}

        def add(pin, label):
            try:
                p = int(pin)
            except (TypeError, ValueError):
                errors.append(f"{label}: invalid pin value {pin!r}")
                return
            if p in RESERVED_BUS_PINS:
                errors.append(f"{label}: BCM{p} is reserved (bus).")
                return
            if p in seen and seen[p] != label:
                errors.append(
                    f"BCM{p} used by both {seen[p]} and {label}."
                )
            else:
                seen[p] = label
            msg = self.validate_app_pin(
                p,
                PinRole.PULSE
                if label.startswith("Pulse")
                else PinRole.TEMP_ALARM
                if label == "Temp alarm"
                else PinRole.BUTTON,
            )
            # validate_app_pin may double-count reserved; only add distinct
            if msg and msg not in errors and "already used" not in msg:
                if "reserved" in msg or "button" in msg.lower() or "range" in msg:
                    if msg not in errors:
                        errors.append(f"{label}: {msg}")

        add(button_pin, "Physical button")
        if alarm_pin is not None:
            add(alarm_pin, "Temp alarm")
        for i, pin in enumerate(pulse_pins):
            add(pin, f"Pulse ch{i + 1}")

        return errors


def default_pulse_pin_list():
    return list(DEFAULT_PULSE_PINS)
