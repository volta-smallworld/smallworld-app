"""Static composition template registry for camera placement.

Each template defines named target placements in normalised image coordinates,
a horizon ratio, and a solver type.  Helper functions match templates to scene
types and select anchor features from extracted terrain data.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TargetPlacement:
    """A named placement in normalised image coordinates."""

    role: str  # e.g. "primary", "secondary", "left", "right", "line", "subject"
    xNorm: float
    yNorm: float


@dataclass
class CompositionTemplate:
    """Describes a photographic composition layout."""

    name: str  # e.g. "ruleOfThirds_A"
    composition: str  # "ruleOfThirds", "goldenRatio", "leadingLine", "symmetry"
    eligible_scene_types: list[str]
    targets: list[TargetPlacement]
    horizon_ratio: float
    solver_type: str  # "pnp" or "leading_line"


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

_ALL_COMMON_SCENES = [
    "peak-ridge",
    "peak-water",
    "cliff-water",
    "multi-peak",
    "mixed-terrain",
]

TEMPLATES: list[CompositionTemplate] = [
    # ── Rule of thirds ────────────────────────────────────────────────────
    CompositionTemplate(
        name="ruleOfThirds_A",
        composition="ruleOfThirds",
        eligible_scene_types=list(_ALL_COMMON_SCENES),
        targets=[
            TargetPlacement(role="primary", xNorm=0.667, yNorm=0.333),
            TargetPlacement(role="secondary", xNorm=0.333, yNorm=0.667),
        ],
        horizon_ratio=0.333,
        solver_type="pnp",
    ),
    CompositionTemplate(
        name="ruleOfThirds_B",
        composition="ruleOfThirds",
        eligible_scene_types=list(_ALL_COMMON_SCENES),
        targets=[
            TargetPlacement(role="primary", xNorm=0.333, yNorm=0.333),
            TargetPlacement(role="secondary", xNorm=0.667, yNorm=0.667),
        ],
        horizon_ratio=0.333,
        solver_type="pnp",
    ),
    # ── Golden ratio ──────────────────────────────────────────────────────
    CompositionTemplate(
        name="goldenRatio_A",
        composition="goldenRatio",
        eligible_scene_types=list(_ALL_COMMON_SCENES),
        targets=[
            TargetPlacement(role="primary", xNorm=0.618, yNorm=0.382),
            TargetPlacement(role="secondary", xNorm=0.382, yNorm=0.618),
        ],
        horizon_ratio=0.382,
        solver_type="pnp",
    ),
    CompositionTemplate(
        name="goldenRatio_B",
        composition="goldenRatio",
        eligible_scene_types=list(_ALL_COMMON_SCENES),
        targets=[
            TargetPlacement(role="primary", xNorm=0.382, yNorm=0.382),
            TargetPlacement(role="secondary", xNorm=0.618, yNorm=0.618),
        ],
        horizon_ratio=0.382,
        solver_type="pnp",
    ),
    # ── Leading line ──────────────────────────────────────────────────────
    CompositionTemplate(
        name="leadingLine",
        composition="leadingLine",
        eligible_scene_types=list(_ALL_COMMON_SCENES),
        targets=[
            TargetPlacement(role="subject", xNorm=0.618, yNorm=0.382),
        ],
        horizon_ratio=0.45,
        solver_type="leading_line",
    ),
    # ── Symmetry ──────────────────────────────────────────────────────────
    CompositionTemplate(
        name="symmetry",
        composition="symmetry",
        eligible_scene_types=["multi-peak", "mixed-terrain"],
        targets=[
            TargetPlacement(role="left", xNorm=0.35, yNorm=0.5),
            TargetPlacement(role="right", xNorm=0.65, yNorm=0.5),
        ],
        horizon_ratio=0.5,
        solver_type="pnp",
    ),
]


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_templates_for_composition(composition: str) -> list[CompositionTemplate]:
    """Return all templates matching the given composition name."""
    return [t for t in TEMPLATES if t.composition == composition]


def get_eligible_templates(
    scene_type: str, compositions: list[str]
) -> list[CompositionTemplate]:
    """Return templates where *scene_type* is eligible AND composition is requested."""
    return [
        t
        for t in TEMPLATES
        if scene_type in t.eligible_scene_types and t.composition in compositions
    ]


# ---------------------------------------------------------------------------
# Anchor selection
# ---------------------------------------------------------------------------


def _top_points_by_kind(
    points: list[dict], kind: str, n: int = 1
) -> list[dict]:
    """Return the top *n* point features of a given kind (e.g. 'peak', 'cliff').

    The input list is assumed to be pre-sorted by score desc then id asc.
    """
    return [p for p in points if p.get("id", "").startswith(f"{kind}-")][:n]


def select_anchors(
    scene_features: dict, template: CompositionTemplate
) -> dict[str, dict] | None:
    """Select anchor features for *template* from *scene_features*.

    *scene_features* has keys:
      - ``"points"``: list of point features (peaks + cliffs, sorted by score
        desc then id asc)
      - ``"lines"``: list of line features (ridges + water channels, sorted by
        score desc then id asc)

    Returns a dict mapping role names to feature dicts, or ``None`` if the
    template cannot be satisfied.
    """
    points: list[dict] = scene_features.get("points", [])
    lines: list[dict] = scene_features.get("lines", [])

    comp = template.composition

    # ── ruleOfThirds / goldenRatio ─────────────────────────────────────
    if comp in ("ruleOfThirds", "goldenRatio"):
        if not points:
            return None

        primary = points[0]

        # Secondary: prefer top-scoring line midpoint, else second point
        secondary: dict | None = None
        if lines:
            secondary = lines[0]
        elif len(points) >= 2:
            secondary = points[1]

        if secondary is None:
            return None

        return {"primary": primary, "secondary": secondary}

    # ── leadingLine ───────────────────────────────────────────────────
    if comp == "leadingLine":
        # Line: highest-scoring ridge, else highest-scoring water channel
        ridges = [ln for ln in lines if ln.get("id", "").startswith("ridge-")]
        waters = [ln for ln in lines if ln.get("id", "").startswith("water-")]
        line_feat = (ridges[0] if ridges else waters[0]) if (ridges or waters) else None

        # Subject: highest-scoring point feature
        subject = points[0] if points else None

        if line_feat is None or subject is None:
            return None

        return {"line": line_feat, "subject": subject}

    # ── symmetry ──────────────────────────────────────────────────────
    if comp == "symmetry":
        peaks = _top_points_by_kind(points, "peak", 2)
        if len(peaks) >= 2:
            pair = peaks[:2]
        else:
            cliffs = _top_points_by_kind(points, "cliff", 2)
            if len(cliffs) >= 2:
                pair = cliffs[:2]
            else:
                return None

        # Sort so the western feature is "left"
        def _lng(feat: dict) -> float:
            center = feat.get("center", {})
            return center.get("lng", 0.0)

        pair.sort(key=_lng)
        return {"left": pair[0], "right": pair[1]}

    return None
