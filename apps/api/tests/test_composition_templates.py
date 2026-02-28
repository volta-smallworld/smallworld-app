from smallworld_api.services.composition_templates import (
    TEMPLATES,
    CompositionTemplate,
    TargetPlacement,
    get_templates_for_composition,
    get_eligible_templates,
    select_anchors,
)


# ---------------------------------------------------------------------------
# TEMPLATES registry
# ---------------------------------------------------------------------------


def test_templates_has_expected_length():
    assert len(TEMPLATES) == 6


def test_templates_cover_all_compositions():
    compositions = {t.composition for t in TEMPLATES}
    assert compositions == {"ruleOfThirds", "goldenRatio", "leadingLine", "symmetry"}


def test_all_templates_have_valid_solver_type():
    for t in TEMPLATES:
        assert t.solver_type in ("pnp", "leading_line")


def test_all_templates_have_at_least_one_target():
    for t in TEMPLATES:
        assert len(t.targets) >= 1


def test_all_templates_have_at_least_one_eligible_scene_type():
    for t in TEMPLATES:
        assert len(t.eligible_scene_types) >= 1


# ---------------------------------------------------------------------------
# get_templates_for_composition
# ---------------------------------------------------------------------------


def test_get_templates_for_rule_of_thirds():
    result = get_templates_for_composition("ruleOfThirds")
    assert len(result) == 2
    assert all(t.composition == "ruleOfThirds" for t in result)
    names = {t.name for t in result}
    assert names == {"ruleOfThirds_A", "ruleOfThirds_B"}


def test_get_templates_for_symmetry():
    result = get_templates_for_composition("symmetry")
    assert len(result) == 1
    assert result[0].name == "symmetry"
    assert result[0].composition == "symmetry"


def test_get_templates_for_golden_ratio():
    result = get_templates_for_composition("goldenRatio")
    assert len(result) == 2
    assert all(t.composition == "goldenRatio" for t in result)


def test_get_templates_for_leading_line():
    result = get_templates_for_composition("leadingLine")
    assert len(result) == 1
    assert result[0].name == "leadingLine"


def test_get_templates_for_unknown_returns_empty():
    result = get_templates_for_composition("unknown_composition")
    assert result == []


def test_get_templates_for_empty_string_returns_empty():
    result = get_templates_for_composition("")
    assert result == []


# ---------------------------------------------------------------------------
# get_eligible_templates
# ---------------------------------------------------------------------------


def test_eligible_peak_ridge_with_rule_of_thirds():
    result = get_eligible_templates("peak-ridge", ["ruleOfThirds"])
    assert len(result) == 2
    assert all(t.composition == "ruleOfThirds" for t in result)
    assert all("peak-ridge" in t.eligible_scene_types for t in result)


def test_eligible_multi_peak_with_symmetry():
    result = get_eligible_templates("multi-peak", ["symmetry"])
    assert len(result) == 1
    assert result[0].composition == "symmetry"
    assert result[0].name == "symmetry"


def test_eligible_peak_ridge_with_symmetry_returns_empty():
    # "peak-ridge" is not in symmetry's eligible_scene_types
    result = get_eligible_templates("peak-ridge", ["symmetry"])
    assert result == []


def test_eligible_multi_peak_with_all_compositions():
    result = get_eligible_templates(
        "multi-peak", ["ruleOfThirds", "goldenRatio", "leadingLine", "symmetry"]
    )
    # multi-peak is eligible for all templates (all 6)
    assert len(result) == 6


def test_eligible_unknown_scene_type_returns_empty():
    result = get_eligible_templates("unknown-scene", ["ruleOfThirds"])
    assert result == []


def test_eligible_empty_compositions_returns_empty():
    result = get_eligible_templates("peak-ridge", [])
    assert result == []


def test_eligible_mixed_terrain_with_symmetry():
    result = get_eligible_templates("mixed-terrain", ["symmetry"])
    assert len(result) == 1
    assert result[0].name == "symmetry"


def test_eligible_cliff_water_excludes_symmetry():
    result = get_eligible_templates("cliff-water", ["symmetry"])
    assert result == []


def test_eligible_peak_water_with_multiple_compositions():
    result = get_eligible_templates("peak-water", ["ruleOfThirds", "goldenRatio"])
    assert len(result) == 4  # 2 ruleOfThirds + 2 goldenRatio


# ---------------------------------------------------------------------------
# select_anchors — ruleOfThirds
# ---------------------------------------------------------------------------


def _rot_template() -> CompositionTemplate:
    """Return the first ruleOfThirds template for testing."""
    return get_templates_for_composition("ruleOfThirds")[0]


