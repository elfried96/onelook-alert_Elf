"""Approches de référence : seuils NDWI / NBR, puis classifieur sur statistiques par bande.

Usage (sur Colab, après le téléchargement du paquet) : uv run python scripts/baselines.py [--limit N]
Les seuils et le classifieur sont ajustés sur l'entraînement seulement, choisis sur rien d'autre,
puis mesurés sur la validation et le test. Écrit runs/baselines/results.json.
"""

from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from tqdm import tqdm

from onelook.data.labels import AMBIGUOUS
from onelook.data.pack import read_packed
from onelook.evaluation.metrics import confusion, decision_metrics, format_row
from onelook.models.baselines import fit_thresholds, stat_features, threshold_features

ROOT = Path(__file__).resolve().parents[1]


def features(pack: Path, index: pd.DataFrame) -> dict[str, np.ndarray]:
    water, fire, stats = [], [], []
    for path in tqdm(index["path"], desc="Indices et statistiques"):
        image = read_packed(pack / path)["image"]
        w, f = threshold_features(image)
        water.append(w)
        fire.append(f)
        stats.append(stat_features(image))
    return {"water": np.stack(water), "fire": np.stack(fire), "stats": np.stack(stats)}


def per_tile_ms(fn, pack: Path, paths: list[str]) -> float:
    """Temps moyen par tuile, lecture du disque exclue."""
    images = [read_packed(pack / p)["image"] for p in paths]
    start = time.perf_counter()
    for image in images:
        fn(image)
    return (time.perf_counter() - start) / len(images) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "baselines")
    parser.add_argument("--limit", type=int, help="Nombre de tuiles par partie (essai rapide)")
    args = parser.parse_args()

    index = pd.read_csv(args.pack / "index.csv")
    if args.limit:
        index = index.sample(frac=1, random_state=0).groupby("split").head(args.limit)
    index = index.reset_index(drop=True)
    feats = features(args.pack, index)
    train = (index["split"] == "train").to_numpy() & (index["label"] != AMBIGUOUS).to_numpy()
    labels = index["label"].to_numpy(dtype=object)

    rule, train_f1 = fit_thresholds(feats["water"][train], feats["fire"][train], labels[train])
    print(f"Seuils retenus sur l'entraînement : {rule} (F1 macro {train_f1:.3f})")
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, class_weight="balanced", random_state=0)
    clf.fit(feats["stats"][train], labels[train])

    approaches = {
        "Seuils NDWI + NBR": (rule.predict(feats["water"], feats["fire"]), len(json.dumps(rule.__dict__)) / 1e6,
                              lambda im: rule.predict(*(x[None] for x in threshold_features(im)))),
        "Classifieur sur statistiques": (clf.predict(feats["stats"]), len(pickle.dumps(clf)) / 1e6,
                                         lambda im: clf.predict(stat_features(im)[None])),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    results, test_paths = {}, index.loc[index["split"] == "test", "path"].head(50).tolist()
    for name, (preds, size_mb, one) in approaches.items():
        ms = per_tile_ms(one, args.pack, test_paths)
        results[name] = {"taille_mo": size_mb, "temps_ms": ms}
        for split in ("val", "test"):
            sel = (index["split"] == split).to_numpy()
            results[name][split] = decision_metrics(index[sel], preds[sel])
        print(f"\n{name} · test\n{confusion(index[index.split == 'test'], preds[(index.split == 'test').to_numpy()])}")
        print(format_row(name, results[name]["test"], size_mb, ms))
    results["seuils"] = rule.__dict__
    (args.out / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    with open(args.out / "classifier.pkl", "wb") as f:
        pickle.dump(clf, f)
    print(f"\nRésultats -> {args.out / 'results.json'}")


if __name__ == "__main__":
    main()
