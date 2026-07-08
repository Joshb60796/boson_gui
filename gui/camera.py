"""Boson+ camera connection and control (SDK + V4L2 capture)."""

import time

import cv2

from BosonSDK import *  # noqa: F403

from gui.constants import (
    COM_PORT,
    DEFAULT_FRAME_RATE,
    HEIGHT,
    VIDEO_DEVICE_INDEX,
    WIDTH,
)


class CameraService:
    """Owns CamAPI client, OpenCV capture, FFC, and frame-rate control."""

    def __init__(self, app):
        self.app = app
        self.myCam = None
        self.cap = None
        self.hardware_base_fps = DEFAULT_FRAME_RATE
        self.auto_ffc_enabled = True

    def connect(self):
        print("Connecting to Boson+...")

        self.myCam = CamAPI.pyClient(manualport=COM_PORT, useDll=False)
        self.myCam.bosonSetGainMode(FLR_BOSON_GAINMODE_E.FLR_BOSON_HIGH_GAIN)

        self.cap = cv2.VideoCapture(VIDEO_DEVICE_INDEX, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

        if not self.cap.isOpened():
            print("ERROR: Could not open video stream.")
            self.myCam.Close()
            raise SystemExit(1)

        self.myCam.TLinearSetControl(FLR_ENABLE_E.FLR_DISABLE)
        self.myCam.sysctrlSetUsbVideoIR16Mode(
            FLR_SYSCTRL_USBIR16_MODE_E.FLR_SYSCTRL_USBIR16_MODE_16
        )
        self.myCam.radiometrySetTransmissionWindow(1.00)
        self.myCam.TLinearRefreshLUT(FLR_BOSON_GAINMODE_E.FLR_BOSON_HIGH_GAIN)

        try:
            self.myCam.gaoSetAveragerState(FLR_ENABLE_E.FLR_DISABLE)
        except Exception as e:
            print(f"Warning: could not disable averager: {e}")

        self.hardware_base_fps = self._query_hardware_base_fps()
        print(f"Hardware base frame rate: {self.hardware_base_fps} Hz")

        time.sleep(0.4)
        self.myCam.bosonRunFFC()
        time.sleep(0.6)

        print("Radiometric mode enabled (RAW counts by default).\n")

    @staticmethod
    def _unwrap_sdk_value(result):
        if isinstance(result, (tuple, list)):
            return result[-1]
        return result

    def _query_hardware_base_fps(self):
        try:
            rate = self._unwrap_sdk_value(self.myCam.sysctrlGetCameraFrameRate())
            rate = int(rate)
            if rate > 0:
                return rate
        except Exception as e:
            print(f"Warning: could not read camera frame rate: {e}")
        return DEFAULT_FRAME_RATE

    def available_frame_rates(self):
        """
        Runtime-selectable rates for this camera.

        Boson+ has no direct SetFrameRate. The smart averager
        (gaoSetAveragerState) halves the base rate (e.g. 60→30, 30→15).
        """
        base = int(self.hardware_base_fps or DEFAULT_FRAME_RATE)
        rates = [base]
        if base >= 30 and base % 2 == 0:
            rates.append(base // 2)
        return sorted(set(rates), reverse=True)

    def apply_video_mode(self):
        app = self.app
        if app.tlinear_enabled_var.get():
            self.myCam.TLinearSetControl(FLR_ENABLE_E.FLR_ENABLE)
            self.myCam.sysctrlSetUsbVideoIR16Mode(
                FLR_SYSCTRL_USBIR16_MODE_E.FLR_SYSCTRL_USBIR16_MODE_TLINEAR
            )
        else:
            self.myCam.TLinearSetControl(FLR_ENABLE_E.FLR_DISABLE)
            self.myCam.sysctrlSetUsbVideoIR16Mode(
                FLR_SYSCTRL_USBIR16_MODE_E.FLR_SYSCTRL_USBIR16_MODE_16
            )

    def apply_frame_rate(self):
        """Full base rate → averager off; half base → averager on."""
        app = self.app
        desired = int(app.frame_rate_var.get())
        available = self.available_frame_rates()
        if desired not in available:
            desired = available[0]
            app.frame_rate_var.set(desired)

        base = available[0]
        try:
            if desired == base:
                self.myCam.gaoSetAveragerState(FLR_ENABLE_E.FLR_DISABLE)
            elif desired == base // 2:
                self.myCam.gaoSetAveragerState(FLR_ENABLE_E.FLR_ENABLE)
            else:
                print(f"Unsupported frame rate {desired}; available: {available}")
                return
            print(f"Camera frame rate set to {desired} Hz")
        except Exception as e:
            print(f"Error setting frame rate: {e}")

    def manual_ffc(self):
        self.myCam.bosonRunFFC()

    def toggle_auto_ffc(self):
        app = self.app
        if self.auto_ffc_enabled:
            self.myCam.bosonSetFFCMode(FLR_BOSON_FFCMODE_E.FLR_BOSON_MANUAL_FFC)
            if getattr(app, "btn_auto_ffc", None) is not None:
                app.btn_auto_ffc.config(text="Enable Auto FFC")
            self.auto_ffc_enabled = False
        else:
            self.myCam.bosonSetFFCMode(FLR_BOSON_FFCMODE_E.FLR_BOSON_AUTO_FFC)
            if getattr(app, "btn_auto_ffc", None) is not None:
                app.btn_auto_ffc.config(text="Disable Auto FFC")
            self.auto_ffc_enabled = True

    def read_frame(self):
        return self.cap.read()

    def temp_from_counts(self, counts):
        return self.myCam.radiometryGetTempFromCounts(counts)

    def close(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        if self.myCam is not None:
            try:
                self.myCam.Close()
            except Exception:
                pass
            self.myCam = None
