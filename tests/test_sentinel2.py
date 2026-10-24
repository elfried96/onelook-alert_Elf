import numpy as np
import pytest

from onelook.data import sources
from onelook.data.sentinel2 import BANDS_L1C, BANDS_L2A, band_names, get_bands, natural_color, nbr, ndwi


def image_with(values: dict[str, float], bands: list[str], size: int = 4) -> np.ndarray:
    """Image synthétique où chaque bande nommée a une réflectance constante."""
    image = np.zeros((len(bands), size, size), dtype=np.int16)
    for name, reflectance in values.items():
        image[bands.index(name)] = int(reflectance * 10_000)
    return image


def test_band_names_follow_processing_level():
    assert band_names(13) == BANDS_L1C
    assert band_names(12) == BANDS_L2A
    with pytest.raises(ValueError):
        band_names(6)


def test_get_bands_finds_same_band_in_l1c_and_l2a():
    l1c = image_with({"B12": 0.3}, BANDS_L1C)
    l2a = image_with({"B12": 0.3}, BANDS_L2A)
    assert get_bands(l1c, ["B12"])[0, 0, 0] == pytest.approx(0.3)
    assert get_bands(l2a, ["B12"])[0, 0, 0] == pytest.approx(0.3)


def test_ndwi_positive_on_water_negative_on_vegetation():
    water = image_with({"B03": 0.08, "B08": 0.02}, BANDS_L1C)
    vegetation = image_with({"B03": 0.06, "B08": 0.40}, BANDS_L1C)
    assert ndwi(water).mean() == pytest.approx(0.6)
    assert ndwi(vegetation).mean() < 0


def test_nbr_low_on_burned_soil():
    burned = image_with({"B08": 0.12, "B12": 0.25}, BANDS_L2A)
    healthy = image_with({"B08": 0.35, "B12": 0.10}, BANDS_L2A)
    assert nbr(burned).mean() < 0 < nbr(healthy).mean()


def test_indices_are_zero_where_no_data():
    empty = np.zeros((13, 4, 4), dtype=np.int16)
    assert np.all(ndwi(empty) == 0)


def test_natural_color_shape_and_range():
    rng = np.random.default_rng(0)
    image = rng.integers(0, 5000, size=(13, 8, 8)).astype(np.int16)
    rgb = natural_color(image)
    assert rgb.shape == (8, 8, 3)
    assert rgb.min() >= 0 and rgb.max() <= 1


def test_flood_stats_excludes_permanent_water_and_nodata():
    label = np.array([[1, 1], [0, -1]])
    permanent = np.array([[1, 0], [0, 0]])
    s = sources.flood_stats(label, permanent)
    assert s["valid"] == pytest.approx(0.75)
    assert s["water"] == pytest.approx(2 / 3)
    assert s["permanent"] == pytest.approx(1 / 3)
    assert s["flood"] == pytest.approx(1 / 3)
