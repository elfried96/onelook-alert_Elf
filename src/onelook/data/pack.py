"""Paquet d'entraînement compact : une tuile = un GeoTIFF de 9 bandes, prêt pour Colab.

Bandes du paquet (uint16, compression zstd) :
    1-6  B02, B03, B04, B08, B11, B12 : réflectance × 10 000 (bandes retenues, voir la page Cadrage)
    7    SCL : classification de scène L2A (nuages, eau, neige…)
    8    vérité terrain unifiée : 0 rien, 1 eau d'inondation, 2 brûlé, 255 non observé
    9    occurrence de l'eau JRC 1984-2020 (0-100 %, 255 en pleine mer)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from onelook.data.sentinel2 import BANDS_L2A, SELECTED_BANDS

PACK_BANDS = [*SELECTED_BANDS, "SCL", "truth", "water"]
TRUTH_NONE, TRUTH_FLOOD, TRUTH_BURNED, TRUTH_UNSEEN = 0, 1, 2, 255
# Codes des masques d'origine (onelook.data.build)
FLOOD_NODATA, FLOOD_WATER = 0, 3


def unified_truth(mask: np.ndarray | None, source: str, shape: tuple[int, int]) -> np.ndarray:
    """Vérité terrain commune à toutes les sources. L'eau permanente n'est pas une anomalie (code 0)."""
    truth = np.full(shape, TRUTH_NONE, dtype=np.uint16)
    if mask is None:
        return truth  # normales du catalogue et points au hasard : pas d'anomalie annotée
    if source == "sen1floods11":
        truth[mask == FLOOD_WATER] = TRUTH_FLOOD
        truth[mask == FLOOD_NODATA] = TRUTH_UNSEEN
    else:
        truth[mask > 0] = TRUTH_BURNED
    return truth


def pack_tile(dataset: Path, row: dict, out: Path) -> None:
    """Écrit la tuile compacte de 9 bandes à partir des fichiers du jeu complet."""
    image = dataset / row["image"]
    stem = image.with_name(image.stem)
    with rasterio.open(image) as src:
        bands = src.read([BANDS_L2A.index(b) + 1 for b in SELECTED_BANDS])
        profile = src.profile
    with rasterio.open(f"{stem}_SCL.tif") as src:
        scl = src.read(1)
    with rasterio.open(f"{stem}_water.tif") as src:
        water = src.read(1)
    mask = None
    if isinstance(row.get("mask"), str):
        with rasterio.open(dataset / row["mask"]) as src:
            mask = src.read(1)
    truth = unified_truth(mask, row["source"], scl.shape)
    stack = np.concatenate([bands, scl[None], truth[None], water[None]]).astype(np.uint16)

    profile.update(count=len(PACK_BANDS), dtype="uint16", compress="zstd", zstd_level=9, predictor=2,
                   tiled=True, blockxsize=256, blockysize=256, nodata=None)
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(stack)
        dst.descriptions = tuple(PACK_BANDS)


def read_packed(path: Path) -> dict[str, np.ndarray]:
    """Lit une tuile du paquet : image (6, H, W) en réflectance, et ses couches."""
    with rasterio.open(path) as src:
        stack = src.read()
    return {
        "image": stack[:6].astype(np.float32) / 10000,
        "scl": stack[6].astype(np.uint8),
        "truth": stack[7].astype(np.uint8),
        "water": stack[8].astype(np.uint8),
    }
