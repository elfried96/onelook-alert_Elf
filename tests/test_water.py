import numpy as np

from onelook.data.l2a import SCL_VEGETATION, SCL_WATER
from onelook.data.water import NO_DATA, permanent_water, water_stats


def test_open_sea_and_frequent_water_are_permanent():
    occurrence = np.array([[NO_DATA, 100, 50], [49, 10, 0]], dtype=np.uint8)
    assert permanent_water(occurrence).tolist() == [[True, True, True], [False, False, False]]


def test_water_seen_outside_permanent_water_is_counted():
    # moitié gauche : fleuve permanent ; moitié droite : terre habituellement sèche, sous l'eau sur l'image
    occurrence = np.zeros((4, 4), dtype=np.uint8)
    occurrence[:, :2] = 90
    scl = np.full((4, 4), SCL_WATER, dtype=np.uint8)
    scl[:, 3] = SCL_VEGETATION
    stats = water_stats(occurrence, scl)
    assert stats == {"frac_permanent_jrc": 0.5, "scl_water_outside_jrc": 0.25}
