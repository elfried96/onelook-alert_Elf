"""Lecture à distance d'images Sentinel-2 L2A harmonisées, sur une grille de tuile donnée.

Source unique pour toutes les classes : la collection `sentinel-2-l2a` de Microsoft Planetary Computer.
Elle couvre toute l'archive depuis 2015, en COG publics (accès gratuit, sans compte) :
on ne lit que les octets de la fenêtre utile, sans télécharger les scènes entières.

Depuis la processing baseline 04.00 (janvier 2022), les valeurs stockées valent
(réflectance + 0,1) × 10 000. On retire ce décalage quand il existe pour obtenir partout
réflectance × 10 000, la même convention que `onelook.data.sentinel2`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import planetary_computer
import rasterio
from affine import Affine
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds

from onelook.data.sentinel2 import BANDS_L2A

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"
BOA_OFFSET = 1_000  # décalage ajouté depuis la baseline 04.00 (offset −0,1 en réflectance)

# Classes de la carte SCL (Scene Classification) fournie avec chaque scène L2A
SCL_NO_DATA, SCL_SATURATED, SCL_DARK, SCL_SHADOW = 0, 1, 2, 3
SCL_VEGETATION, SCL_BARE, SCL_WATER, SCL_UNCLASSIFIED = 4, 5, 6, 7
SCL_CLOUD_MEDIUM, SCL_CLOUD_HIGH, SCL_CIRRUS, SCL_SNOW = 8, 9, 10, 11
SCL_CLOUDY = (SCL_SHADOW, SCL_CLOUD_MEDIUM, SCL_CLOUD_HIGH, SCL_CIRRUS)

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "2",
}


@dataclass(frozen=True)
class Grid:
    """Grille cible d'une tuile : système de coordonnées, géotransformation et taille."""

    crs: str
    transform: Affine
    width: int = 512
    height: int = 512

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        left, top = self.transform * (0, 0)
        right, bottom = self.transform * (self.width, self.height)
        return min(left, right), min(top, bottom), max(left, right), max(top, bottom)

    def bounds_wgs84(self) -> tuple[float, float, float, float]:
        return transform_bounds(self.crs, "EPSG:4326", *self.bounds)

    @classmethod
    def from_file(cls, path) -> Grid:
        with rasterio.open(path) as src:
            return cls(src.crs.to_string(), src.transform, src.width, src.height)

    @classmethod
    def centered(cls, lon: float, lat: float, size: int = 512, resolution: float = 10.0) -> Grid:
        """Tuile de `size` × `size` pixels centrée sur un point, dans la zone UTM du point."""
        zone = int((lon + 180) // 6) + 1
        epsg = (32600 if lat >= 0 else 32700) + zone
        from pyproj import Transformer

        x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(lon, lat)
        half = size * resolution / 2
        # Origine alignée sur la grille Sentinel-2 (multiples de la résolution)
        left = np.floor((x - half) / resolution) * resolution
        top = np.floor((y + half) / resolution) * resolution
        return cls(f"EPSG:{epsg}", Affine(resolution, 0, left, 0, -resolution, top), size, size)


def search(grid: Grid, day: date, days_around: int = 0, max_cloud: float = 100):
    """Scènes L2A qui recoupent la tuile, de `day − days_around` à `day + days_around`."""
    start, end = day - timedelta(days=days_around), day + timedelta(days=days_around)
    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = client.search(
        collections=[COLLECTION],
        bbox=grid.bounds_wgs84(),
        datetime=f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    ).item_collection()
    # Les scènes les plus proches de la date, puis les moins nuageuses
    return sorted(
        items,
        key=lambda it: (abs((it.datetime.date() - day).days), it.properties.get("eo:cloud_cover", 100)),
    )


def search_period(grid: Grid, start: date, end: date, min_cloud: float = 0, max_cloud: float = 100):
    """Passages du satellite sur la tuile entre deux dates, regroupés par jour d'acquisition.

    Une tuile peut chevaucher plusieurs scènes d'un même passage : chaque groupe se mosaïque
    sans mélanger des dates différentes. Groupes triés du moins au plus nuageux.
    """
    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = client.search(
        collections=[COLLECTION],
        bbox=grid.bounds_wgs84(),
        datetime=f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        query={"eo:cloud_cover": {"gte": min_cloud, "lte": max_cloud}},
    ).item_collection()
    by_day: dict[date, list] = {}
    for item in items:
        by_day.setdefault(item.datetime.date(), []).append(item)
    groups = [sorted(g, key=lambda it: it.properties.get("eo:cloud_cover", 100)) for g in by_day.values()]
    return sorted(groups, key=lambda g: min(it.properties.get("eo:cloud_cover", 100) for it in g))


def boa_offset(item) -> int:
    """Décalage à retirer selon la processing baseline de la scène."""
    baseline = item.properties.get("s2:processing_baseline", "00.00")
    return BOA_OFFSET if float(baseline) >= 4.0 else 0


def _read_asset(href: str, grid: Grid, resampling: Resampling) -> np.ndarray:
    with rasterio.open(href) as src, WarpedVRT(
        src, crs=grid.crs, transform=grid.transform, width=grid.width, height=grid.height,
        resampling=resampling, src_nodata=0, nodata=0,
    ) as vrt:
        return vrt.read(1)


def read_tile(items, grid: Grid, bands: list[str] = BANDS_L2A) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Lit les bandes et la carte SCL sur la grille, en mosaïquant les scènes si la tuile en chevauche plusieurs.

    Retourne (image (bandes, H, W) en réflectance × 10 000, scl (H, W), identifiants des scènes utilisées).
    """
    image = np.zeros((len(bands), grid.height, grid.width), dtype=np.uint16)
    scl = np.zeros((grid.height, grid.width), dtype=np.uint8)
    used = []
    with rasterio.Env(**GDAL_ENV):
        for item in items:
            missing = scl == SCL_NO_DATA
            if not missing.any():
                break
            item_scl = _read_asset(item.assets["SCL"].href, grid, Resampling.nearest)
            fill = missing & (item_scl != SCL_NO_DATA)
            if not fill.any():
                continue
            scl[fill] = item_scl[fill]
            offset = boa_offset(item)
            for i, band in enumerate(bands):
                raw = _read_asset(item.assets[band].href, grid, Resampling.bilinear).astype(np.int32)
                image[i][fill] = np.clip(raw - offset, 0, None)[fill]
            used.append(item.id)
    return image, scl, used


def scl_fractions(scl: np.ndarray) -> dict[str, float]:
    """Parts de la tuile : sans donnée, nuages et ombres, eau, neige, d'après la carte SCL."""
    n = scl.size
    return {
        "no_data": float((scl == SCL_NO_DATA).sum() / n),
        "cloud": float(np.isin(scl, SCL_CLOUDY).sum() / n),
        "water": float((scl == SCL_WATER).sum() / n),
        "snow": float((scl == SCL_SNOW).sum() / n),
    }


def write_tile(path, image: np.ndarray, grid: Grid, bands: list[str] = BANDS_L2A, scl: np.ndarray | None = None) -> None:
    """Enregistre la tuile en GeoTIFF multibande (et la carte SCL à côté si fournie)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="GTiff", width=grid.width, height=grid.height, crs=grid.crs,
                   transform=grid.transform, compress="deflate", tiled=True)
    with rasterio.open(path, "w", count=len(bands), dtype="uint16", nodata=0, **profile) as dst:
        dst.write(image)
        for i, name in enumerate(bands, start=1):
            dst.set_band_description(i, name)
    if scl is not None:
        with rasterio.open(path.with_name(path.stem + "_SCL.tif"), "w", count=1, dtype="uint8", nodata=0, **profile) as dst:
            dst.write(scl, 1)
