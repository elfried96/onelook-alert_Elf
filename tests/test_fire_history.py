from affine import Affine
from rasterio.warp import transform_bounds

from onelook.data.fire_history import history_stats
from onelook.data.l2a import Grid

# Tuile de 5,12 km en UTM 10N, en Californie
GRID = Grid("EPSG:32610", Affine(10, 0, 600_000, 0, -10, 4_200_000))


def fire(year: int, left_share: float) -> dict:
    """Feu couvrant la part left_share de la tuile, côté ouest."""
    x0, y0, x1, y1 = 599_000, 4_194_880, 600_000 + 5120 * left_share, 4_201_000
    west, south, east, north = transform_bounds("EPSG:32610", "EPSG:4326", x0, y0, x1, y1)
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"year": year, "name": f"F{year}", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "bbox": (west, south, east, north)}


def test_history_counts_fires_by_age():
    stats = history_stats(GRID, [fire(2018, 0.25), fire(2020, 0.5), fire(2010, 1.0)], image_year=2020)
    assert abs(stats["frac_fire_0y"] - 0.5) < 0.03  # feu de l'année de l'image
    assert abs(stats["frac_fire_1y"] - 0.5) < 0.03
    assert abs(stats["frac_fire_2y"] - 0.5) < 0.03  # le feu de 2018 est sous celui de 2020
    assert stats["frac_fire_5y"] < 0.53  # le feu de 2010 est trop ancien
    assert stats["fire_history_names"] == "F2018 2018;F2020 2020"


def test_later_fires_are_ignored():
    assert history_stats(GRID, [fire(2021, 1.0)], image_year=2020)["frac_fire_5y"] == 0
