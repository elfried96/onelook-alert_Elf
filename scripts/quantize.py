"""Quantifie un modèle exporté (ONNX), sans réentraîner : runs/<nom>/model_<mode>.onnx.

Trois modes, tous avec des poids int8 par canal :
- int8 : activations aussi en int8 (quantification statique, format QDQ) ;
- a16w8 : activations en 16 bits ;
- poids : poids seuls, calculs en flottant (le fichier rétrécit, pas le calcul).
Pour int8 et a16w8, les plages des activations sont mesurées sur des tuiles d'**entraînement**, jamais
de validation ni de test, réparties entre les classes. Évaluer ensuite avec :
    uv run python scripts/evaluate.py runs/<nom> --model model_<mode>.onnx --split test

Constat sur MobileNetV3-Small (9 nov, docs/results.md) : en int8 complet, le réseau répond « normal »
partout. La première convolution sort des valeurs de -160 à 120 pour un écart-type de 2,4 (pixels très
brillants) : 8 bits ne gardent pas les détails utiles.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np
import onnx
import pandas as pd
from onnx import helper, numpy_helper
from onnxruntime.quantization import (CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType,
                                      quantize_static)
from onnxruntime.quantization.shape_inference import quant_pre_process

from onelook.data.labels import CLASSES
from onelook.data.pack import read_packed

ROOT = Path(__file__).resolve().parents[1]


class Tiles(CalibrationDataReader):
    def __init__(self, pack: Path, paths: list[str]):
        self.pack, self.paths = pack, iter(paths)

    def get_next(self) -> dict | None:
        path = next(self.paths, None)
        return None if path is None else {"image": read_packed(self.pack / path)["image"][None]}


def calibration_paths(pack: Path, n: int, seed: int = 0) -> list[str]:
    """n tuiles d'entraînement, autant par classe que possible (les ambiguës écartées)."""
    index = pd.read_csv(pack / "index.csv")
    train = index[(index["split"] == "train") & index["label"].isin(CLASSES)]
    per_class = n // len(CLASSES)
    picked = [g.sample(min(per_class, len(g)), random_state=seed) for _, g in train.groupby("label")]
    return pd.concat(picked)["path"].tolist()


def weights_only(src: Path, dst: Path) -> None:
    """Poids des Conv et Gemm en int8 symétrique par canal de sortie, suivis d'un DequantizeLinear."""
    model = onnx.load(src)
    inits = {t.name: t for t in model.graph.initializer}
    nodes = []
    for node in model.graph.node:
        if node.op_type in ("Conv", "Gemm") and node.input[1] in inits:
            name = node.input[1]
            w = numpy_helper.to_array(inits[name])
            scale = (np.abs(w).max(axis=tuple(range(1, w.ndim))) / 127).astype(np.float32)
            scale[scale == 0] = 1
            q = np.clip(np.round(w / scale.reshape(-1, *[1] * (w.ndim - 1))), -127, 127).astype(np.int8)
            model.graph.initializer.remove(inits[name])
            model.graph.initializer.extend([numpy_helper.from_array(q, f"{name}_q"),
                                            numpy_helper.from_array(scale, f"{name}_s"),
                                            numpy_helper.from_array(np.zeros_like(scale, np.int8), f"{name}_z")])
            nodes.append(helper.make_node("DequantizeLinear", [f"{name}_q", f"{name}_s", f"{name}_z"], [name], axis=0))
        nodes.append(node)
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    onnx.checker.check_model(model)
    onnx.save(model, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path, help="Dossier runs/<nom> avec model.onnx")
    parser.add_argument("--mode", default="int8", choices=["int8", "a16w8", "poids"])
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--calib", type=int, default=150, help="Nombre de tuiles d'entraînement pour les plages")
    parser.add_argument("--method", default="MinMax", choices=["MinMax", "Entropy", "Percentile"])
    args = parser.parse_args()

    source, out = args.run / "model.onnx", args.run / f"model_{args.mode}.onnx"
    if args.mode == "poids":
        weights_only(source, out)
        note = "poids seuls"
    else:
        paths = calibration_paths(args.pack, args.calib)
        activations = QuantType.QUInt8 if args.mode == "int8" else QuantType.QUInt16
        with tempfile.TemporaryDirectory() as tmp:
            prepared = Path(tmp) / "prepared.onnx"
            quant_pre_process(str(source), str(prepared), skip_symbolic_shape=True)  # formes fixes
            quantize_static(str(prepared), str(out), Tiles(args.pack, paths), quant_format=QuantFormat.QDQ,
                            activation_type=activations, weight_type=QuantType.QInt8, per_channel=True,
                            calibrate_method=CalibrationMethod[args.method])
        note = f"plages mesurées sur {len(paths)} tuiles d'entraînement"
    print(f"{out.name} : {out.stat().st_size / 1e6:.2f} Mo (au lieu de {source.stat().st_size / 1e6:.2f}), {note}")


if __name__ == "__main__":
    main()
