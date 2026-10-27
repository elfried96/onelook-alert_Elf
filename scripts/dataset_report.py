"""Résume le jeu de données : décisions attendues par partie, sources, catégories, et contrôle de fuite spatiale.

Usage : uv run python scripts/dataset_report.py
Écrit data/dataset/report.md et data/dataset/index_labels.csv.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from onelook.data.labels import LabelRules, add_labels
from onelook.data.splits import haversine_km

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "dataset"
LEAK_DISTANCE_KM = 10  # deux tuiles de parties différentes à moins de 10 km : risque de fuite


def spatial_leaks(df: pd.DataFrame) -> pd.DataFrame:
    """Paires de tuiles de parties différentes dont les centres sont à moins de LEAK_DISTANCE_KM."""
    leaks = []
    lat, lon, split = df["lat"].to_numpy(), df["lon"].to_numpy(), df["split"].to_numpy()
    for i in range(len(df)):
        d = haversine_km(lat[i], lon[i], lat[i + 1:], lon[i + 1:])
        for j in np.nonzero((d < LEAK_DISTANCE_KM) & (split[i + 1:] != split[i]))[0]:
            k = i + 1 + j
            leaks.append({"a": df["id"].iat[i], "split_a": split[i], "b": df["id"].iat[k], "split_b": split[k],
                          "km": round(float(d[j]), 1)})
    return pd.DataFrame(leaks)


def md_table(table: pd.DataFrame) -> str:
    table = table.reset_index()
    header = "| " + " | ".join(str(c) for c in table.columns) + " |"
    sep = "|" + "---|" * len(table.columns)
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in table.itertuples(index=False)]
    return "\n".join([header, sep, *rows])


def main() -> None:
    rules = LabelRules.from_yaml(ROOT / "configs" / "labels.yaml")
    df = add_labels(pd.read_csv(DATASET / "index.csv"), rules)
    df.to_csv(DATASET / "index_labels.csv", index=False)

    by_label = pd.crosstab(df["label"], df["split"], margins=True, margins_name="total")
    by_source = pd.crosstab(df["source"], df["split"], margins=True, margins_name="total")
    normals = df[df["label"] == "normal"]
    by_category = pd.crosstab(normals["category"], normals["split"], margins=True, margins_name="total")
    leaks = spatial_leaks(df)

    report = [
        "# Rapport du jeu de données", "",
        f"Seuils : alerte inondation ≥ {rules.flood_alert:.0%}, alerte incendie ≥ {rules.fire_alert:.0%}, "
        f"normal < {rules.normal_max:.1%} de la tuile.", "",
        "## Décisions attendues par partie", "", md_table(by_label), "",
        "## Sources par partie", "", md_table(by_source), "",
        "## Catégories des tuiles normales", "", md_table(by_category), "",
        "## Contrôle de fuite spatiale", "",
        f"Paires de tuiles de parties différentes à moins de {LEAK_DISTANCE_KM} km : **{len(leaks)}**.",
    ]
    if len(leaks):
        report += ["", md_table(leaks.head(20).set_index("a"))]
    (DATASET / "report.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
