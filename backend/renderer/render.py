"""
Terrain renderer — first-person landscape views + overhead overview maps.

Front-to-back voxel-space raycaster with bilinear DEM sampling,
distance fog, diffuse sun lighting, and sky gradient.
"""

import os
import numpy as np
from PIL import Image as PILImage, ImageFilter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, LinearSegmentedColormap
from matplotlib.patches import Wedge
from typing import Optional
from log import get_logger

log = get_logger("renderer")

RENDER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "renders")
os.makedirs(RENDER_DIR, exist_ok=True)

# ── Colors ────────────────────────────────────────────────
_TC = np.array([
    [56, 92, 46], [77, 122, 56], [128, 153, 77], [174, 166, 97],
    [158, 128, 87], [140, 112, 84], [184, 174, 158], [235, 235, 230],
], dtype=np.float64) / 255.0
_TS = np.array([0.0, 0.12, 0.25, 0.40, 0.55, 0.70, 0.85, 1.0])

_SKY_TOP = np.array([0.33, 0.50, 0.70])
_SKY_HOR = np.array([0.78, 0.82, 0.88])
_FOG = np.array([0.75, 0.79, 0.85])

TERRAIN_CMAP = LinearSegmentedColormap.from_list(
    "terrain_sw", list(zip(_TS, [tuple(c) for c in _TC])))


def _build_lut(n=512):
    """Elevation-fraction → RGB lookup, shape (n, 3)."""
    lut = np.zeros((n, 3))
    for i in range(n):
        t = i / (n - 1)
        for j in range(len(_TS) - 1):
            if t <= _TS[j + 1] or j == len(_TS) - 2:
                f = np.clip((t - _TS[j]) / max(_TS[j+1] - _TS[j], 1e-6), 0, 1)
                lut[i] = _TC[j] * (1 - f) + _TC[j + 1] * f
                break
    return lut

_COLOR_LUT = _build_lut()
_LUT_N = len(_COLOR_LUT)


def _bilerp(dem, r_f, c_f):
    """Bilinear interpolation of DEM at fractional (row, col) coords.
    r_f, c_f: float arrays of shape (N,). Returns elevation array (N,)."""
    h, w = dem.shape
    r0 = np.clip(r_f.astype(np.int32), 0, h - 2)
    c0 = np.clip(c_f.astype(np.int32), 0, w - 2)
    fr = np.clip(r_f - r0, 0, 1)
    fc = np.clip(c_f - c0, 0, 1)
    z00 = dem[r0, c0]
    z01 = dem[r0, c0 + 1]
    z10 = dem[r0 + 1, c0]
    z11 = dem[r0 + 1, c0 + 1]
    return z00 * (1 - fr) * (1 - fc) + z01 * (1 - fr) * fc + \
           z10 * fr * (1 - fc) + z11 * fr * fc


def render_viewpoint(
    dem, cam_row, cam_col, cam_z,
    yaw_deg, pitch_deg, fov_deg, res_m,
    render_id, width=640, height=400,
):
    """Render first-person terrain panorama."""
    try:
        img = _raycast(dem, cam_row, cam_col, cam_z,
                       yaw_deg, pitch_deg, fov_deg, res_m,
                       width, height)
        _draw_hud(img, yaw_deg, pitch_deg, fov_deg)

        # Post-process: blur to smooth staircase edges, then sharpen to restore detail
        pil_img = PILImage.fromarray((img * 255).clip(0, 255).astype(np.uint8))
        pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=1.2))
        pil_img = pil_img.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))

        filename = f"{render_id}.png"
        pil_img.save(os.path.join(RENDER_DIR, filename), optimize=True)
        log.info(f"Rendered {render_id} → {filename}")
        return filename
    except Exception as e:
        log.error(f"Render failed for {render_id}: {e}")
        return None


def _bilerp_grid(grid, r_f, c_f):
    """Bilinear interpolation on any 2D grid at fractional coords."""
    h, w = grid.shape
    r0 = np.clip(r_f.astype(np.int32), 0, h - 2)
    c0 = np.clip(c_f.astype(np.int32), 0, w - 2)
    fr = np.clip(r_f - r0, 0, 1)
    fc = np.clip(c_f - c0, 0, 1)
    return (grid[r0, c0] * (1 - fr) * (1 - fc) +
            grid[r0, c0 + 1] * (1 - fr) * fc +
            grid[r0 + 1, c0] * fr * (1 - fc) +
            grid[r0 + 1, c0 + 1] * fr * fc)


