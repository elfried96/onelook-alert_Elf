import numpy as np

from onelook.data.splits import assign_zones, haversine_km, spatial_zones


def test_haversine_one_degree_of_latitude():
    assert abs(haversine_km(0, 0, 1, 0) - 111.2) < 0.5


def test_neighbours_chain_into_one_zone_far_tiles_do_not():
    # trois tuiles à 5 km de proche en proche, une quatrième à 100 km
    lat = [34.0, 34.045, 34.09, 35.0]
    zones = spatial_zones(lat, [-118.0] * 4, max_km=10)
    assert zones[0] == zones[1] == zones[2] != zones[3]


def test_each_zone_goes_to_a_single_split_with_balanced_positives():
    zones = np.repeat(np.arange(10), 10)
    positives = np.ones(100, bool)
    out = assign_zones(zones, positives, {"train": 0.6, "val": 0.2, "test": 0.2})
    assert set(out) == set(range(10))
    counts = {s: list(out.values()).count(s) for s in ("train", "val", "test")}
    assert counts == {"train": 6, "val": 2, "test": 2}
