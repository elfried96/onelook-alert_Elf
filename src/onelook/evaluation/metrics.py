"""Mesures communes à toutes les approches, sur les décisions par tuile.

Les tuiles ambiguës sont écartées. « Inconnu » n'est jamais une bonne réponse sur ce jeu (aucune tuile
n'y est hors distribution) : sur une tuile en alerte, c'est une alerte manquée, mais transmise au sol.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from onelook.data.labels import AMBIGUOUS, CLASSES, FIRE, FLOOD, NORMAL

UNKNOWN = "inconnu"
ALERTS = [FLOOD, FIRE]
WATER_TRAPS = ["ocean", "littoral", "estuaire", "lac", "reservoir", "riviere", "lagune_ville", "rizieres"]
CALIFORNIA_SOURCES = ("cabuar", "cabuar_avant_feu")


def _rate(hits: np.ndarray) -> float:
    return float(hits.mean()) if len(hits) else float("nan")


def decision_metrics(index: pd.DataFrame, predictions) -> dict[str, float]:
    """Mesures d'un jeu de décisions. `index` a les colonnes label, source, category ; même ordre que predictions."""
    df = index.assign(pred=list(predictions))
    df = df[df["label"] != AMBIGUOUS]
    out: dict[str, float] = {"tuiles": len(df)}
    f1s = []
    for cls, name in ((FLOOD, "inondation"), (FIRE, "incendie"), (NORMAL, "normal")):
        truth, pred = df["label"] == cls, df["pred"] == cls
        tp = int((truth & pred).sum())
        precision = tp / pred.sum() if pred.sum() else float("nan")
        recall = tp / truth.sum() if truth.sum() else float("nan")
        f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
        f1s.append(f1)
        if cls != NORMAL:
            out[f"precision_{name}"] = precision
            out[f"rappel_{name}"] = recall
    out["f1_macro"] = float(np.nanmean(f1s))
    normals = df[df["label"] == NORMAL]
    alerted = normals["pred"].isin(ALERTS)
    out["fausses_alertes"] = _rate(alerted)
    out["fausses_alertes_eau"] = _rate(alerted[normals["category"].isin(WATER_TRAPS)])
    out["fausses_alertes_hors_californie"] = _rate(alerted[~normals["source"].isin(CALIFORNIA_SOURCES)])
    out["inconnu"] = _rate(df["pred"] == UNKNOWN)
    out["exactitude"] = _rate(df["pred"] == df["label"])
    return out


def confusion(index: pd.DataFrame, predictions) -> pd.DataFrame:
    """Matrice de confusion (lignes : vérité, colonnes : décision), tuiles ambiguës écartées."""
    df = index.assign(pred=list(predictions))
    df = df[df["label"] != AMBIGUOUS]
    return pd.crosstab(df["label"], df["pred"]).reindex(index=CLASSES, columns=[*CLASSES, UNKNOWN], fill_value=0)


def format_row(name: str, metrics: dict[str, float], size_mb: float | None = None, time_ms: float | None = None) -> str:
    """Ligne du tableau de docs/results.md."""
    pct = lambda v: "–" if v is None or v != v else f"{v:.0%}"  # noqa: E731
    num = lambda v, f: "–" if v is None else format(v, f)  # noqa: E731
    return (f"| {name} | {pct(metrics['precision_inondation'])} · {pct(metrics['precision_incendie'])} "
            f"| {pct(metrics['rappel_inondation'])} · {pct(metrics['rappel_incendie'])} "
            f"| {pct(metrics['fausses_alertes'])} | {pct(metrics['fausses_alertes_eau'])} "
            f"| {num(size_mb, '.2f')} | {num(time_ms, '.1f')} |")
