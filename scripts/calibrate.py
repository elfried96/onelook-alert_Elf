"""Recalibre le seuil « inconnu » d'un run existant, sans réentraîner, à partir de ses décisions de validation.

Prérequis : `scripts/evaluate.py runs/<nom> --split val` (écrit decisions_val_model.csv).
Affiche le balayage des parts gardées sur la validation, puis écrit le seuil choisi dans config.json
(l'ancien est conservé sous seuil_inconnu_precedent). Relancer ensuite evaluate.py sur le test.
--figure trace le compromis sur le test (decisions_test_model.csv) : pour information, le choix reste fait
sur la validation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from onelook.data.labels import CLASSES  # noqa: E402
from onelook.evaluation.metrics import decision_metrics  # noqa: E402
from onelook.ood.confidence import KEEP, calibrate_threshold, decisions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SWEEP = (0.95, 0.97, 0.98, 0.99)
INK, MUTED, FLOOD, FIRE = "#14202b", "#4f5f6b", "#2a78d6", "#eb6834"


def load(run: Path, pack: Path, split: str) -> tuple[pd.DataFrame, np.ndarray]:
    index = pd.read_csv(pack / "index.csv")
    index = index[index["split"] == split].reset_index(drop=True)
    found = pd.read_csv(run / f"decisions_{split}_model.csv")
    if not (found["id"].values == index["id"].values).all():
        raise SystemExit(f"decisions_{split}_model.csv ne correspond pas à l'index : relancer evaluate.py --split {split}")
    return index, found[[f"p_{c}" for c in CLASSES]].values


def figure(index: pd.DataFrame, probs: np.ndarray, marks: dict[str, float], out: Path) -> None:
    """Rappels et fausses alertes selon le seuil « inconnu », en deux panneaux (échelles différentes)."""
    grid = np.round(np.arange(0.40, 0.951, 0.01), 2)
    rows = [decision_metrics(index, decisions(probs, t)) for t in grid]
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(7.2, 5.4), sharex=True, height_ratios=[3, 2])
    for key, color, name in (("rappel_inondation", FLOOD, "Rappel inondation"),
                             ("rappel_incendie", FIRE, "Rappel incendie")):
        values = [100 * r[key] for r in rows]
        top.plot(grid, values, color=color, linewidth=2)
        top.annotate(name, (grid[0], values[0]), xytext=(4, 6), textcoords="offset points", color=INK, fontsize=9)
    bottom.plot(grid, [100 * r["fausses_alertes"] for r in rows], color=INK, linewidth=2)
    bottom.plot(grid, [100 * r["inconnu"] for r in rows], color=MUTED, linewidth=2, linestyle="--")
    bottom.annotate("Fausses alertes", (grid[0], 100 * rows[0]["fausses_alertes"]), xytext=(4, 6),
                    textcoords="offset points", color=INK, fontsize=9)
    bottom.annotate("Part « inconnu »", (grid[-1], 100 * rows[-1]["inconnu"]), xytext=(-4, 6),
                    textcoords="offset points", color=MUTED, fontsize=9, ha="right")
    for label, t in marks.items():
        for ax in (top, bottom):
            ax.axvline(t, color=MUTED, linewidth=1, linestyle=":")
        top.annotate(f"{label}\n{t:.2f}".replace(".", ","), (t, 101), ha="center", va="bottom", fontsize=8,
                     color=MUTED, annotation_clip=False)
    top.set_ylabel("Rappel (%)", color=MUTED)
    bottom.set_ylabel("Part (%)", color=MUTED)
    bottom.set_xlabel("Seuil de confiance « inconnu »", color=MUTED)
    top.set_ylim(20, 100)
    bottom.set_ylim(0, None)
    for ax in (top, bottom):
        ax.grid(axis="y", color="#e4e8eb", linewidth=0.8)
        ax.tick_params(colors=MUTED, labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c9d1d6")
    fig.suptitle("Seuil « inconnu » : compromis sur le test (546 tuiles hors ambiguës)", x=0.01, ha="left",
                 fontsize=10, color=INK, y=1.03)
    fig.tight_layout()
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"{out.name} écrit")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path, help="Dossier runs/<nom>")
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--keep", type=float, default=KEEP, help="Part des bonnes réponses gardées")
    parser.add_argument("--dry-run", action="store_true", help="Afficher le balayage sans écrire config.json")
    parser.add_argument("--figure", type=Path, help="Image du compromis sur le test (ex. docs/assets/figures/seuil.png)")
    args = parser.parse_args()

    index, probs = load(args.run, args.pack, "val")
    known = index["label"].isin(CLASSES).values  # tuiles ambiguës exclues du calibrage
    labels = np.array([CLASSES.index(c) for c in index["label"][known]])

    print("part gardée · seuil · rappel inond. · rappel incendie · fausses alertes · inconnu (validation)")
    for keep in sorted({*SWEEP, args.keep}):
        threshold = calibrate_threshold(probs[known], labels, keep)
        m = decision_metrics(index, decisions(probs, threshold))
        print(f"{keep:.2f} · {threshold:.3f} · {m['rappel_inondation']:.0%} · {m['rappel_incendie']:.0%} · "
              f"{m['fausses_alertes']:.1%} · {m['inconnu']:.1%}")

    config_path = args.run / "config.json"
    config = json.loads(config_path.read_text())
    threshold = calibrate_threshold(probs[known], labels, args.keep)
    if args.figure:
        previous = config.get("seuil_inconnu_precedent", config["seuil_inconnu"])
        marks = {"avant": previous, "retenu": threshold} if abs(previous - threshold) > 1e-6 else {"retenu": threshold}
        figure(*load(args.run, args.pack, "test"), marks, args.figure)
    if args.dry_run:
        return
    config.setdefault("seuil_inconnu_precedent", config["seuil_inconnu"])
    config.update(seuil_inconnu=threshold, part_gardee=args.keep,
                  val=decision_metrics(index, decisions(probs, threshold)))
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"\nSeuil « inconnu » : {config['seuil_inconnu_precedent']:.3f} → {threshold:.3f} (part gardée {args.keep})")


if __name__ == "__main__":
    main()
