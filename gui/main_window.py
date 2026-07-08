"""Main application window layout (video panel + touch buttons)."""

import tkinter as tk
from tkinter import ttk


class MainWindow:
    """Builds the primary UI and stores widget references on the app."""

    def __init__(self, app):
        self.app = app

    def build(self):
        app = self.app
        style = ttk.Style()
        style.configure("Touch.TButton", font=("Helvetica", 16), padding=(40, 22))
        style.configure("Small.TButton", font=("Helvetica", 14), padding=(20, 12))

        main_frame = tk.Frame(app.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        app.video_label = tk.Label(main_frame)
        app.video_label.pack(side=tk.LEFT, padx=(0, 20))

        button_frame = tk.Frame(main_frame)
        button_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)

        ttk.Label(
            button_frame, textvariable=app.fps_var, font=("Helvetica", 12)
        ).pack(pady=(0, 4))

        app.temp_guard_status_label = tk.Label(
            button_frame,
            textvariable=app.temp_guard_status_var,
            font=("Helvetica", 11, "bold"),
            fg="#666666",
        )
        app.temp_guard_status_label.pack(pady=(0, 8))

        ffc_frame = ttk.Frame(button_frame)
        ffc_frame.pack(pady=6, fill=tk.X)
        ffc_frame.columnconfigure(0, weight=1)
        ffc_frame.columnconfigure(1, weight=1)

        ttk.Button(
            ffc_frame,
            text="Manual FFC",
            command=app.camera.manual_ffc,
            style="Touch.TButton",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))

        app.btn_auto_ffc = ttk.Button(
            ffc_frame,
            text="Disable Auto FFC",
            command=app.camera.toggle_auto_ffc,
            style="Small.TButton",
        )
        app.btn_auto_ffc.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        app.btn_trigger = ttk.Button(
            button_frame,
            text="Trigger Pulse",
            command=app.pulses.trigger_pulse_button_action,
            style="Touch.TButton",
            width=18,
        )
        app.btn_trigger.pack(pady=6, fill=tk.X)

        app.btn_stream = ttk.Button(
            button_frame,
            text="Record Stream",
            command=app.recording.record_stream,
            style="Touch.TButton",
            width=18,
        )
        app.btn_stream.pack(pady=6, fill=tk.X)

        app.btn_frame = ttk.Button(
            button_frame,
            text="Record Frame",
            command=app.recording.record_frame,
            style="Touch.TButton",
            width=18,
        )
        app.btn_frame.pack(pady=6, fill=tk.X)

        app.btn_raw = ttk.Button(
            button_frame,
            text="Record RAW",
            command=app.recording.record_raw_frame,
            style="Touch.TButton",
            width=18,
        )
        app.btn_raw.pack(pady=6, fill=tk.X)

        app.btn_background = ttk.Button(
            button_frame,
            text="-Background",
            command=app.recording.capture_background,
            style="Touch.TButton",
            width=18,
        )
        app.btn_background.pack(pady=6, fill=tk.X)

        bottom_frame = ttk.Frame(button_frame)
        bottom_frame.pack(pady=10, fill=tk.X)
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.columnconfigure(1, weight=1)

        ttk.Button(
            bottom_frame,
            text="Settings",
            command=app.open_settings,
            style="Small.TButton",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(
            bottom_frame,
            text="Quit",
            command=app.root.destroy,
            style="Small.TButton",
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

        app.root.protocol("WM_DELETE_WINDOW", app.on_closing)
