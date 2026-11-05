"""Évalue un modèle exporté (ONNX) sur une partie du paquet : décisions, mesures, taille et temps.

Usage : uv run python scripts/evaluate.py runs/<nom> [--split test]
Tourne en local comme sur Colab (onnxruntime, CPU) : c'est une évaluation, pas un entraînement.
Le temps est mesuré tuile par tuile, sur un seul cœur : l'approximation la plus proche d'un calculateur embarqué.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
from tqdm import tqdm

from onelook.data.pack import read_packed
from onelook.evaluation.metrics import confusion, decision_metrics, format_row
from onelook.ood.confidence import decisions, softmax

ROOT = Path(__file__).resolve().parents[1]


def session(model: Path, threads: int) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    return ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path, help="Dossier runs/<nom> avec model.onnx et config.json")
    parser.add_argument("--model", default="model.onnx", help="Fichier ONNX du dossier (ex. model_int8.onnx)")
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--split", default="test")
    parser.add_argument("--timing", type=int, default=50, help="Nombre de tuiles pour mesurer le temps")
    args = parser.parse_args()

    config = json.loads((args.run / "config.json").read_text())
    index = pd.read_csv(args.pack / "index.csv")
    index = index[index["split"] == args.split].reset_index(drop=True)
    model = args.run / args.model

    fast = session(model, threads=4)
    logits = []
    for path in tqdm(index["path"], desc=f"Décisions ({args.split})"):
        logits.append(fast.run(None, {"image": read_packed(args.pack / path)["image"][None]})[0][0])
    probs = softmax(np.stack(logits))
    preds = decisions(probs, config["seuil_inconnu"])
    metrics = decision_metrics(index, preds)

    single = session(model, threads=1)
    images = [read_packed(args.pack / p)["image"][None] for p in index["path"].head(args.timing)]
    single.run(None, {"image": images[0]})  # préchauffage
    times = []
    for image in images:
        start = time.perf_counter()
        single.run(None, {"image": image})
        times.append((time.perf_counter() - start) * 1000)
    size_mb, time_ms = model.stat().st_size / 1e6, float(np.median(times))

    print(confusion(index, preds), "\n")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print("\n" + format_row(f"{config['arch']} {config['size']} ({args.model})", metrics, size_mb, time_ms))
    result = {"split": args.split, "modele": args.model, "taille_mo": size_mb, "temps_ms_1_coeur": time_ms, **metrics}
    (args.run / f"eval_{args.split}_{Path(args.model).stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    pd.DataFrame({"id": index["id"], "label": index["label"], "decision": preds,
                  **{f"p_{c}": probs[:, i] for i, c in enumerate(config["classes"])}}).to_csv(
        args.run / f"decisions_{args.split}_{Path(args.model).stem}.csv", index=False)


if __name__ == "__main__":
    main()
