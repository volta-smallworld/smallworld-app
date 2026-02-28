import numpy as np
from PIL import Image

from smallworld_api.services.terrarium import decode_terrarium


def _make_tile(r: int, g: int, b: int, size: int = 1) -> Image.Image:
    """Create a small RGB image with uniform color."""
    arr = np.full((size, size, 3), [r, g, b], dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def test_sea_level():
    # elevation = (128 * 256 + 0 + 0/256) - 32768 = 0
    img = _make_tile(128, 0, 0)
    elev = decode_terrarium(img)
    assert elev[0, 0] == 0.0


def test_positive_elevation():
    # elevation = (134 * 256 + 55 + 128/256) - 32768 = 1591.5
    img = _make_tile(134, 55, 128)
    elev = decode_terrarium(img)
    assert abs(elev[0, 0] - 1591.5) < 0.01


def test_negative_elevation():
    # elevation = (127 * 256 + 0 + 0/256) - 32768 = -256
    img = _make_tile(127, 0, 0)
    elev = decode_terrarium(img)
    assert elev[0, 0] == -256.0


def test_multi_pixel():
    arr = np.array([
        [[128, 0, 0], [134, 55, 128]],
        [[127, 0, 0], [128, 1, 0]],
    ], dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    elev = decode_terrarium(img)
    assert elev.shape == (2, 2)
    assert elev[0, 0] == 0.0
    assert abs(elev[0, 1] - 1591.5) < 0.01
    assert elev[1, 0] == -256.0
    assert elev[1, 1] == 1.0
