"""Décision attendue pour chaque tuile, à partir des parts d'anomalie de l'index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

NORMAL, FLOOD, FIRE, AMBIGUOUS = "normal", "alerte_inondation", "alerte_incendie", "ambigu"
CLASSES = [NORMAL, FLOOD, FIRE]  # les trois décisions apprises ; « inconnu » vient de la confiance du modèle


@dataclass(frozen=True)
class LabelRules:
    flood_alert: float = 0.05
    fire_alert: float = 0.05
    normal_max: float = 0.005

    @classmethod
    def from_yaml(cls, path: Path) -> LabelRules:
        return cls(**yaml.safe_load(Path(path).read_text()))


def label_row(frac_flood: float, frac_valid: float, frac_burned: float, rules: LabelRules) -> str:
    """Décision attendue d'une tuile. Les parts d'inondation sont ramenées à la tuile entière."""
    flood = frac_flood * frac_valid
    if flood >= rules.flood_alert and flood >= frac_burned:
        return FLOOD
    if frac_burned >= rules.fire_alert:
        return FIRE
    if flood < rules.normal_max and frac_burned < rules.normal_max:
        return NORMAL
    return AMBIGUOUS


def add_labels(index: pd.DataFrame, rules: LabelRules) -> pd.DataFrame:
    out = index.copy()
    out["label"] = [
        label_row(f, v, b, rules)
        for f, v, b in zip(out["frac_flood"].fillna(0), out["frac_valid"].fillna(1), out["frac_burned"].fillna(0))
    ]
    return out
