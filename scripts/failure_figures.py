"""Planches des erreurs d'un modèle sur le test, pour la page Limites et échecs.

Usage : uv run python scripts/failure_figures.py runs/mobilenet_v3_small_256 [--prefix echecs] [--max 8]
Lit les décisions (decisions_test_model.csv) et le paquet ; écrit docs/assets/figures/<prefix>_*.jpg.
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


def sheet(rows: pd.DataFrame, pack: Path, title: str, name: str, per_row: int = 4, out: Path = OUT) -> None:
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
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / name, dpi=55, bbox_inches="tight", pil_kwargs={"quality": 82})
    plt.close(fig)
    print(f"{name} : {n} tuiles, {(out / name).stat().st_size / 1024:.0f} Ko")


def confusion_figure(df: pd.DataFrame, title: str, name: str, out: Path = OUT) -> None:
    """Matrice de confusion : nombre de tuiles par vérité (lignes) et décision (colonnes).
    La teinte suit la part de la ligne (rampe bleue séquentielle), le texte donne nombre et part."""
    from matplotlib.colors import LinearSegmentedColormap

    truths = [("normal", "Normal"), ("alerte_inondation", "Inondation"), ("alerte_incendie", "Incendie")]
    decisions = truths + [("inconnu", "Inconnu")]
    df = df[df.label.isin([t for t, _ in truths])]
    counts = pd.crosstab(df.label, df.decision).reindex(index=[t for t, _ in truths],
                                                         columns=[d for d, _ in decisions], fill_value=0)
    share = counts.div(counts.sum(axis=1), axis=0).to_numpy()
    ramp = LinearSegmentedColormap.from_list("bleu", ["#ffffff", "#cde2fb", "#86b6ef", "#2a78d6", "#184f95"])
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.imshow(share, cmap=ramp, vmin=0, vmax=1, aspect="auto")
    for i in range(share.shape[0]):
        for j in range(share.shape[1]):
            ink = "#ffffff" if share[i, j] > 0.55 else "#14202b"
            pct = f"{share[i, j]:.1%}" if 0 < share[i, j] < 0.1 else f"{share[i, j]:.0%}"
            ax.text(j, i, f"{counts.iat[i, j]}\n{pct.replace('.', ',')}", ha="center", va="center", fontsize=10,
                    color=ink)
    ax.set_xticks(range(len(decisions)), [f"Décision\n{n}" for _, n in decisions], fontsize=9, color="#4f5f6b")
    ax.set_yticks(range(len(truths)), [f"Vérité {n}\n({counts.iloc[i].sum()} tuiles)" for i, (_, n) in enumerate(truths)],
                  fontsize=9, color="#4f5f6b")
    ax.set_xticks([x + 0.5 for x in range(len(decisions) - 1)], minor=True)
    ax.set_yticks([y + 0.5 for y in range(len(truths) - 1)], minor=True)
    ax.grid(which="minor", color="#ffffff", linewidth=2)
    ax.tick_params(which="both", length=0)
    ax.xaxis.tick_top()
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, fontsize=10, loc="left", color="#14202b", pad=34)
    fig.tight_layout()
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / name, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"{name} : {len(df)} tuiles")


def load(run: Path, pack: Path) -> pd.DataFrame:
    decisions = pd.read_csv(run / "decisions_test_model.csv")
    index = pd.read_csv(pack / "index.csv")
    df = decisions.drop(columns="label").merge(index, on="id")  # étiquettes de l'index actuel
    df["conf"] = df[[c for c in df if c.startswith("p_")]].max(axis=1)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--prefix", default="echecs", help="Début du nom des fichiers")
    parser.add_argument("--max", type=int, default=8, help="Nombre maximal de tuiles par planche")
    args = parser.parse_args()
    df = load(args.run, args.pack)
    pre, top = args.prefix, args.max
    confusion_figure(df, "Matrice de confusion sur le test (tuiles ambiguës exclues)", f"{pre}_matrice_confusion.png",
                     out=args.out)

    normal = df[df.label == "normal"]
    sheet(normal[normal.decision == "alerte_incendie"].sort_values("conf", ascending=False).head(top), args.pack,
          "Fausses alertes incendie (normales prises pour un incendie)", f"{pre}_fausses_alertes_incendie.jpg",
          out=args.out)
    sheet(normal[normal.decision == "alerte_inondation"], args.pack,
          "Fausses alertes inondation", f"{pre}_fausses_alertes_inondation.jpg", per_row=3, out=args.out)
    flood = df[df.label == "alerte_inondation"]
    sheet(flood[flood.decision != "alerte_inondation"].sort_values("frac_flood").head(top), args.pack,
          "Inondations manquées (contour bleu : eau d'inondation annotée)", f"{pre}_inondations_manquees.jpg",
          per_row=5, out=args.out)
    fire = df[df.label == "alerte_incendie"]
    sheet(fire[fire.decision != "alerte_incendie"].sort_values("frac_burned").head(top), args.pack,
          "Incendies manqués (contour jaune : zone brûlée annotée)", f"{pre}_incendies_manques.jpg", out=args.out)


if __name__ == "__main__":
    main()
