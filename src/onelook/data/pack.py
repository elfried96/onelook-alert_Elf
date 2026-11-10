"""Paquet d'entraînement compact : une tuile = un GeoTIFF multibande, prêt pour Colab.

Bandes du paquet (uint16, compression zstd), n bandes d'image puis 3 couches :
    1-n  réflectance × 10 000 : les 6 bandes retenues (B02, B03, B04, B08, B11, B12, data/pack/),
         ou les 12 bandes L2A (data/pack12/, essai « 12 bandes »)
    n+1  SCL : classification de scène L2A (nuages, eau, neige…)
    n+2  vérité terrain unifiée : 0 rien, 1 eau d'inondation, 2 brûlé, 255 non observé
    n+3  occurrence de l'eau JRC 1984-2020 (0-100 %, 255 en pleine mer)
Les noms des bandes sont écrits dans le fichier : read_packed et pack_band_names les relisent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from onelook.data.sentinel2 import BANDS_L2A, SELECTED_BANDS

LAYERS = ["SCL", "truth", "water"]
PACK_BANDS = [*SELECTED_BANDS, *LAYERS]
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


def pack_tile(dataset: Path, row: dict, out: Path, bands: list[str] = SELECTED_BANDS) -> None:
    """Écrit la tuile compacte (bandes d'image choisies, puis SCL, vérité, eau) à partir du jeu complet."""
    image = dataset / row["image"]
    stem = image.with_name(image.stem)
    with rasterio.open(image) as src:
        reflectance = src.read([BANDS_L2A.index(b) + 1 for b in bands])
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
    stack = np.concatenate([reflectance, scl[None], truth[None], water[None]]).astype(np.uint16)

    profile.update(count=len(bands) + len(LAYERS), dtype="uint16", compress="zstd", zstd_level=9, predictor=2,
                   tiled=True, blockxsize=256, blockysize=256, nodata=None)
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(stack)
        dst.descriptions = (*bands, *LAYERS)


def read_packed(path: Path) -> dict[str, np.ndarray]:
    """Lit une tuile du paquet : image (n, H, W) en réflectance (n = 6 ou 12), et ses couches."""
    with rasterio.open(path) as src:
        stack = src.read()
    n = stack.shape[0] - len(LAYERS)
    return {
        "image": stack[:n].astype(np.float32) / 10000,
        "scl": stack[n].astype(np.uint8),
        "truth": stack[n + 1].astype(np.uint8),
        "water": stack[n + 2].astype(np.uint8),
    }


def pack_band_names(path: Path) -> list[str]:
    """Noms des bandes d'image d'une tuile du paquet (dans l'ordre où le modèle les reçoit)."""
    with rasterio.open(path) as src:
        names = list(src.descriptions)
    return names[: len(names) - len(LAYERS)] if all(names) else list(SELECTED_BANDS)
