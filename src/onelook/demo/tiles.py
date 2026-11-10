"""Lecture des tuiles de la démo (paquet, lot « inconnu », GeoTIFF déposé) et rendu en images."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import rasterio
import rasterio.errors
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.warp import transform as warp_transform

from onelook.data.pack import TRUTH_BURNED, TRUTH_FLOOD, read_packed
from onelook.data.sentinel2 import BANDS_L1C, BANDS_L2A, SELECTED_BANDS

TILE = 512
VIEWS = {"naturel": (2, 1, 0), "swir": (5, 3, 2), "pir": (3, 2, 1)}


def read_pack_tile(path: Path) -> dict:
    tile = read_packed(path)
    return {"image": tile["image"], "scl": tile["scl"], "water": tile["water"], "truth": tile["truth"]}


def read_unknown_tile(path: Path) -> dict:
    with rasterio.open(path) as src:
        image = src.read([BANDS_L2A.index(b) + 1 for b in SELECTED_BANDS]).astype(np.float32) / 10000
    scl_path = path.with_name(path.stem + "_SCL.tif")
    scl = None
    if scl_path.exists():
        with rasterio.open(scl_path) as src:
            scl = src.read(1)
    return {"image": image, "scl": scl, "water": None, "truth": None}


def read_upload(data: bytes) -> tuple[dict, dict]:
    """GeoTIFF déposé : 6 bandes dans l'ordre du modèle, ou 12 (L2A) / 13 (L1C) bandes Sentinel-2.

    Les bandes sont prises par leur nom quand le fichier les décrit, sinon par leur nombre. Une image plus
    grande que 512 × 512 est recadrée au centre. Réflectance attendue en 0-1 ou × 10 000.
    """
    try:
        memfile = MemoryFile(data)
        src = memfile.open()
    except rasterio.errors.RasterioIOError:
        raise ValueError("Fichier illisible : il faut un GeoTIFF.") from None
    with memfile, src:
        names = [d or "" for d in src.descriptions]
        if all(b in names for b in SELECTED_BANDS):
            index = [names.index(b) + 1 for b in SELECTED_BANDS]
        elif src.count == 6:
            index = list(range(1, 7))
        elif src.count in (12, 13):
            order = BANDS_L2A if src.count == 12 else BANDS_L1C
            index = [order.index(b) + 1 for b in SELECTED_BANDS]
        else:
            raise ValueError(f"{src.count} bande{'s' if src.count > 1 else ''} : il faut 6 bandes (B02, B03, B04, B08, B11, B12) ou une "
                             "tuile Sentinel-2 complète de 12 ou 13 bandes.")
        if src.width < TILE or src.height < TILE:
            raise ValueError(f"Image de {src.width} × {src.height} pixels : il faut au moins 512 × 512.")
        top, left = (src.height - TILE) // 2, (src.width - TILE) // 2
        window = rasterio.windows.Window(left, top, TILE, TILE)
        image = src.read(index, window=window).astype(np.float32)
        meta = {}
        if src.crs is not None:
            x, y = src.window_transform(window) * (TILE / 2, TILE / 2)
            lon, lat = warp_transform(src.crs, "EPSG:4326", [x], [y])
            meta = {"lon": float(lon[0]), "lat": float(lat[0])}
    if np.nanmax(image) > 2:  # réflectance × 10 000
        image /= 10000
    return {"image": np.nan_to_num(image), "scl": None, "water": None, "truth": None}, meta


def stretch(rgb: np.ndarray) -> np.ndarray:
    valid = rgb.sum(axis=0) > 0
    out = np.zeros_like(rgb)
    for i, band in enumerate(rgb):
        values = band[valid] if valid.any() else band.ravel()
        lo, hi = np.percentile(values, [2, 98])
        out[i] = np.clip((band - lo) / (hi - lo + 1e-6), 0, 1)
    return (out.transpose(1, 2, 0) * 255).astype(np.uint8)


def render(tile: dict, view: str) -> tuple[bytes, str]:
    """Image d'une vue : couleurs (naturel, swir, pir), une bande (b0 à b5) ou la vérité terrain (PNG transparent)."""
    image = tile["image"]
    if view in VIEWS:
        pixels = Image.fromarray(stretch(image[list(VIEWS[view])]))
    elif view.startswith("b") and view[1:].isdigit():
        pixels = Image.fromarray(stretch(image[[int(view[1:])]])[..., 0])
    elif view == "verite":
        rgba = np.zeros((*image.shape[1:], 4), dtype=np.uint8)
        truth = tile.get("truth")
        if truth is not None:
            for code, color in ((TRUTH_FLOOD, (111, 177, 227)), (TRUTH_BURNED, (255, 210, 63))):
                mask = truth == code
                edge = mask & ~(np.roll(mask, 1, 0) & np.roll(mask, -1, 0) & np.roll(mask, 1, 1) & np.roll(mask, -1, 1))
                rgba[mask] = (*color, 70)
                rgba[edge] = (*color, 255)
        buffer = io.BytesIO()
        Image.fromarray(rgba).save(buffer, "PNG")
        return buffer.getvalue(), "image/png"
    else:
        raise KeyError(view)
    buffer = io.BytesIO()
    pixels.save(buffer, "JPEG", quality=88)
    return buffer.getvalue(), "image/jpeg"
