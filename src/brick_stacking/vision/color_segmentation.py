"""HSV masks; profile ranges use OpenCV H=0..179, S/V=0..255."""
import cv2
import numpy as np


def segment_colors(rgb, ranges):
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[-1] != 3:
        raise ValueError("uint8 RGB required")
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    masks = {}
    for color, bands in ranges.items():
        if not bands:
            raise ValueError("empty HSV range")
        mask = np.zeros(rgb.shape[:2], np.uint8)
        for low, high in bands:
            lo, hi = np.asarray(low), np.asarray(high)
            if lo.shape != (3,) or hi.shape != (3,) or not np.isfinite(lo).all() or not np.isfinite(hi).all():
                raise ValueError("invalid HSV bounds")
            if np.any(lo < 0) or np.any(hi > [179, 255, 255]) or np.any(lo > hi):
                raise ValueError("HSV range out of bounds")
            mask |= cv2.inRange(hsv, lo.astype(np.uint8), hi.astype(np.uint8))
        masks[color] = mask
    return masks
