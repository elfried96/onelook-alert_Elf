"""Bandes Sentinel-2, indices spectraux et compositions colorées pour l'affichage."""

from __future__ import annotations

import numpy as np

# Ordre des bandes selon le niveau de traitement
BANDS_L1C = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B10", "B11", "B12"]
BANDS_L2A = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B11", "B12"]

# Bandes retenues pour le modèle (voir la page Cadrage)
SELECTED_BANDS = ["B02", "B03", "B04", "B08", "B11", "B12"]

# Les réflectances sont stockées multipliées par 10 000
REFLECTANCE_SCALE = 10_000


def band_names(n_bands: int) -> list[str]:
    """Noms des bandes d'après leur nombre : 13 pour L1C, 12 pour L2A."""
    if n_bands == len(BANDS_L1C):
        return BANDS_L1C
    if n_bands == len(BANDS_L2A):
        return BANDS_L2A
    raise ValueError(f"Nombre de bandes inattendu : {n_bands}")


def get_bands(image: np.ndarray, names: list[str]) -> np.ndarray:
    """Extrait des bandes par leur nom d'une image (bandes, H, W), en réflectance 0-1."""
    order = band_names(image.shape[0])
    idx = [order.index(n) for n in names]
    return image[idx].astype(np.float32) / REFLECTANCE_SCALE


def normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(a − b) / (a + b), à 0 là où le dénominateur est nul."""
    num, den = a - b, a + b
    return np.divide(num, den, out=np.zeros_like(num), where=den != 0)


def ndwi(image: np.ndarray) -> np.ndarray:
    """Indice de l'eau : (vert − proche infrarouge) / (vert + proche infrarouge). Eau : > 0."""
    green, nir = get_bands(image, ["B03", "B08"])
    return normalized_difference(green, nir)


def mndwi(image: np.ndarray) -> np.ndarray:
    """Indice de l'eau modifié, avec le SWIR (B11) : sépare mieux l'eau des zones bâties."""
    green, swir = get_bands(image, ["B03", "B11"])
    return normalized_difference(green, swir)


def nbr(image: np.ndarray) -> np.ndarray:
    """Indice de brûlure : (proche infrarouge − SWIR B12) / (somme). Sol brûlé : valeur basse."""
    nir, swir2 = get_bands(image, ["B08", "B12"])
    return normalized_difference(nir, swir2)


def composite(image: np.ndarray, names: list[str], low: float = 2, high: float = 98) -> np.ndarray:
    """Composition colorée (H, W, 3) étirée entre deux percentiles, prête pour imshow."""
    rgb = get_bands(image, names)
    valid = rgb.sum(axis=0) > 0
    out = np.zeros_like(rgb)
    for i, band in enumerate(rgb):
        values = band[valid] if valid.any() else band.ravel()
        lo, hi = np.percentile(values, [low, high])
        out[i] = np.clip((band - lo) / (hi - lo + 1e-6), 0, 1)
    return np.transpose(out, (1, 2, 0))


def natural_color(image: np.ndarray) -> np.ndarray:
    """Couleurs naturelles : rouge, vert, bleu (B04, B03, B02)."""
    return composite(image, ["B04", "B03", "B02"])


def false_color_infrared(image: np.ndarray) -> np.ndarray:
    """Infrarouge fausses couleurs (B08, B04, B03) : végétation rouge, eau noire."""
    return composite(image, ["B08", "B04", "B03"])


def false_color_swir(image: np.ndarray) -> np.ndarray:
    """SWIR fausses couleurs (B12, B08, B04) : sol brûlé brun-rouge, eau très sombre."""
    return composite(image, ["B12", "B08", "B04"])
