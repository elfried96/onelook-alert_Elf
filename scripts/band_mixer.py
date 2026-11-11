"""Ce que le mélange 1 × 1 a appris (essai « 12 bandes ») : quelles bandes chaque canal du réseau reçoit.

Lit poids_melange et importance_melange dans runs/<nom>/config.json (écrits par scripts/train.py --melange).

    uv run python scripts/band_mixer.py runs/<nom> --figure docs/assets/figures/melange_bandes.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from onelook.data.sentinel2 import SELECTED_BANDS


def show(config: dict) -> None:
    bands, weights = config["bands"], np.asarray(config["poids_melange"])
    print("canal  " + " ".join(f"{b:>5}" for b in bands))
    for name, row in zip(SELECTED_BANDS, weights):
        print(f"{name:<6} " + " ".join(f"{v:5.2f}" for v in row))
    print("\nPoids total par bande : " + ", ".join(f"{b} {v:.2f}" for b, v in config["importance_melange"].items()))


def figure(config: dict, out: Path) -> None:
    """Carte des poids (valeur absolue en couleur, valeur signée écrite), une ligne par canal du réseau."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted = "#14202b", "#4f5f6b"
    bands, weights = config["bands"], np.asarray(config["poids_melange"])
    fig, ax = plt.subplots(figsize=(9.5, 3.6))
    ax.imshow(np.abs(weights), cmap="Blues", vmin=0, vmax=1.1, aspect="auto")
    for i in range(weights.shape[0]):
        for j in range(weights.shape[1]):
            v = weights[i, j] if abs(weights[i, j]) >= 0.005 else 0.0
            ax.text(j, i, f"{v:.2f}".replace("-", "−").replace(".", ","), ha="center", va="center", fontsize=7.5,
                    color="white" if abs(v) > 0.6 else (ink if abs(v) >= 0.03 else "#a7b2ba"))
    ax.set_xticks(range(len(bands)), bands)
    ax.set_yticks(range(len(SELECTED_BANDS)), [f"canal {k + 1} (départ {b})" for k, b in enumerate(SELECTED_BANDS)])
    ax.tick_params(colors=muted, labelsize=8, length=0)
    for j, b in enumerate(bands):
        if b in SELECTED_BANDS:
            ax.get_xticklabels()[j].set_fontweight("bold")
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_title(f"Mélange appris : poids de chaque bande (colonnes) dans les 6 canaux du réseau (lignes), "
                 f"L1 = {config['l1']}".replace(".", ","), fontsize=9.5, color=ink, loc="left")
    fig.tight_layout()
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"{out.name} écrit")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    parser.add_argument("--figure", type=Path, help="Image de la documentation")
    args = parser.parse_args()
    config = json.loads((args.run / "config.json").read_text())
    if not config.get("melange"):
        raise SystemExit(f"{args.run.name} n'a pas de mélange (entraîné sans --melange)")
    show(config)
    if args.figure:
        figure(config, args.figure)


if __name__ == "__main__":
    main()
