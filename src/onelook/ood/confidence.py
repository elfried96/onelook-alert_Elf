"""Décision « inconnu » : le modèle répond seulement s'il est assez sûr de lui.

Seuil calibré sur la validation : on garde `keep` des tuiles que le modèle classe correctement,
les moins sûres passent en « inconnu ». Le lot de phénomènes jamais vus mesurera ensuite si ce seuil
les attrape.

KEEP = 0,98 (9 nov) : avec 0,95, le seuil du réseau à 512 px v3 envoyait 18 des 66 incendies de validation
en « inconnu ». 0,98 est la part la plus haute dont les fausses alertes de validation restent à 0,5 %
au plus ; choisie sur la validation seule (balayage : `scripts/calibrate.py`, docs/results.md).
"""

from __future__ import annotations

import numpy as np

from onelook.data.labels import CLASSES
from onelook.evaluation.metrics import UNKNOWN

KEEP = 0.98  # part des bonnes réponses de validation gardées hors « inconnu »


def softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def calibrate_threshold(probs: np.ndarray, labels: np.ndarray, keep: float = KEEP) -> float:
    """Confiance minimale gardant `keep` des bonnes réponses. labels : indices dans CLASSES."""
    correct = probs.argmax(axis=1) == labels
    confidence = probs.max(axis=1)[correct]
    return float(np.quantile(confidence, 1 - keep)) if len(confidence) else 0.0


def decisions(probs: np.ndarray, threshold: float) -> np.ndarray:
    out = np.array(CLASSES, dtype=object)[probs.argmax(axis=1)]
    out[probs.max(axis=1) < threshold] = UNKNOWN
    return out