def test_select_anchors_rot_with_points_and_lines():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
            {"id": "peak-2", "center": {"lat": 39.76, "lng": -104.97}, "score": 0.8},
        ],
        "lines": [
            {"id": "ridge-1", "path": [], "score": 0.85},
        ],
    }
    result = select_anchors(scene, _rot_template())
    assert result is not None
    assert "primary" in result
    assert "secondary" in result
    assert result["primary"]["id"] == "peak-1"
    # Secondary prefers line over second point
    assert result["secondary"]["id"] == "ridge-1"


def test_select_anchors_rot_with_points_no_lines():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
            {"id": "peak-2", "center": {"lat": 39.76, "lng": -104.97}, "score": 0.8},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _rot_template())
    assert result is not None
    assert result["primary"]["id"] == "peak-1"
    # Falls back to second point
    assert result["secondary"]["id"] == "peak-2"


def test_select_anchors_rot_with_single_point_no_lines_returns_none():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _rot_template())
    assert result is None


def test_select_anchors_rot_no_points_returns_none():
    scene = {
        "points": [],
        "lines": [{"id": "ridge-1", "path": [], "score": 0.85}],
    }
    result = select_anchors(scene, _rot_template())
    assert result is None


def test_select_anchors_rot_empty_features_returns_none():
    scene = {"points": [], "lines": []}
    result = select_anchors(scene, _rot_template())
    assert result is None


# ---------------------------------------------------------------------------
# select_anchors — goldenRatio
# ---------------------------------------------------------------------------


def _gr_template() -> CompositionTemplate:
    """Return the first goldenRatio template for testing."""
    return get_templates_for_composition("goldenRatio")[0]


def test_select_anchors_golden_ratio_with_points_and_lines():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
        ],
        "lines": [
            {"id": "ridge-1", "path": [], "score": 0.85},
        ],
    }
    result = select_anchors(scene, _gr_template())
    assert result is not None
    assert "primary" in result
    assert "secondary" in result
    assert result["primary"]["id"] == "peak-1"
    assert result["secondary"]["id"] == "ridge-1"


def test_select_anchors_golden_ratio_with_points_no_lines():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
            {"id": "cliff-1", "center": {"lat": 39.76, "lng": -104.97}, "score": 0.7},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _gr_template())
    assert result is not None
    assert result["primary"]["id"] == "peak-1"
    assert result["secondary"]["id"] == "cliff-1"


def test_select_anchors_golden_ratio_single_point_no_lines_returns_none():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _gr_template())
    assert result is None


# ---------------------------------------------------------------------------
# select_anchors — leadingLine
# ---------------------------------------------------------------------------


def _ll_template() -> CompositionTemplate:
    """Return the leadingLine template for testing."""
    return get_templates_for_composition("leadingLine")[0]


def test_select_anchors_leading_line_with_ridge_and_point():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
        ],
        "lines": [
            {"id": "ridge-1", "path": [], "score": 0.85},
            {"id": "water-1", "path": [], "score": 0.80},
        ],
    }
    result = select_anchors(scene, _ll_template())
    assert result is not None
    assert "line" in result
    assert "subject" in result
    # Prefers ridge over water
    assert result["line"]["id"] == "ridge-1"
    assert result["subject"]["id"] == "peak-1"


def test_select_anchors_leading_line_prefers_ridge_over_water():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
        ],
        "lines": [
            {"id": "water-1", "path": [], "score": 0.95},
            {"id": "ridge-1", "path": [], "score": 0.80},
        ],
    }
    result = select_anchors(scene, _ll_template())
    assert result is not None
    # Ridges are checked first regardless of score ordering in list
    assert result["line"]["id"] == "ridge-1"


def test_select_anchors_leading_line_falls_back_to_water():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
        ],
        "lines": [
            {"id": "water-1", "path": [], "score": 0.80},
        ],
    }
    result = select_anchors(scene, _ll_template())
    assert result is not None
    assert result["line"]["id"] == "water-1"
    assert result["subject"]["id"] == "peak-1"


def test_select_anchors_leading_line_no_lines_returns_none():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _ll_template())
    assert result is None


def test_select_anchors_leading_line_no_points_returns_none():
    scene = {
        "points": [],
        "lines": [
            {"id": "ridge-1", "path": [], "score": 0.85},
        ],
    }
    result = select_anchors(scene, _ll_template())
    assert result is None


def test_select_anchors_leading_line_no_ridge_or_water_prefix_returns_none():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
        ],
        "lines": [
            {"id": "other-1", "path": [], "score": 0.85},
        ],
    }
    result = select_anchors(scene, _ll_template())
    assert result is None


def test_select_anchors_leading_line_empty_returns_none():
    scene = {"points": [], "lines": []}
    result = select_anchors(scene, _ll_template())
    assert result is None


# ---------------------------------------------------------------------------
# select_anchors — symmetry
# ---------------------------------------------------------------------------


