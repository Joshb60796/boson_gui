"""Frame processing helpers (background subtraction, FPN correction)."""

import cv2
import numpy as np


def apply_background_subtraction(frame, background_frame):
    if background_frame is None:
        return frame
    result = frame.astype(np.float32) - background_frame
    result = np.clip(result, 0, 65535).astype(np.uint16)
    return result


def apply_fpn_correction(frame, kernel_size=51):
    if frame is None:
        return frame
    frame = frame.astype(np.float32)
    blurred = cv2.GaussianBlur(frame, (kernel_size, kernel_size), 0)
    result = frame - blurred
    return result


def process_frame(frame, background_frame=None, fpn_enabled=False):
    frame = apply_background_subtraction(frame, background_frame)
    if fpn_enabled:
        frame = apply_fpn_correction(frame)
    return frame


def finalize_frame(frame):
    return np.clip(frame, 0, 65535).astype(np.uint16)
