"""Planches des erreurs d'un modèle sur le test, pour la page Limites et échecs.

Usage : uv run python scripts/failure_figures.py runs/mobilenet_v3_small_256
Lit les décisions (decisions_test_model.csv) et le paquet ; écrit docs/assets/figures/echecs_*.jpg.
Chaque tuile est montrée en couleurs naturelles et en infrarouge court (B12, B08, B04), où le brûlé
ressort en rouge-brun et l'eau en noir, avec la vérité terrain en contour.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from onelook.data.pack import TRUTH_BURNED, TRUTH_FLOOD, read_packed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "figures"
NAMES = {"normal": "normal", "alerte_inondation": "inondation", "alerte_incendie": "incendie", "inconnu": "inconnu"}


def stretch(rgb: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(rgb, [2, 98])
    return np.clip((rgb - lo) / (hi - lo + 1e-6), 0, 1)


def views(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tile = read_packed(path)
    image = tile["image"]  # B02, B03, B04, B08, B11, B12
    natural = stretch(np.dstack([image[2], image[1], image[0]]))
    swir = stretch(np.dstack([image[5], image[3], image[2]]))
    return natural, swir, tile["truth"]


def sheet(rows: pd.DataFrame, pack: Path, title: str, name: str, per_row: int = 4) -> None:
    n = len(rows)
    cols = min(per_row, n)
    lines = int(np.ceil(n / cols))
    fig, axes = plt.subplots(lines * 2, cols, figsize=(3.2 * cols, 6.4 * lines), squeeze=False)
    for k, row in enumerate(rows.itertuples()):
        natural, swir, truth = views(pack / row.path)
        r, c = 2 * (k // cols), k % cols
        for ax, img in ((axes[r, c], natural), (axes[r + 1, c], swir)):
            ax.imshow(img)
            for code, color in ((TRUTH_FLOOD, "#1d5f96"), (TRUTH_BURNED, "#ffd23f")):
                if (truth == code).any():
                    ax.contour(truth == code, levels=[0.5], colors=color, linewidths=0.9)
        share = row.frac_burned if row.label == "alerte_incendie" or row.source.startswith("cabuar") else row.frac_flood
        axes[r, c].set_title(f"{row.id[:22]}\nvérité {NAMES.get(row.label, row.label)} ({share:.0%}) → "
                             f"{NAMES[row.decision]} ({row.conf:.2f})", fontsize=7.5)
        axes[r + 1, c].set_title("infrarouge court", fontsize=7, color="#4f5f6b")
    for ax in axes.ravel():
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
    for k in range(n, lines * cols):
        axes[2 * (k // cols), k % cols].set_visible(False)
        axes[2 * (k // cols) + 1, k % cols].set_visible(False)
    fig.suptitle(title, fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=55, bbox_inches="tight", pil_kwargs={"quality": 82})
    plt.close(fig)
    print(f"{name} : {n} tuiles, {(OUT / name).stat().st_size / 1024:.0f} Ko")


def load(run: Path, pack: Path) -> pd.DataFrame:
    decisions = pd.read_csv(run / "decisions_test_model.csv")
    index = pd.read_csv(pack / "index.csv")
    df = decisions.merge(index, on=["id", "label"])
    df["conf"] = df[[c for c in df if c.startswith("p_")]].max(axis=1)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    args = parser.parse_args()
    df = load(args.run, args.pack)

    normal = df[df.label == "normal"]
    sheet(normal[normal.decision == "alerte_incendie"].sort_values("conf", ascending=False).head(8), args.pack,
          "Fausses alertes incendie (normales prises pour un incendie)", "echecs_fausses_alertes_incendie.jpg")
    sheet(normal[normal.decision == "alerte_inondation"], args.pack,
          "Fausses alertes inondation", "echecs_fausses_alertes_inondation.jpg", per_row=3)
    flood = df[df.label == "alerte_inondation"]
    sheet(flood[flood.decision != "alerte_inondation"].sort_values("frac_flood"), args.pack,
          "Inondations manquées (contour bleu : eau d'inondation annotée)", "echecs_inondations_manquees.jpg", per_row=5)
    fire = df[df.label == "alerte_incendie"]
    sheet(fire[fire.decision != "alerte_incendie"].sort_values("frac_burned").head(8), args.pack,
          "Incendies manqués (contour jaune : zone brûlée annotée)", "echecs_incendies_manques.jpg")


if __name__ == "__main__":
    main()
