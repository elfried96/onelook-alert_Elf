"""Historique des périmètres de feux (NIFC, InterAgency Fire Perimeter History), pour les étiquettes.

CaBuAr n'annote que l'incendie de l'événement : les cicatrices des feux des années précédentes restent
« normales », alors qu'elles se voient encore sur l'image. Ce module mesure, pour chaque tuile, la part
couverte par des feux des années précédant l'image. Sert aux étiquettes, pas d'entrée au modèle.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import requests
from rasterio.features import rasterize
from rasterio.warp import transform_geom

from onelook.data.l2a import Grid

SERVICE = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
           "InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0/query")
CALIFORNIA = (-124.5, 32.5, -114.0, 42.0)
PAGE = 500
SIMPLIFY_DEG = 0.0003  # environ 30 m : bien en dessous d'un pixel de la grille de mesure
MEASURE_SIZE = 128  # grille de mesure (40 m) : suffisante pour une part de tuile


def download(out: Path, first_year: int, last_year: int, bbox: tuple = CALIFORNIA) -> Path:
    """Télécharge les périmètres (GeoJSON, WGS84) des feux de first_year à last_year dans bbox."""
    features, offset = [], 0
    while True:
        params = {
            "where": f"FIRE_YEAR_INT>={first_year} AND FIRE_YEAR_INT<={last_year}",
            "geometry": ",".join(map(str, bbox)), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "FIRE_YEAR_INT,INCIDENT,SOURCE",
            "outSR": 4326, "maxAllowableOffset": SIMPLIFY_DEG, "geometryPrecision": 5,
            "resultOffset": offset, "resultRecordCount": PAGE, "orderByFields": "OBJECTID", "f": "geojson",
        }
        response = requests.get(SERVICE, params=params, timeout=120)
        response.raise_for_status()
        page = response.json()["features"]
        features += [f for f in page if f.get("geometry")]
        if len(page) < PAGE:
            break
        offset += PAGE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return out


def load(path: Path) -> list[dict]:
    """Périmètres sous la forme {year, name, geometry, bbox} (bbox en WGS84, pour filtrer vite)."""
    fires = []
    for feature in json.loads(Path(path).read_text())["features"]:
        coords = np.concatenate([np.asarray(ring)[:, :2] for ring in _rings(feature["geometry"])])
        fires.append({"year": int(feature["properties"]["FIRE_YEAR_INT"]),
                      "name": feature["properties"].get("INCIDENT"), "geometry": feature["geometry"],
                      "bbox": (*coords.min(axis=0), *coords.max(axis=0))})
    return fires


def _rings(geometry: dict) -> list:
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    return [ring for polygon in geometry["coordinates"] for ring in polygon]


def _overlaps(a: tuple, b: tuple) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def history_stats(grid: Grid, fires: list[dict], image_year: int, years: tuple[int, ...] = (0, 1, 2, 3, 5)) -> dict:
    """Part de la tuile couverte par des feux de l'année de l'image et des n années précédentes (n de years).

    frac_fire_0y ne compte que les feux de l'année de l'image : sans date de fin fiable, on ne sait pas
    s'ils précèdent l'image. Pour une image après feu CaBuAr, il contient le feu de l'événement lui-même.
    """
    box = grid.bounds_wgs84()
    recent = [f for f in fires if image_year - max(years) <= f["year"] <= image_year and _overlaps(f["bbox"], box)]
    scale = grid.width / MEASURE_SIZE
    transform = grid.transform * grid.transform.scale(scale, scale)
    age = np.full((MEASURE_SIZE, MEASURE_SIZE), 255, dtype=np.uint8)  # âge du feu le plus récent, en années
    names = set()
    for fire in sorted(recent, key=lambda f: f["year"]):
        shape = transform_geom("EPSG:4326", grid.crs, fire["geometry"])
        burned = rasterize([shape], out_shape=age.shape, transform=transform, fill=0, dtype=np.uint8) > 0
        age[burned] = image_year - fire["year"]
        if burned.any():
            names.add(f"{fire['name'] or '?'} {fire['year']}")
    stats = {f"frac_fire_{n}y": round(float((age <= n).mean()), 4) for n in years}
    stats["fire_history_names"] = ";".join(sorted(names))
    return stats
