"""Settings and camera-settings dialogs."""

import tkinter as tk
from tkinter import ttk

from gui.config_io import save_config
from gui.constants import (
    MAX_PULSE_TIME_MS,
    MAX_PULSES,
    MAX_START_DELAY_MS,
    MIN_PULSE_TIME_MS,
    MIN_PULSES,
    MIN_START_DELAY_MS,
    clamp_pulse_count,
    clamp_pulse_time_ms,
    clamp_start_delay_ms,
    pulse_time_ms_to_us,
    start_delay_ms_to_us,
    us_to_pulse_time_ms,
    us_to_start_delay_ms,
)


def open_settings(app):
    win = tk.Toplevel(app.root)
    win.title("Settings")
    win.geometry("920x920")
    win.transient(app.root)
    win.grab_set()
    win.focus_force()

    ttk.Button(
        win,
        text="Camera Settings",
        command=lambda: open_camera_settings(app),
        style="Touch.TButton",
    ).pack(pady=15, fill="x", padx=30)
    ttk.Separator(win, orient="horizontal").pack(fill="x", pady=10, padx=20)

    top_row = ttk.Frame(win)
    top_row.pack(pady=8, fill="x", padx=20)

    ttk.Label(top_row, text="Frames to Record:").pack(side=tk.LEFT)
    ttk.Entry(top_row, textvariable=app.record_frames_var, width=8).pack(
        side=tk.LEFT, padx=10
    )

    ttk.Checkbutton(
        win, text="Show ROI Overlay on Live View", variable=app.show_overlay_var
    ).pack(pady=5)

    capture_row = ttk.Frame(win)
    capture_row.pack(pady=10, fill="x", padx=20)

    sync_frame = ttk.LabelFrame(capture_row, text="Capture Synchronization")
    sync_frame.pack(side=tk.LEFT, fill="both", expand=True)

    ttk.Checkbutton(
        sync_frame,
        text="Sync GPIO Pulse with Capture",
        variable=app.sync_capture_var,
    ).pack(pady=3)
    ttk.Label(sync_frame, text="Delay (ms):").pack()
    capture_delay_ms_var = tk.IntVar(
        value=int(round(app.capture_delay_us_var.get() / 1000))
    )
    ttk.Entry(sync_frame, textvariable=capture_delay_ms_var, width=10).pack()

    ttk.Label(
        win, text="Physical Button Action (GPIO 17)", font=("Helvetica", 12, "bold")
    ).pack(pady=10)
    button_options = [
        "None",
        "Trigger Pulse",
        "Record Stream",
        "Record Frame",
        "Record RAW",
    ]
    ttk.Combobox(
        win,
        textvariable=app.physical_button_action_var,
        values=button_options,
        width=20,
        state="readonly",
    ).pack()

    ttk.Label(win, text="Save Location", font=("Helvetica", 12, "bold")).pack(
        pady=(15, 5)
    )
    path_frame = ttk.Frame(win)
    path_frame.pack(fill="x", padx=20)
    ttk.Entry(
        path_frame,
        textvariable=app.save_path_var,
        width=50,
        font=("Helvetica", 11),
    ).pack(side=tk.LEFT, fill="x", expand=True)

    def browse_save_path():
        from tkinter import filedialog

        folder = filedialog.askdirectory(title="Select Save Folder")
        if folder:
            app.save_path_var.set(folder)
            save_config(app)

    ttk.Button(path_frame, text="Browse...", command=browse_save_path).pack(
        side=tk.LEFT, padx=5
    )

    # ---- Temperature guard -------------------------------------------------
    # Full install / wiring / import notes live in gui/temp_guard.py (module
    # docstring). Summary for operators:
    #
    # DS18B20 (1-Wire °C):
    #   - /boot/firmware/config.txt → dtoverlay=w1-gpio  then reboot
    #   - DATA pin + 4.7k pull-up to 3V3; VDD→3V3, GND→GND
    #   - No pip package (kernel sysfs)
    #   - Optional: ls /sys/bus/w1/devices/
    #
    # ADS1115 (thermistor voltage via I2C ADC):
    #   - Enable I2C (raspi-config), reboot
    #   - pip install smbus2
    #   - Thermistor divider mid-point → AINx; ADS VDD/GND/SDA/SCL to Pi
    #   - i2cdetect -y 1  (often shows 0x48 → Addr 72 in UI)
    #
    # Leave checkbox OFF until Read Now shows a sensible value.
    # GPIO alarm: Arduino 3.3 V out → Pi BCM pin (default 16); HIGH = TEMP HIGH.
    from gui.constants import DEFAULT_GPIO_ALARM_PIN, PHYSICAL_BUTTON_PIN
    from gui.temp_guard import (
        DS18B20Reader,
        SENSOR_ADS1115,
        SENSOR_DS18B20,
        SENSOR_GPIO_ALARM,
    )

    interlock = ttk.LabelFrame(win, text="Temp Guard")
    interlock.pack(pady=12, fill="x", padx=20)

    ttk.Checkbutton(
        interlock,
        text="Temp Guard — block pulses when over temperature",
        variable=app.temp_guard_enabled_var,
    ).pack(anchor="w", padx=10, pady=4)

    ttk.Label(
        interlock,
        text=(
            "Disabled by default. Wire sensor → choose type → set threshold → "
            "Read Now → then enable. "
            "DS18B20: 1-Wire °C. ADS1115: I2C thermistor V. "
            f"GPIO alarm: Arduino 3.3 V digital HIGH = TEMP HIGH "
            f"(default BCM{DEFAULT_GPIO_ALARM_PIN}; avoids button BCM{PHYSICAL_BUTTON_PIN}, "
            "pulse defaults 22/23/24/27, I2C 2/3). "
            "Use 3.3 V logic only. Details: gui/temp_guard.py"
        ),
        font=("Helvetica", 9),
        wraplength=820,
    ).pack(anchor="w", padx=10, pady=(0, 6))

    sensor_row = ttk.Frame(interlock)
    sensor_row.pack(fill="x", padx=10, pady=4)

    ttk.Label(sensor_row, text="Sensor:").pack(side=tk.LEFT)
    sensor_labels = {
        SENSOR_DS18B20: "DS18B20 (1-Wire °C)",
        SENSOR_ADS1115: "ADS1115 (thermistor V)",
        SENSOR_GPIO_ALARM: "GPIO alarm (Arduino HIGH)",
    }
    # Keep StringVar as sensor key; combobox shows friendly labels
    sensor_display = tk.StringVar(
        value=sensor_labels.get(
            app.temp_guard_sensor_var.get(), sensor_labels[SENSOR_DS18B20]
        )
    )
    sensor_combo = ttk.Combobox(
        sensor_row,
        textvariable=sensor_display,
        values=list(sensor_labels.values()),
        width=32,
        state="readonly",
    )
    sensor_combo.pack(side=tk.LEFT, padx=8)

    def _sensor_key_from_display():
        display = sensor_display.get()
        for key, label in sensor_labels.items():
            if label == display:
                return key
        return SENSOR_DS18B20

    ads_frame = ttk.Frame(interlock)
    ads_frame.pack(fill="x", padx=10, pady=4)

    ttk.Label(ads_frame, text="ADS1115 — I2C bus:").pack(side=tk.LEFT)
    ttk.Entry(ads_frame, textvariable=app.thermistor_i2c_bus_var, width=4).pack(
        side=tk.LEFT, padx=(2, 8)
    )
    ttk.Label(ads_frame, text="Addr (dec):").pack(side=tk.LEFT)
    ttk.Entry(ads_frame, textvariable=app.thermistor_i2c_addr_var, width=5).pack(
        side=tk.LEFT, padx=(2, 8)
    )
    ttk.Label(ads_frame, text="AIN:").pack(side=tk.LEFT)
    ttk.Spinbox(
        ads_frame, from_=0, to=3, textvariable=app.thermistor_channel_var, width=4
    ).pack(side=tk.LEFT, padx=(2, 8))
    ttk.Label(ads_frame, text="Max V:").pack(side=tk.LEFT)
    ttk.Entry(ads_frame, textvariable=app.thermistor_threshold_v_var, width=7).pack(
        side=tk.LEFT, padx=(2, 4)
    )

    ds_frame = ttk.Frame(interlock)
    ds_frame.pack(fill="x", padx=10, pady=4)

    ttk.Label(ds_frame, text="DS18B20 — ID (blank=first):").pack(side=tk.LEFT)
    ttk.Entry(ds_frame, textvariable=app.ds18b20_id_var, width=18).pack(
        side=tk.LEFT, padx=(2, 8)
    )
    ttk.Label(ds_frame, text="Max °C (20–80):").pack(side=tk.LEFT)
    ttk.Spinbox(
        ds_frame,
        from_=20,
        to=80,
        increment=0.5,
        textvariable=app.ds18b20_threshold_c_var,
        width=7,
    ).pack(side=tk.LEFT, padx=(2, 8))

    def refresh_ds_list():
        found = DS18B20Reader.list_sensors()
        if found:
            live_var.set(f"Found: {', '.join(found)}")
        else:
            live_var.set("Found: (none)")

    ttk.Button(ds_frame, text="List sensors", command=refresh_ds_list).pack(
        side=tk.LEFT, padx=4
    )

    gpio_frame = ttk.Frame(interlock)
    gpio_frame.pack(fill="x", padx=10, pady=4)

    ttk.Label(gpio_frame, text="GPIO alarm — BCM pin:").pack(side=tk.LEFT)
    ttk.Entry(gpio_frame, textvariable=app.gpio_alarm_pin_var, width=5).pack(
        side=tk.LEFT, padx=(2, 8)
    )
    ttk.Label(
        gpio_frame,
        text="(3.3 V HIGH = TEMP HIGH; common GND; pull-down on Pi)",
        font=("Helvetica", 9),
    ).pack(side=tk.LEFT)

    live_row = ttk.Frame(interlock)
    live_row.pack(fill="x", padx=10, pady=4)
    live_var = tk.StringVar(value="Reading: --")
    ttk.Label(live_row, textvariable=live_var, width=50).pack(side=tk.LEFT)

    def read_temp_now():
        app.temp_guard_sensor_var.set(_sensor_key_from_display())
        app.reconfigure_temp_guard()
        if app.temp_guard is None:
            live_var.set("Reading: not init")
            return
        sensor = app.temp_guard_sensor_var.get()
        value, unit = app.temp_guard.read_current(sensor)
        if value is None:
            err = app.temp_guard.last_error or "failed"
            live_var.set(f"Reading: ERR ({err[:40]})")
        elif unit == "C":
            live_var.set(f"Reading: {value:.2f} °C")
        elif unit == "ALARM":
            live_var.set(
                "TEMP HIGH (input HIGH)" if int(value) else "OK (input LOW)"
            )
        else:
            live_var.set(f"Reading: {value:.3f} V")
        app._refresh_temp_guard_status()

    ttk.Button(live_row, text="Read Now", command=read_temp_now).pack(
        side=tk.LEFT, padx=4
    )

    def update_sensor_panels(*_args):
        key = _sensor_key_from_display()
        app.temp_guard_sensor_var.set(key)

    sensor_combo.bind("<<ComboboxSelected>>", update_sensor_panels)

    ttk.Label(win, text="GPIO Pulse Channels", font=("Helvetica", 14, "bold")).pack(
        pady=(15, 2)
    )
    ttk.Label(
        win,
        text=(
            f"On/Off: integer ms only ({MIN_PULSE_TIME_MS}–{MAX_PULSE_TIME_MS} ms). "
            f"Pulses: {MIN_PULSES}–{MAX_PULSES}. "
            f"Start delay: {MIN_START_DELAY_MS}–{MAX_START_DELAY_MS} ms. "
            "Values snap to the nearest allowed limit when you leave a field. "
            "Off time applies only when Pulses > 1. "
            "Limits are set in gui/constants.py."
        ),
        font=("Helvetica", 9),
        wraplength=860,
    ).pack(pady=(0, 8), padx=10)

    channel_on_time_ms_vars = []
    channel_off_time_ms_vars = []
    channel_delay_ms_vars = []
    channel_pulses_vars = []

    def _bind_clamp_on_focus_out(entry, var, clamp_fn):
        """When the user leaves the field, snap var to the nearest allowed value."""

        def on_focus_out(_event=None):
            try:
                raw = var.get()
            except (tk.TclError, ValueError, TypeError):
                raw = None
            fixed = clamp_fn(raw)
            try:
                if int(var.get()) != fixed:
                    var.set(fixed)
            except (tk.TclError, ValueError, TypeError):
                var.set(fixed)
            return None

        entry.bind("<FocusOut>", on_focus_out)
        # Also clamp when user presses Return in the field
        entry.bind("<Return>", on_focus_out)
        return on_focus_out

    for i, ch in enumerate(app.pulse_channels):
        frame = ttk.Frame(win)
        frame.pack(pady=4, fill="x", padx=10)

        ttk.Checkbutton(
            frame, text=f"Ch {i + 1}", variable=ch["enabled"]
        ).pack(side=tk.LEFT, padx=2)
        ttk.Label(frame, text="Pin:").pack(side=tk.LEFT)
        ttk.Entry(frame, textvariable=ch["pin"], width=4).pack(side=tk.LEFT, padx=2)

        on_time_ms_var = tk.IntVar(value=us_to_pulse_time_ms(ch["on_time_us"].get()))
        channel_on_time_ms_vars.append(on_time_ms_var)
        ttk.Label(frame, text="On (ms):").pack(side=tk.LEFT, padx=(6, 0))
        on_entry = ttk.Entry(frame, textvariable=on_time_ms_var, width=5)
        on_entry.pack(side=tk.LEFT)
        _bind_clamp_on_focus_out(on_entry, on_time_ms_var, clamp_pulse_time_ms)

        off_time_ms_var = tk.IntVar(value=us_to_pulse_time_ms(ch["off_time_us"].get()))
        channel_off_time_ms_vars.append(off_time_ms_var)
        ttk.Label(frame, text="Off (ms):").pack(side=tk.LEFT, padx=(6, 0))
        off_entry = ttk.Entry(frame, textvariable=off_time_ms_var, width=5)
        off_entry.pack(side=tk.LEFT)
        _bind_clamp_on_focus_out(off_entry, off_time_ms_var, clamp_pulse_time_ms)

        pulses_var = tk.IntVar(value=clamp_pulse_count(ch["pulses"].get()))
        channel_pulses_vars.append(pulses_var)
        ttk.Label(frame, text="Pulses:").pack(side=tk.LEFT, padx=(6, 0))
        pulses_entry = ttk.Entry(frame, textvariable=pulses_var, width=5)
        pulses_entry.pack(side=tk.LEFT)
        _bind_clamp_on_focus_out(pulses_entry, pulses_var, clamp_pulse_count)

        delay_ms_var = tk.IntVar(value=us_to_start_delay_ms(ch["start_delay_us"].get()))
        channel_delay_ms_vars.append(delay_ms_var)
        ttk.Label(frame, text="Start (ms):").pack(side=tk.LEFT, padx=(6, 0))
        delay_entry = ttk.Entry(frame, textvariable=delay_ms_var, width=5)
        delay_entry.pack(side=tk.LEFT)
        _bind_clamp_on_focus_out(delay_entry, delay_ms_var, clamp_start_delay_ms)

    def on_settings_close():
        from tkinter import messagebox

        from gui.constants import PHYSICAL_BUTTON_PIN
        from gui.gpio_service import GpioError

        try:
            app.capture_delay_us_var.set(int(capture_delay_ms_var.get()) * 1000)
        except (tk.TclError, ValueError, TypeError):
            pass

        for i, ch in enumerate(app.pulse_channels):
            on_ms = clamp_pulse_time_ms(channel_on_time_ms_vars[i].get())
            off_ms = clamp_pulse_time_ms(channel_off_time_ms_vars[i].get())
            pulses = clamp_pulse_count(channel_pulses_vars[i].get())
            delay_ms = clamp_start_delay_ms(channel_delay_ms_vars[i].get())
            channel_on_time_ms_vars[i].set(on_ms)
            channel_off_time_ms_vars[i].set(off_ms)
            channel_pulses_vars[i].set(pulses)
            channel_delay_ms_vars[i].set(delay_ms)
            ch["on_time_us"].set(pulse_time_ms_to_us(on_ms))
            ch["off_time_us"].set(pulse_time_ms_to_us(off_ms))
            ch["pulses"].set(pulses)
            ch["start_delay_us"].set(start_delay_ms_to_us(delay_ms))

        app.temp_guard_sensor_var.set(_sensor_key_from_display())
        try:
            t_c = float(app.ds18b20_threshold_c_var.get())
            app.ds18b20_threshold_c_var.set(max(20.0, min(80.0, t_c)))
        except (TypeError, ValueError):
            pass

        # ---- GPIO pin conflict check (Phase 1) ----
        pulse_pins = []
        for ch in app.pulse_channels:
            try:
                pulse_pins.append(int(ch["pin"].get()))
            except (TypeError, ValueError, tk.TclError):
                pulse_pins.append(-1)
        try:
            alarm_pin = int(app.gpio_alarm_pin_var.get())
        except (TypeError, ValueError, tk.TclError):
            alarm_pin = None

        if getattr(app, "gpio", None) is not None:
            conflicts = app.gpio.validate_pin_set(
                pulse_pins=pulse_pins,
                alarm_pin=alarm_pin,
                button_pin=PHYSICAL_BUTTON_PIN,
            )
            if conflicts:
                messagebox.showerror(
                    "GPIO pin conflict",
                    "Fix pin assignments before closing Settings:\n\n"
                    + "\n".join(f"• {c}" for c in conflicts),
                )
                return  # keep Settings open

        try:
            if getattr(app, "pulses", None) is not None:
                app.pulses.sync_pulse_pins()
        except GpioError as e:
            messagebox.showerror("GPIO", str(e))
            return

        app.reconfigure_temp_guard()
        app._refresh_temp_guard_status()
        # Phase 3: refresh plain-Python cache for worker / button threads
        if hasattr(app, "sync_runtime_caches"):
            app.sync_runtime_caches()
        save_config(app)
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_settings_close)


