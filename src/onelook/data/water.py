"""Eau permanente (océans, lacs, cours d'eau) d'après JRC Global Surface Water, lue sur Planetary Computer.

Sert aux étiquettes et à l'évaluation, pas d'entrée au modèle : savoir si l'eau vue sur une tuile est
habituelle (mer, fleuve dans son lit) ou inattendue (inondation possible).
"""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from onelook.data.l2a import GDAL_ENV, SCL_WATER, Grid, _search_items

COLLECTION = "jrc-gsw"
# Part des observations 1984-2020 où le pixel était sous l'eau. 50 % reproduit le mieux la couche
# « eau permanente » de Sen1Floods11 (IoU 0,90 sur 40 tuiles, contre 0,76 au mieux pour les autres seuils).
PERMANENT_MIN_OCCURRENCE = 50
# Hors de la couverture terrestre de JRC : la pleine mer.
NO_DATA = 255


def read_occurrence(grid: Grid) -> np.ndarray:
    """Occurrence de l'eau (0-100 %, NO_DATA en pleine mer) sur la grille de la tuile."""
    items = _search_items(COLLECTION, bbox=grid.bounds_wgs84())
    occurrence = np.full((grid.height, grid.width), NO_DATA, dtype=np.uint8)
    with rasterio.Env(**GDAL_ENV):
        for item in items:
            with rasterio.open(item.assets["occurrence"].href) as src, WarpedVRT(
                src, crs=grid.crs, transform=grid.transform, width=grid.width, height=grid.height,
                resampling=Resampling.nearest, nodata=NO_DATA,
            ) as vrt:
                tile = vrt.read(1)
            fill = (occurrence == NO_DATA) & (tile != NO_DATA)
            occurrence[fill] = tile[fill]
    return occurrence


def permanent_water(occurrence: np.ndarray) -> np.ndarray:
    """Masque de l'eau permanente : eau au moins la moitié du temps, ou pleine mer."""
    return (occurrence == NO_DATA) | ((occurrence >= PERMANENT_MIN_OCCURRENCE) & (occurrence <= 100))


def water_stats(occurrence: np.ndarray, scl: np.ndarray) -> dict[str, float]:
    """Part de la tuile en eau permanente, et part d'eau vue par la SCL hors de l'eau permanente."""
    permanent = permanent_water(occurrence)
    seen = scl == SCL_WATER
    return {
        "frac_permanent_jrc": round(float(permanent.mean()), 4),
        "scl_water_outside_jrc": round(float((seen & ~permanent).mean()), 4),
    }
