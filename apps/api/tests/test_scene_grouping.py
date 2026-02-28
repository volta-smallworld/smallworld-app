from smallworld_api.services.scenes import group_scenes


def test_peak_ridge_yields_scene():
    hotspots = [
        {"id": "hotspot-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9, "reasons": ["peaks"]},
    ]
    features = {
        "peaks": [
            {"id": "peak-1", "center": {"lat": 39.751, "lng": -104.981}, "score": 0.85},
        ],
        "ridges": [
            {"id": "ridge-1", "path": [{"lat": 39.749, "lng": -104.979}], "lengthMetersApprox": 1000, "score": 0.8},
        ],
        "cliffs": [],
        "waterChannels": [],
    }
    scenes = group_scenes(hotspots, features)
    assert len(scenes) >= 1
    assert scenes[0]["type"] == "peak-ridge"
    assert "peak-1" in scenes[0]["featureIds"]
    assert "ridge-1" in scenes[0]["featureIds"]


def test_distant_clusters_do_not_merge():
    hotspots = [
        {"id": "hotspot-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9, "reasons": []},
        {"id": "hotspot-2", "center": {"lat": 40.50, "lng": -105.80}, "score": 0.8, "reasons": []},
    ]
    features = {
        "peaks": [
            {"id": "peak-1", "center": {"lat": 39.751, "lng": -104.981}, "score": 0.85},
            {"id": "peak-2", "center": {"lat": 40.501, "lng": -105.801}, "score": 0.80},
        ],
        "ridges": [
            {"id": "ridge-1", "path": [{"lat": 39.749, "lng": -104.979}], "lengthMetersApprox": 1000, "score": 0.8},
            {"id": "ridge-2", "path": [{"lat": 40.499, "lng": -105.799}], "lengthMetersApprox": 1000, "score": 0.7},
        ],
        "cliffs": [],
        "waterChannels": [],
    }
    scenes = group_scenes(hotspots, features)
    # Should get two separate scenes, not one merged one
    assert len(scenes) >= 2
    ids_0 = set(scenes[0]["featureIds"])
    ids_1 = set(scenes[1]["featureIds"])
    assert ids_0 & ids_1 == set()  # No shared features


def test_duplicate_hotspots_dedup():
    hotspots = [
        {"id": "hotspot-1", "center": {"lat": 39.75, "lng": -104.98}, "score": 0.9, "reasons": []},
        {"id": "hotspot-2", "center": {"lat": 39.7501, "lng": -104.9801}, "score": 0.85, "reasons": []},
    ]
    features = {
        "peaks": [
            {"id": "peak-1", "center": {"lat": 39.751, "lng": -104.981}, "score": 0.85},
        ],
        "ridges": [
            {"id": "ridge-1", "path": [{"lat": 39.749, "lng": -104.979}], "lengthMetersApprox": 1000, "score": 0.8},
        ],
        "cliffs": [],
        "waterChannels": [],
    }
    scenes = group_scenes(hotspots, features)
    # Should dedup to one scene since hotspots are nearly identical
    assert len(scenes) == 1
