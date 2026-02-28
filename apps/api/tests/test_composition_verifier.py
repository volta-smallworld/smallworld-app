from smallworld_api.models.previews import (
    CompositionAnchor,
    CompositionTemplate,
    VerificationStatus,
)
from smallworld_api.services.composition_verifier import verify_composition

# Shared camera parameters for tests that need valid projection
CAM = dict(
    camera_lat=39.7392,
    camera_lng=-104.9903,
    camera_alt_meters=2450,
    heading_deg=0,
    pitch_deg=-10,
    roll_deg=0,
    fov_deg=50,
    viewport_width=1536,
    viewport_height=1024,
)


def _anchor(**overrides):
    defaults = dict(
        id="peak-1",
        lat=39.745,
        lng=-104.990,
        altMeters=1800,
        desiredNormalizedX=0.5,
        desiredNormalizedY=0.5,
    )
    defaults.update(overrides)
    return CompositionAnchor(**defaults)


def test_no_anchors_returns_skipped():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.RULE_OF_THIRDS,
        anchors=None,
        horizon_ratio=None,
    )
    assert result.status == VerificationStatus.SKIPPED


def test_empty_anchors_returns_skipped():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.RULE_OF_THIRDS,
        anchors=[],
        horizon_ratio=None,
    )
    assert result.status == VerificationStatus.SKIPPED


def test_leading_line_returns_unsupported():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.LEADING_LINE,
        anchors=[_anchor()],
        horizon_ratio=None,
    )
    assert result.status == VerificationStatus.UNSUPPORTED_TEMPLATE


def test_rule_of_thirds_with_anchor():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.RULE_OF_THIRDS,
        anchors=[_anchor(desiredNormalizedX=0.5, desiredNormalizedY=0.5)],
        horizon_ratio=None,
    )
    assert result.status in (VerificationStatus.VERIFIED, VerificationStatus.FAILED)
    assert isinstance(result.meanAnchorErrorPx, float)


def test_golden_ratio_supported():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.GOLDEN_RATIO,
        anchors=[_anchor()],
        horizon_ratio=None,
    )
    assert result.status != VerificationStatus.UNSUPPORTED_TEMPLATE


def test_symmetry_supported():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.SYMMETRY,
        anchors=[_anchor()],
        horizon_ratio=None,
    )
    assert result.status != VerificationStatus.UNSUPPORTED_TEMPLATE


def test_custom_with_anchors():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.CUSTOM,
        anchors=[_anchor()],
        horizon_ratio=None,
    )
    assert result.status != VerificationStatus.SKIPPED


def test_source_is_geometry_projection_v1():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.RULE_OF_THIRDS,
        anchors=[_anchor()],
        horizon_ratio=None,
    )
    assert result.source == "geometry_projection_v1"


def test_horizon_ratio_included():
    result = verify_composition(
        **CAM,
        template=CompositionTemplate.RULE_OF_THIRDS,
        anchors=[_anchor()],
        horizon_ratio=0.33,
    )
    assert result.horizonErrorPx is not None
    assert isinstance(result.horizonErrorPx, float)
