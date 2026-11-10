"""Importance de chaque bande pour un modèle exporté, sans réentraîner : on brouille une bande et on mesure la perte.

Deux façons de brouiller la bande k d'une tuile :
- permutation : on la remplace par la bande k d'une autre tuile tirée au hasard (même partie) ;
- moyenne : on la remplace par sa moyenne d'entraînement (l'information de la bande disparaît).
Une bande dont le brouillage fait chuter les détections ou monter les fausses alertes est une bande utile.

    uv run python scripts/band_importance.py runs/<nom> --split test
Écrit runs/<nom>/band_importance_<split>.json ; --figure trace la figure de la documentation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
from tqdm import tqdm

from onelook.data.labels import CLASSES
from onelook.data.pack import read_packed
from onelook.data.sentinel2 import SELECTED_BANDS
from onelook.evaluation.metrics import decision_metrics
from onelook.ood.confidence import decisions, softmax

ROOT = Path(__file__).resolve().parents[1]
NAMES = {"B02": "B02 · bleu", "B03": "B03 · vert", "B04": "B04 · rouge", "B08": "B08 · proche infrarouge",
         "B11": "B11 · infrarouge court 1", "B12": "B12 · infrarouge court 2"}
KEYS = ("rappel_inondation", "rappel_incendie", "fausses_alertes", "f1_macro")


def measure(run: Path, pack: Path, split: str, seed: int) -> dict:
    config = json.loads((run / "config.json").read_text())
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    session = ort.InferenceSession(str(run / "model.onnx"), options, providers=["CPUExecutionProvider"])
    index = pd.read_csv(pack / "index.csv")
    index = index[(index["split"] == split) & index["label"].isin(CLASSES)].reset_index(drop=True)
    donors = np.random.default_rng(seed).permutation(len(index))
    mean = np.asarray(config["mean"], dtype=np.float32)[:, None, None]
    n = len(SELECTED_BANDS)
    probs = np.zeros((1 + 2 * n, len(index), len(CLASSES)), dtype=np.float32)  # référence, permutations, moyennes
    for i, path in enumerate(tqdm(index["path"], desc=f"Bandes ({split})")):
        image = read_packed(pack / path)["image"]
        donor = read_packed(pack / index["path"].iat[donors[i]])["image"]
        batch = np.repeat(image[None], 1 + 2 * n, axis=0)
        for k in range(n):
            batch[1 + k, k] = donor[k]
            batch[1 + n + k, k] = mean[k]
        probs[:, i] = softmax(session.run(None, {"image": batch})[0])

    def metrics(p: np.ndarray) -> dict:
        m = decision_metrics(index, decisions(p, config["seuil_inconnu"]))
        return {k: round(float(m[k]), 4) for k in KEYS}

    out = {"split": split, "tuiles": len(index), "seuil": config["seuil_inconnu"], "reference": metrics(probs[0]),
           "permutation": {}, "moyenne": {}}
    for k, band in enumerate(SELECTED_BANDS):
        out["permutation"][band] = metrics(probs[1 + k])
        out["moyenne"][band] = metrics(probs[1 + n + k])
    return out


def figure(result: dict, out: Path) -> None:
    """Effet du brouillage de chaque bande, deux méthodes côte à côte, trois panneaux (une échelle par mesure)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid = "#14202b", "#4f5f6b", "#e4e8eb"
    methods = [("permutation", "bande d'une autre tuile", "#184f95"), ("moyenne", "bande remplacée par sa moyenne", "#86b6ef")]
    ref = result["reference"]
    panels = [("rappel_inondation", "Inondations détectées", -1), ("rappel_incendie", "Incendies détectés", -1),
              ("fausses_alertes", "Fausses alertes", 1)]
    bands = list(result["permutation"])
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9), sharey=True)
    for ax, (key, title, sign) in zip(axes, panels):
        for m, (method, _, color) in enumerate(methods):
            change = [100 * sign * (result[method][b][key] - ref[key]) for b in bands]  # positif = pire
            ys = [y + (m - 0.5) * 0.36 for y in range(len(bands))]
            ax.barh(ys, change, color=color, height=0.32)
            for y, v in zip(ys, change):
                ax.text(v + 1, y, f"{v:+.0f}".replace("-", "−"), va="center", ha="left", fontsize=7.5, color=ink)
        ax.axvline(0, color="#c9d1d6", linewidth=1)
        unit = "points perdus" if sign < 0 else "points ajoutés"
        ax.set_title(f"{title} : {unit}\n(référence {100 * ref[key]:.1f} %)".replace(".", ","), fontsize=9,
                     color=ink, loc="left")
        ax.grid(axis="x", color=grid, linewidth=0.8)
        ax.tick_params(colors=muted, labelsize=8)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#c9d1d6")
        ax.set_xlim(-9, 108 if sign < 0 else 25)
    axes[0].set_yticks(range(len(bands)), [NAMES[b] for b in bands])
    axes[0].invert_yaxis()
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in methods]
    fig.legend(handles, [f"Brouillage : {label}" for _, label, _ in methods], loc="lower left", ncol=2,
               frameon=False, fontsize=8.5, bbox_to_anchor=(0.01, -0.06))
    fig.suptitle(f"Importance des bandes : effet du brouillage d'une bande sur le {result['split']} "
                 f"({result['tuiles']} tuiles, modèle de référence)", x=0.01, ha="left", fontsize=10, color=ink)
    fig.tight_layout()
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"{out.name} écrit")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--split", default="test")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--figure", type=Path, help="Image de la documentation (ex. docs/assets/figures/bandes.png)")
    args = parser.parse_args()
    path = args.run / f"band_importance_{args.split}.json"
    if args.figure and path.exists():
        result = json.loads(path.read_text())  # figure seule : mesure déjà faite
    else:
        result = measure(args.run, args.pack, args.split, args.seed)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(json.dumps(result, indent=1, ensure_ascii=False))
    if args.figure:
        figure(result, args.figure)


if __name__ == "__main__":
    main()