def _raycast(dem, cam_row, cam_col, cam_z,
             yaw_deg, pitch_deg, fov_deg, res_m,
             img_w, img_h, max_dist_m=15000):
    """Front-to-back column raycaster with bilinear sampling."""

    h, w = dem.shape
    vfov = fov_deg * img_h / img_w
    top_ang = pitch_deg + vfov / 2.0
    px_per_deg = img_h / vfov

    image = _sky(img_h, img_w, pitch_deg, vfov)

    # Rays
    half_h = fov_deg / 2.0
    az_rad = np.radians(yaw_deg + np.linspace(-half_h, half_h, img_w))
    ray_dr = -np.cos(az_rad) / res_m
    ray_dc = np.sin(az_rad) / res_m

    # Precompute normals + sun (bilinear-interpolated later)
    gy, gx = np.gradient(dem, res_m)
    sa, se = np.radians(315), np.radians(30)
    sun = np.array([np.sin(sa)*np.cos(se), -np.cos(sa)*np.cos(se), np.sin(se)])

    dem_min, dem_max = float(dem.min()), float(dem.max())
    dem_range = max(dem_max - dem_min, 1.0)

    # Adaptive step distances: 1m near, 4m mid-near, 12m mid, 30m far
    d_near = np.arange(1, 120, 1.0)
    d_mid1 = np.arange(120, 600, 4.0)
    d_mid2 = np.arange(600, 2000, 12.0)
    d_far = np.arange(2000, max_dist_m, 30.0)
    distances = np.concatenate([d_near, d_mid1, d_mid2, d_far])

    y_buf = np.full(img_w, img_h, dtype=np.int32)

    # Precompute a small noise texture for dithering (breaks up color bands)
    rng = np.random.RandomState(42)
    noise = rng.uniform(-0.012, 0.012, (img_h, img_w, 3))

    for dist in distances:
        r_f = cam_row + ray_dr * dist
        c_f = cam_col + ray_dc * dist

        # Bounds check (need 1px margin for bilinear)
        valid = (r_f >= 0) & (r_f < h - 1) & (c_f >= 0) & (c_f < w - 1)
        if not valid.any():
            continue

        # Bilinear elevation sampling
        tz = np.full(img_w, cam_z)
        v_idx = np.where(valid)[0]
        tz[v_idx] = _bilerp(dem, r_f[v_idx], c_f[v_idx])

        # Project to screen
        elev = np.degrees(np.arctan2(tz - cam_z, dist))
        scr = ((top_ang - elev) * px_per_deg).astype(np.int32)
        scr = np.clip(scr, 0, img_h)

        draw = valid & (scr < y_buf)
        if not draw.any():
            continue

        dc = np.where(draw)[0]

        # Color: elevation LUT
        te = ((tz[dc] - dem_min) / dem_range).clip(0, 1)
        li = (te * (_LUT_N - 1)).astype(int).clip(0, _LUT_N - 1)
        rgb = _COLOR_LUT[li].copy()

        # Lighting: bilinear-interpolated normals for smooth shading
        nx = -_bilerp_grid(gx, r_f[dc], c_f[dc])
        ny = -_bilerp_grid(gy, r_f[dc], c_f[dc])
        nl = np.sqrt(nx*nx + ny*ny + 1)
        nl[nl == 0] = 1
        diff = ((nx*sun[0] + ny*sun[1] + sun[2]) / nl).clip(0, 1)
        rgb *= (0.35 + 0.65 * diff)[:, None]

        # Fog
        fog = np.clip(1.0 - np.exp(-dist / (max_dist_m * 0.3)), 0, 0.94)
        rgb = rgb * (1 - fog) + _FOG * fog
        rgb = rgb.clip(0, 1)

        # Paint: flat color per strip (no vertical gradient — it causes banding)
        for i, col in enumerate(dc):
            rt = scr[col]
            rb = y_buf[col]
            if rt >= rb:
                continue
            image[rt:rb, col] = rgb[i]
            y_buf[col] = rt

    # Apply noise dithering to break up color bands
    image[:, :] = (image + noise[:img_h, :img_w]).clip(0, 1)

    return image