def open_camera_settings(app):
    win = tk.Toplevel(app.root)
    win.title("Camera Settings")
    win.geometry("500x460")
    win.transient(app.root)
    win.grab_set()
    win.focus_force()

    ttk.Label(win, text="Boson+ Camera Controls", font=("Helvetica", 14, "bold")).pack(
        pady=15
    )

    ttk.Checkbutton(
        win,
        text="Enable TLinear (Temperature Linear)",
        variable=app.tlinear_enabled_var,
    ).pack(pady=8, anchor="w", padx=30)
    ttk.Checkbutton(
        win,
        text="Enable FPN Correction (Software)",
        variable=app.fpn_correction_enabled,
    ).pack(pady=8, anchor="w", padx=30)

    ttk.Separator(win, orient="horizontal").pack(fill="x", pady=15, padx=30)

    rate_frame = ttk.Frame(win)
    rate_frame.pack(pady=8, fill="x", padx=30)

    ttk.Label(rate_frame, text="Frame Rate (Hz):").pack(side=tk.LEFT)
    available_rates = app.available_frame_rates()
    rate_labels = [str(r) for r in available_rates]
    frame_rate_str_var = tk.StringVar(value=str(app.frame_rate_var.get()))
    rate_combo = ttk.Combobox(
        rate_frame,
        textvariable=frame_rate_str_var,
        values=rate_labels,
        width=8,
        state="readonly" if len(rate_labels) > 1 else "disabled",
    )
    rate_combo.pack(side=tk.LEFT, padx=10)

    ttk.Label(
        win,
        text=(
            f"Hardware base: {app.hardware_base_fps} Hz. "
            "Lower rates use the smart averager (half rate)."
        ),
        font=("Helvetica", 9),
        wraplength=420,
    ).pack(pady=(0, 8), padx=30, anchor="w")

    roi_frame = ttk.Frame(win)
    roi_frame.pack(pady=10, fill="x", padx=30)

    ttk.Label(roi_frame, text="ROI Size (pixels):").pack(side=tk.LEFT)
    ttk.Spinbox(
        roi_frame, from_=5, to=200, textvariable=app.roi_half_var, width=8
    ).pack(side=tk.LEFT, padx=10)

    ttk.Checkbutton(
        win, text="Show ROI Overlay on Live View", variable=app.show_overlay_var
    ).pack(pady=8, anchor="w", padx=30)

    def apply_changes():
        try:
            app.frame_rate_var.set(int(frame_rate_str_var.get()))
        except (TypeError, ValueError):
            pass
        app.apply_video_mode()
        app.apply_frame_rate()
        save_config(app)

    ttk.Button(win, text="Apply Changes", command=apply_changes).pack(pady=20)
