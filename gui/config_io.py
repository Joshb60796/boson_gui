"""
Load and save application settings.

Phase 4: all persistence goes through AppSettings (gui/settings_model.py).
These helpers remain the public API used by app.py and settings dialogs.
"""

from __future__ import annotations

from gui.constants import CONFIG_FILE
from gui.settings_model import AppSettings


def load_config(app, path: str = CONFIG_FILE) -> AppSettings:
    """
    Load config.json into the app's tk variables.

    Returns the AppSettings instance applied (defaults if file missing/corrupt).
    Logs a warning on parse failure instead of silent pass.
    """
    settings = AppSettings.load(path)
    available = None
    if hasattr(app, "available_frame_rates"):
        try:
            available = app.available_frame_rates()
        except Exception:
            available = None
    settings = settings.constrain_frame_rate(available)
    settings.apply_to_app(app, available_frame_rates=available)
    # Keep a copy on the app for introspection / tests
    app.settings_model = settings
    return settings


def save_config(app, path: str = CONFIG_FILE) -> AppSettings:
    """
    Capture tk variables into AppSettings, clamp, write config.json.

    Returns the saved AppSettings instance.
    """
    settings = AppSettings.capture_from_app(app)
    if hasattr(app, "available_frame_rates"):
        try:
            settings = settings.constrain_frame_rate(app.available_frame_rates())
        except Exception:
            pass
    # Write clamped values back into tk so UI matches disk
    settings.apply_to_app(app)
    settings.save(path)
    app.settings_model = settings
    return settings
