"""Vérifie le paquet d'entraînement (data/pack/) : fichiers présents, composition, lecture et débit.

Usage : uv run python scripts/check_pack.py [--pack data/pack] [--sample 64]
Sert après le téléchargement sur Colab, avant tout entraînement.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from onelook.data.pack import TRUTH_BURNED, TRUTH_FLOOD, TRUTH_UNSEEN, read_packed

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--sample", type=int, default=64)
    args = parser.parse_args()

    index = pd.read_csv(args.pack / "index.csv")
    missing = [p for p in index.path if not (args.pack / p).exists()]
    print(f"{len(index)} tuiles dans l'index, {len(missing)} fichiers manquants")
    print(pd.crosstab(index.label, index.split, margins=True), "\n")

    # Les parts de l'index doivent se retrouver dans la vérité terrain du paquet
    sample = index.sample(min(args.sample, len(index)), random_state=0)
    start, errors = time.perf_counter(), []
    for row in sample.itertuples():
        tile = read_packed(args.pack / row.path)
        assert tile["image"].shape == (6, 512, 512), row.id
        seen = tile["truth"] != TRUTH_UNSEEN
        flood = (tile["truth"] == TRUTH_FLOOD).sum() / max(seen.sum(), 1)
        burned = (tile["truth"] == TRUTH_BURNED).mean()
        if abs(flood - np.nan_to_num(row.frac_flood)) > 0.01 or abs(burned - np.nan_to_num(row.frac_burned)) > 0.01:
            errors.append(row.id)
    elapsed = (time.perf_counter() - start) / len(sample)
    print(f"Lecture : {elapsed * 1000:.0f} ms par tuile ; vérité incohérente avec l'index : {len(errors)} {errors[:5]}")
    if missing or errors:
        raise SystemExit("Paquet incomplet ou incohérent")
    print("Paquet prêt.")


if __name__ == "__main__":
    main()
