"""Moteur d'analyse de la démo : une passe ONNX, puis les mesures qui expliquent la décision.

Le modèle exporté rend 3 scores ; on lui ajoute en sortie ses descripteurs (les 576 valeurs avant la
décision), qui servent aux voisins et à la distance de Mahalanobis. Tout tourne sur un cœur de processeur.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort

from onelook.data.l2a import SCL_CLOUDY, SCL_NO_DATA
from onelook.data.labels import CLASSES
from onelook.data.water import permanent_water
from onelook.demo.describe import Facts, describe
from onelook.ood.confidence import decisions, softmax

OCCLUSION_GRID = 8  # 8 × 8 cases de 64 pixels


def with_features(model_path: Path) -> bytes:
    """Le modèle ONNX avec une sortie de plus : les descripteurs (entrée de la couche dense finale)."""
    model = onnx.load(model_path)
    flatten = [n.output[0] for n in model.graph.node if n.op_type == "Flatten"]
    if flatten:
        model.graph.output.append(onnx.ValueInfoProto(name=flatten[0]))
    return model.SerializeToString()


def spectral(image: np.ndarray, scl: np.ndarray | None, water: np.ndarray | None) -> dict:
    """Parts de la tuile : eau (NDWI), végétation (NDVI), sol de type brûlé (NBR), nuages, eau permanente."""
    blue, green, red, nir, swir1, swir2 = image
    eps = 1e-6
    ndwi = (green - nir) / (green + nir + eps)
    ndvi = (nir - red) / (nir + red + eps)
    nbr = (nir - swir2) / (nir + swir2 + eps)
    valid = image.sum(axis=0) > 0
    clear = valid if scl is None else valid & ~np.isin(scl, SCL_CLOUDY) & (scl != SCL_NO_DATA)
    n = max(valid.sum(), 1)
    out = {
        "water": float(((ndwi > 0) & clear).sum() / n),
        "vegetation": float(((ndvi > 0.4) & clear).sum() / n),
        "burn_like": float(((nbr < -0.1) & (ndwi <= 0) & clear).sum() / n),
        "cloud": None if scl is None else float(np.isin(scl, SCL_CLOUDY).sum() / n),
        "permanent_water": None,
    }
    if water is not None:
        out["permanent_water"] = float(permanent_water(water).mean())
    return out


class Engine:
    def __init__(self, run: Path, bank: Path | None = None, threads: int = 1):
        self.run = Path(run)
        self.config = json.loads((self.run / "config.json").read_text())
        self.threshold = float(self.config["seuil_inconnu"])
        options = ort.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = threads, 1
        model = with_features(self.run / "model.onnx")
        self.session = ort.InferenceSession(model, options, providers=["CPUExecutionProvider"])
        # L'occlusion (64 passes) n'est pas la mesure de temps : elle peut prendre plusieurs cœurs
        batch_options = ort.SessionOptions()
        batch_options.intra_op_num_threads = 4
        self.batch_session = ort.InferenceSession(model, batch_options, providers=["CPUExecutionProvider"])
        self.size_mb = (self.run / "model.onnx").stat().st_size / 1e6
        self.bank = None
        if bank is not None and Path(bank).exists():
            data = np.load(bank, allow_pickle=False)
            self.bank = {k: data[k] for k in data.files}
            self.bank_meta = json.loads(str(self.bank.pop("meta")))

    def forward(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        outputs = self.session.run(None, {"image": image[None].astype(np.float32)})
        return softmax(outputs[0])[0], (outputs[1][0] if len(outputs) > 1 else None)

    def predict(self, image: np.ndarray) -> dict:
        """Une passe chronométrée : probabilités, décision, descripteurs."""
        self.forward(image)  # préchauffage : la première passe d'une session est plus lente
        start = time.perf_counter()
        probs, features = self.forward(image)
        ms = (time.perf_counter() - start) * 1000
        decision = str(decisions(probs[None], self.threshold)[0])
        return {"probs": probs, "features": features, "decision": decision, "ms": ms}

    def occlusion(self, image: np.ndarray, probs: np.ndarray, grid: int = OCCLUSION_GRID) -> np.ndarray:
        """Baisse de la probabilité de la classe retenue (en points) quand on remplace une case par la moyenne."""
        k = int(probs.argmax())
        step = image.shape[1] // grid
        mean = image.reshape(image.shape[0], -1).mean(axis=1)[:, None, None]
        batch = np.repeat(image[None], grid * grid, axis=0)
        for i in range(grid):
            for j in range(grid):
                batch[i * grid + j, :, i * step:(i + 1) * step, j * step:(j + 1) * step] = mean
        scores = np.concatenate([softmax(self.batch_session.run(None, {"image": batch[b:b + 16]})[0])
                                 for b in range(0, len(batch), 16)])
        return (100 * (probs[k] - scores[:, k])).reshape(grid, grid)

    def neighbours(self, features: np.ndarray, k: int = 5) -> list[dict]:
        if self.bank is None or features is None:
            return []
        dist = np.linalg.norm(self.bank["features"] - features, axis=1)
        order = np.argsort(dist)[:k]
        return [{"id": str(self.bank["ids"][i]), "label": str(self.bank["labels"][i]),
                 "place": str(self.bank["places"][i])} for i in order]

    def atypicity(self, features: np.ndarray) -> float | None:
        """Distance de Mahalanobis (au carré) au plus proche nuage de classe des tuiles d'entraînement."""
        if self.bank is None or features is None:
            return None
        diffs = features[None] - self.bank["means"]
        return float(np.min(np.einsum("ij,jk,ik->i", diffs, self.bank["precision"], diffs)))

    def analyse(self, image: np.ndarray, scl: np.ndarray | None = None, water: np.ndarray | None = None,
                meta: dict | None = None) -> dict:
        meta = meta or {}
        result = self.predict(image)
        start = time.perf_counter()
        drop = self.occlusion(image, result["probs"])
        occlusion_ms = (time.perf_counter() - start) * 1000
        measures = spectral(image, scl, water)
        neighbours = self.neighbours(result["features"])
        atypicity = self.atypicity(result["features"])
        probs = {c: float(p) for c, p in zip(CLASSES, result["probs"])}
        facts = Facts(decision=result["decision"], probs=probs, threshold=self.threshold, date=meta.get("date"),
                      place=meta.get("place"), lat=meta.get("lat"), lon=meta.get("lon"), occlusion=drop,
                      neighbours=neighbours, atypicity=atypicity,
                      atypicity_limit=self.bank_meta["limite_atypique"] if self.bank is not None else None,
                      **measures)
        return {
            "decision": result["decision"], "probs": probs, "seuil": self.threshold,
            "temps_ms": round(result["ms"], 1), "occlusion_ms": round(occlusion_ms), "occlusion": drop.round(2).tolist(),
            "mesures": measures, "voisins": neighbours, "atypicite": atypicity,
            "description": describe(facts),
        }
