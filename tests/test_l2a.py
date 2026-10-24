import numpy as np
import pytest

from onelook.data import l2a


class FakeItem:
    def __init__(self, baseline: str):
        self.properties = {"s2:processing_baseline": baseline}


def test_boa_offset_only_since_baseline_04():
    assert l2a.boa_offset(FakeItem("02.12")) == 0
    assert l2a.boa_offset(FakeItem("03.01")) == 0
    assert l2a.boa_offset(FakeItem("04.00")) == 1000
    assert l2a.boa_offset(FakeItem("05.10")) == 1000


def test_centered_grid_is_512_pixels_of_10_m_in_utm():
    grid = l2a.Grid.centered(lon=2.39, lat=6.37)  # Cotonou
    assert grid.crs == "EPSG:32631"
    assert (grid.width, grid.height) == (512, 512)
    left, bottom, right, top = grid.bounds
    assert right - left == pytest.approx(5120)
    assert top - bottom == pytest.approx(5120)
    assert left % 10 == 0 and top % 10 == 0


def test_centered_grid_contains_its_center():
    west, south, east, north = l2a.Grid.centered(lon=-62.22, lat=-3.47).bounds_wgs84()
    assert west < -62.22 < east
    assert south < -3.47 < north
    assert l2a.Grid.centered(lon=-62.22, lat=-3.47).crs == "EPSG:32720"


def test_scl_fractions():
    scl = np.array([[l2a.SCL_WATER, l2a.SCL_CLOUD_HIGH], [l2a.SCL_SHADOW, l2a.SCL_VEGETATION]], dtype=np.uint8)
    f = l2a.scl_fractions(scl)
    assert f["water"] == pytest.approx(0.25)
    assert f["cloud"] == pytest.approx(0.5)
    assert f["no_data"] == 0
