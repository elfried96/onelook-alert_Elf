"""Approches de référence, sans réseau de neurones : seuils sur les indices, et classifieur sur statistiques.

Les deux ne lisent que l'image (6 bandes), comme le ferait le satellite : ni carte SCL, ni eau permanente.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from onelook.data.labels import FIRE, FLOOD, NORMAL

# Ordre des bandes du paquet (onelook.data.pack)
B02, B03, B04, B08, B11, B12 = range(6)
INDEX_GRID = np.round(np.arange(-0.4, 0.31, 0.05), 2)
AREA_GRID = np.array([0.02, 0.05, 0.1, 0.2, 0.3])
SUBSAMPLE = 2  # un pixel sur deux dans chaque direction : 256 × 256 suffisent pour des parts de surface


def _nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a - b) / (a + b + 1e-6)


def indices(image: np.ndarray) -> dict[str, np.ndarray]:
    """NDWI, MNDWI et NBR d'une image (6, H, W) en réflectance."""
    return {"ndwi": _nd(image[B03], image[B08]), "mndwi": _nd(image[B03], image[B11]),
            "nbr": _nd(image[B08], image[B12])}


def threshold_features(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Parts de pixels « eau » pour chaque seuil NDWI, et « brûlé » (NBR bas et pas de l'eau) pour chaque couple."""
    idx = indices(image[:, ::SUBSAMPLE, ::SUBSAMPLE])
    ndwi, nbr = idx["ndwi"].ravel(), idx["nbr"].ravel()
    water = ndwi[None, :] > INDEX_GRID[:, None]                          # (seuils NDWI, pixels)
    burned = nbr[None, :] < INDEX_GRID[:, None]                          # (seuils NBR, pixels)
    water_frac = water.mean(axis=1)
    fire_frac = (burned[None, :, :] & ~water[:, None, :]).mean(axis=2)  # (seuils NDWI, seuils NBR)
    return water_frac.astype(np.float32), fire_frac.astype(np.float32)


def stat_features(image: np.ndarray) -> np.ndarray:
    """Statistiques par bande et par indice : moyenne, écart-type, centiles 10, 50 et 90 (45 valeurs)."""
    sub = image[:, ::SUBSAMPLE, ::SUBSAMPLE]
    layers = [*sub, *indices(sub).values()]
    feats = []
    for layer in layers:
        flat = layer.ravel()
        feats += [flat.mean(), flat.std(), *np.percentile(flat, [10, 50, 90])]
    return np.array(feats, dtype=np.float32)


@dataclass(frozen=True)
class ThresholdRule:
    """Alerte si la part de pixels « eau » ou « brûlé » dépasse une surface minimale."""
    ndwi: float
    nbr: float
    water_area: float
    fire_area: float

    def predict(self, water_frac: np.ndarray, fire_frac: np.ndarray) -> np.ndarray:
        """water_frac (tuiles, seuils NDWI), fire_frac (tuiles, seuils NDWI, seuils NBR) -> décisions."""
        i, j = int(np.argmin(abs(INDEX_GRID - self.ndwi))), int(np.argmin(abs(INDEX_GRID - self.nbr)))
        return decide(water_frac[:, i], fire_frac[:, i, j], self.water_area, self.fire_area)


def decide(water: np.ndarray, fire: np.ndarray, water_area: float, fire_area: float) -> np.ndarray:
    flood_hit, fire_hit = water >= water_area, fire >= fire_area
    out = np.full(len(water), NORMAL, dtype=object)
    out[fire_hit] = FIRE
    out[flood_hit & (~fire_hit | (water >= fire))] = FLOOD
    return out


def macro_f1(truth: np.ndarray, pred: np.ndarray) -> float:
    scores = []
    for cls in (NORMAL, FLOOD, FIRE):
        tp = np.sum((truth == cls) & (pred == cls))
        p, r = tp / max(np.sum(pred == cls), 1), tp / max(np.sum(truth == cls), 1)
        scores.append(2 * p * r / (p + r) if p + r else 0.0)
    return float(np.mean(scores))


def fit_thresholds(water_frac: np.ndarray, fire_frac: np.ndarray, labels: np.ndarray) -> tuple[ThresholdRule, float]:
    """Recherche exhaustive des seuils qui maximisent le F1 macro (à faire sur l'entraînement seulement)."""
    best, best_score = None, -1.0
    for i, ndwi in enumerate(INDEX_GRID):
        for j, nbr in enumerate(INDEX_GRID):
            for wa in AREA_GRID:
                for fa in AREA_GRID:
                    score = macro_f1(labels, decide(water_frac[:, i], fire_frac[:, i, j], wa, fa))
                    if score > best_score:
                        best, best_score = ThresholdRule(float(ndwi), float(nbr), float(wa), float(fa)), score
    return best, best_score