def _sky(img_h, img_w, pitch, vfov):
    """Sky gradient with warm horizon glow."""
    img = np.zeros((img_h, img_w, 3))
    top_ang = pitch + vfov / 2
    sky_extent = max(top_ang, 0.01)  # how many degrees of sky visible
    for r in range(img_h):
        ang = top_ang - r * vfov / img_h
        if ang > 0:
            t = np.clip(1 - ang / sky_extent, 0, 1)
            glow = max(0, 1 - ang / 4) * 0.12
            c = _SKY_TOP * (1 - t) + _SKY_HOR * t
            c += [glow, glow * 0.5, 0]
            img[r] = np.clip(c, 0, 1)
        else:
            img[r] = _FOG * 0.88
    return img


def _draw_hud(img, yaw, pitch, fov):
    """Compass + horizon HUD."""
    h, w, _ = img.shape
    vfov = fov * h / w
    hud = 18
    img[h - hud:] *= 0.18

    # Horizon
    hr = int((pitch + vfov / 2) / vfov * h) if vfov > 0 else h // 2
    if 0 < hr < h:
        for x in range(0, w, 8):
            img[hr, x:min(x + 3, w)] = 0.35

    # Compass
    hf = fov / 2
    for b in range(0, 360, 5):
        off = ((b - yaw + 180) % 360) - 180
        if abs(off) > hf:
            continue
        col = int((off + hf) / fov * w)
        if col < 0 or col >= w:
            continue
        card = b % 90 == 0
        inter = b % 45 == 0 and not card
        th = 9 if card else (5 if inter else (3 if b % 15 == 0 else 1))
        br = 1.0 if card else (0.6 if inter else 0.25)
        img[h - hud:h - hud + th, col:col + 1] = br


# ── Overview ──────────────────────────────────────────────

def render_overview(dem, res_m, camera_positions,
                    render_id="overview", width=800, height=500):
    """Bird's-eye hillshade with camera markers."""
    try:
        h, w = dem.shape
        step = max(1, max(h, w) // 300)
        ds = dem[::step, ::step]
        dh, dw = ds.shape

        ls = LightSource(azdeg=315, altdeg=40)
        rgb = ls.shade(ds, cmap=TERRAIN_CMAP, blend_mode='soft',
                       vert_exag=3, dx=res_m * step, dy=res_m * step)

        dpi = 100
        fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
        ax.imshow(rgb, aspect='equal', interpolation='bilinear')

        for i, (row, col, z, yaw) in enumerate(camera_positions):
            pr, pc = row / step, col / step
            if 0 <= pr < dh and 0 <= pc < dw:
                cr = min(dh, dw) * 0.04
                ax.add_patch(Wedge((pc, pr), cr, 90 - yaw - 30, 90 - yaw + 30,
                                   alpha=0.4, facecolor='#e8c170', edgecolor='none'))
                ax.plot(pc, pr, 'o', color='white', markersize=5,
                        markeredgecolor='#2c2a25', markeredgewidth=1.5, zorder=10)
                ax.text(pc + 4, pr - 4, f'#{i+1}', fontsize=6, fontweight='bold',
                        color='white', zorder=11,
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='#2c2a25',
                                  alpha=0.7, edgecolor='none'))

        ax.set_xlim(0, dw); ax.set_ylim(dh, 0); ax.set_axis_off()
        fig.patch.set_facecolor('#2c2a25')
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        filename = f"{render_id}.png"
        fig.savefig(os.path.join(RENDER_DIR, filename), bbox_inches='tight',
                    pad_inches=0.02, facecolor=fig.get_facecolor(), dpi=dpi)
        plt.close(fig)
        log.info(f"Rendered overview → {filename}")
        return filename
    except Exception as e:
        log.error(f"Overview render failed: {e}")
        plt.close('all')
        return None


def get_render_path(filename):
    return os.path.join(RENDER_DIR, filename)
