"""Accès aux sources de données publiques : Sen1Floods11 (inondations) et CaBuAr (incendies)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import requests

# Sen1Floods11 : bucket Google Cloud public, tuiles annotées à la main (446 tuiles, 11 pays)
SEN1FLOODS11_BUCKET = "sen1floods11"
SEN1FLOODS11_PREFIX = "v1.1/data/flood_events/HandLabeled"
SEN1FLOODS11_HTTP = f"https://storage.googleapis.com/{SEN1FLOODS11_BUCKET}/{SEN1FLOODS11_PREFIX}"

# CaBuAr : Hugging Face, tuiles 512 × 512 pré-découpées (HDF5, lu à distance sans tout télécharger)
CABUAR_PATCHED_URL = (
    "https://huggingface.co/datasets/DarthReca/california_burned_areas/"
    "resolve/main/raw/patched/512x512.hdf5"
)

# Valeurs du masque LabelHand de Sen1Floods11
LABEL_NODATA, LABEL_DRY, LABEL_WATER = -1, 0, 1


def list_sen1floods11_tiles() -> list[str]:
    """Identifiants des 446 tuiles annotées, par exemple « Bolivia_103757 »."""
    url = f"https://storage.googleapis.com/storage/v1/b/{SEN1FLOODS11_BUCKET}/o"
    params = {
        "prefix": f"{SEN1FLOODS11_PREFIX}/LabelHand/",
        "maxResults": 1000,
        "fields": "items(name)",
    }
    items = requests.get(url, params=params, timeout=60).json()["items"]
    return sorted(Path(i["name"]).name.removesuffix("_LabelHand.tif") for i in items)


def sen1floods11_url(tile_id: str, layer: str) -> str:
    """URL d'une couche d'une tuile : « S2Hand », « LabelHand » ou « JRCWaterHand »."""
    return f"{SEN1FLOODS11_HTTP}/{layer}/{tile_id}_{layer}.tif"


def download(url: str, dest: Path) -> Path:
    """Télécharge un fichier s'il n'est pas déjà présent."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    return dest


def flood_stats(label: np.ndarray, permanent: np.ndarray) -> dict[str, float]:
    """Parts d'eau, d'eau permanente et d'eau d'inondation parmi les pixels visibles.

    Eau d'inondation = eau annotée qui n'est pas de l'eau permanente (couche JRC).
    """
    valid = label != LABEL_NODATA
    n_valid = int(valid.sum())
    water = (label == LABEL_WATER) & valid
    flood = water & (permanent == 0)
    if n_valid == 0:
        return {"valid": 0.0, "water": 0.0, "permanent": 0.0, "flood": 0.0}
    return {
        "valid": n_valid / label.size,
        "water": water.sum() / n_valid,
        "permanent": (water & (permanent > 0)).sum() / n_valid,
        "flood": flood.sum() / n_valid,
    }


def read_band_stack(path: Path) -> np.ndarray:
    """Lit un GeoTIFF en tableau (bandes, hauteur, largeur)."""
    with rasterio.open(path) as src:
        return src.read()


def load_json(path: Path) -> object:
    return json.loads(path.read_text())


def save_json(obj: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
