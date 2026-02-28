"""
Composition templates: define where features should appear on screen.
Each template produces (feature_index, screen_x, screen_y) assignments
plus a desired horizon position.

These constraints feed into the inverse PnP solver.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class CompositionTemplate:
    """A composition rule defining desired screen positions."""
    name: str
    # List of (feature_index, normalized_x, normalized_y)
    # where 0,0 = top-left and 1,1 = bottom-right
    feature_placements: List[Tuple[int, float, float]]
    # Horizon position: 0.0 = top, 0.5 = center, 1.0 = bottom
    horizon_y: float
    # Minimum number of features required
    min_features: int
    description: str


# Standard composition templates
COMPOSITION_TEMPLATES = [
    # Rule of Thirds — 4 power point variants
    CompositionTemplate(
        name="thirds_upper_right",
        feature_placements=[(0, 2 / 3, 1 / 3)],
        horizon_y=1 / 3,
        min_features=1,
        description="Primary feature at upper-right power point",
    ),
    CompositionTemplate(
        name="thirds_upper_left",
        feature_placements=[(0, 1 / 3, 1 / 3)],
        horizon_y=1 / 3,
        min_features=1,
        description="Primary feature at upper-left power point",
    ),
    CompositionTemplate(
        name="thirds_lower_right",
        feature_placements=[(0, 2 / 3, 2 / 3)],
        horizon_y=2 / 3,
        min_features=1,
        description="Primary feature at lower-right power point",
    ),
    CompositionTemplate(
        name="thirds_lower_left",
        feature_placements=[(0, 1 / 3, 2 / 3)],
        horizon_y=2 / 3,
        min_features=1,
        description="Primary feature at lower-left power point",
    ),
    # Two features on opposite thirds
    CompositionTemplate(
        name="thirds_diagonal",
        feature_placements=[(0, 2 / 3, 1 / 3), (1, 1 / 3, 2 / 3)],
        horizon_y=0.5,
        min_features=2,
        description="Primary upper-right, secondary lower-left",
    ),

    # Golden Ratio — phi intersections
    CompositionTemplate(
        name="golden_upper_right",
        feature_placements=[(0, 0.618, 0.382)],
        horizon_y=0.382,
        min_features=1,
        description="Primary at golden ratio upper-right",
    ),
    CompositionTemplate(
        name="golden_lower_left",
        feature_placements=[(0, 0.382, 0.618)],
        horizon_y=0.618,
        min_features=1,
        description="Primary at golden ratio lower-left",
    ),
    CompositionTemplate(
        name="golden_diagonal",
        feature_placements=[(0, 0.618, 0.382), (1, 0.382, 0.618)],
        horizon_y=0.5,
        min_features=2,
        description="Two features at golden ratio diagonals",
    ),

    # Centered / Symmetry
    CompositionTemplate(
        name="centered",
        feature_placements=[(0, 0.5, 0.4)],
        horizon_y=0.6,
        min_features=1,
        description="Primary feature centered, low horizon for sky drama",
    ),
    CompositionTemplate(
        name="symmetry",
        feature_placements=[(0, 0.35, 0.4), (1, 0.65, 0.4)],
        horizon_y=0.5,
        min_features=2,
        description="Two features symmetric about center",
    ),

    # Leading line — feature at vanishing point
    CompositionTemplate(
        name="leading_line_center",
        feature_placements=[(0, 0.5, 1 / 3)],
        horizon_y=1 / 3,
        min_features=1,
        description="Subject at vanishing point, camera behind leading element",
    ),

    # Dramatic low horizon (big sky)
    CompositionTemplate(
        name="big_sky",
        feature_placements=[(0, 0.5, 0.75)],
        horizon_y=0.75,
        min_features=1,
        description="Feature low in frame, emphasizing sky/atmosphere",
    ),

    # High horizon (foreground emphasis)
    CompositionTemplate(
        name="foreground_emphasis",
        feature_placements=[(0, 0.5, 0.25)],
        horizon_y=0.25,
        min_features=1,
        description="Feature high, camera tilted down showing foreground",
    ),
]


def get_templates_for_scene(n_features: int) -> List[CompositionTemplate]:
    """Return composition templates that work with the given number of features."""
    return [t for t in COMPOSITION_TEMPLATES if t.min_features <= n_features]
