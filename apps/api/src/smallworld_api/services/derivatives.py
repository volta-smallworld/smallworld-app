"""Pure-NumPy terrain derivative computations on a 2-D elevation grid."""

import numpy as np


def compute_slope_degrees(dem: np.ndarray, cell_size: float) -> np.ndarray:
    """Slope in degrees via central differences.

    Uses np.gradient which applies central differences in the interior
    and one-sided differences at the boundaries.
    """
    dy, dx = np.gradient(dem, cell_size)
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    return np.degrees(slope_rad)


def compute_profile_curvature(dem: np.ndarray, cell_size: float) -> np.ndarray:
    """Profile curvature — rate of slope change in the gradient direction.

    Approximated via second derivatives along the gradient.
    Cells with negligible gradient are clamped to zero.
    """
    dy, dx = np.gradient(dem, cell_size)
    grad_mag_sq = dx**2 + dy**2
    grad_mag_sq_safe = np.where(grad_mag_sq > 1e-8, grad_mag_sq, 1.0)

    dyy, dyx = np.gradient(dy, cell_size)
    dxy, dxx = np.gradient(dx, cell_size)

    # Profile curvature formula:
    # Kp = -(dx^2*dxx + 2*dx*dy*dxy + dy^2*dyy) / (grad_mag^2 * sqrt(1+grad_mag^2))
    numerator = dx**2 * dxx + 2 * dx * dy * dxy + dy**2 * dyy
    denominator = grad_mag_sq_safe * np.sqrt(1.0 + grad_mag_sq_safe)

    curv = -numerator / denominator
    # Zero out cells where gradient is negligible
    curv = np.where(grad_mag_sq > 1e-8, curv, 0.0)
    return curv


def compute_local_relief(dem: np.ndarray, window: int = 21) -> np.ndarray:
    """Local relief: max - min elevation within a sliding window.

    Uses stride_tricks for a fast sliding window. Pads edges with
    reflect so the output is the same shape as the input.
    """
    pad = window // 2
    padded = np.pad(dem, pad, mode="reflect")
    h, w = padded.shape
    out_h = h - window + 1
    out_w = w - window + 1
    shape = (out_h, out_w, window, window)
    strides = padded.strides * 2
    windows = np.lib.stride_tricks.as_strided(padded, shape=shape, strides=strides)
    local_max = windows.reshape(out_h, out_w, -1).max(axis=2)
    local_min = windows.reshape(out_h, out_w, -1).min(axis=2)
    return local_max - local_min