def _sym_template() -> CompositionTemplate:
    """Return the symmetry template for testing."""
    return get_templates_for_composition("symmetry")[0]


def test_select_anchors_symmetry_two_peaks():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -105.00}, "score": 0.9},
            {"id": "peak-2", "center": {"lat": 39.76, "lng": -104.90}, "score": 0.8},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _sym_template())
    assert result is not None
    assert "left" in result
    assert "right" in result
    # Sorted by lng: -105.00 < -104.90
    assert result["left"]["id"] == "peak-1"
    assert result["right"]["id"] == "peak-2"


def test_select_anchors_symmetry_sorts_by_longitude():
    # Supply peaks in "wrong" order (eastern first by list position)
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.80}, "score": 0.9},
            {"id": "peak-2", "center": {"lat": 39.76, "lng": -105.20}, "score": 0.8},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _sym_template())
    assert result is not None
    # peak-2 is more western (-105.20 < -104.80)
    assert result["left"]["id"] == "peak-2"
    assert result["right"]["id"] == "peak-1"


def test_select_anchors_symmetry_falls_back_to_cliffs():
    scene = {
        "points": [
            {"id": "cliff-1", "center": {"lat": 39.75, "lng": -105.00}, "score": 0.9},
            {"id": "cliff-2", "center": {"lat": 39.76, "lng": -104.90}, "score": 0.8},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _sym_template())
    assert result is not None
    assert result["left"]["id"] == "cliff-1"
    assert result["right"]["id"] == "cliff-2"


def test_select_anchors_symmetry_prefers_peaks_over_cliffs():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -105.00}, "score": 0.9},
            {"id": "peak-2", "center": {"lat": 39.76, "lng": -104.90}, "score": 0.8},
            {"id": "cliff-1", "center": {"lat": 39.77, "lng": -104.85}, "score": 0.95},
            {"id": "cliff-2", "center": {"lat": 39.78, "lng": -104.80}, "score": 0.90},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _sym_template())
    assert result is not None
    # Should use peaks, not cliffs
    assert result["left"]["id"] == "peak-1"
    assert result["right"]["id"] == "peak-2"


def test_select_anchors_symmetry_one_peak_no_cliffs_returns_none():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -105.00}, "score": 0.9},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _sym_template())
    assert result is None


def test_select_anchors_symmetry_one_peak_one_cliff_returns_none():
    # Not enough of either kind to form a pair
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -105.00}, "score": 0.9},
            {"id": "cliff-1", "center": {"lat": 39.76, "lng": -104.90}, "score": 0.8},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _sym_template())
    assert result is None


def test_select_anchors_symmetry_no_points_returns_none():
    scene = {"points": [], "lines": []}
    result = select_anchors(scene, _sym_template())
    assert result is None


def test_select_anchors_symmetry_non_peak_non_cliff_returns_none():
    scene = {
        "points": [
            {"id": "other-1", "center": {"lat": 39.75, "lng": -105.00}, "score": 0.9},
            {"id": "other-2", "center": {"lat": 39.76, "lng": -104.90}, "score": 0.8},
        ],
        "lines": [],
    }
    result = select_anchors(scene, _sym_template())
    assert result is None


# ---------------------------------------------------------------------------
# select_anchors — unknown composition
# ---------------------------------------------------------------------------


def test_select_anchors_unknown_composition_returns_none():
    template = CompositionTemplate(
        name="unknown",
        composition="unknownComp",
        eligible_scene_types=["peak-ridge"],
        targets=[TargetPlacement(role="primary", xNorm=0.5, yNorm=0.5)],
        horizon_ratio=0.5,
        solver_type="pnp",
    )
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -105.00}, "score": 0.9},
        ],
        "lines": [
            {"id": "ridge-1", "path": [], "score": 0.85},
        ],
    }
    result = select_anchors(scene, template)
    assert result is None


# ---------------------------------------------------------------------------
# select_anchors — missing keys in scene_features
# ---------------------------------------------------------------------------


def test_select_anchors_missing_points_key():
    scene = {"lines": [{"id": "ridge-1", "path": [], "score": 0.85}]}
    result = select_anchors(scene, _rot_template())
    assert result is None


def test_select_anchors_missing_lines_key():
    scene = {
        "points": [
            {"id": "peak-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9},
            {"id": "peak-2", "center": {"lat": 39.76, "lng": -104.97}, "score": 0.8},
        ],
    }
    result = select_anchors(scene, _rot_template())
    assert result is not None
    # Falls back to second point since lines is empty by default
    assert result["secondary"]["id"] == "peak-2"


def test_select_anchors_empty_dict():
    scene = {}
    result = select_anchors(scene, _rot_template())
    assert result is None
