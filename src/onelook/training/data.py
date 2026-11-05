"""Lecture du paquet pour PyTorch (groupe « train », sur Colab uniquement)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, WeightedRandomSampler

from onelook.data.labels import AMBIGUOUS, CLASSES, NORMAL
from onelook.data.pack import read_packed
from onelook.evaluation.metrics import CALIFORNIA_SOURCES


def trainable(index: pd.DataFrame, split: str) -> pd.DataFrame:
    """Tuiles d'une partie, sans les ambiguës."""
    return index[(index["split"] == split) & (index["label"] != AMBIGUOUS)].reset_index(drop=True)


def augment(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Rotations d'un quart de tour et miroirs : une vue satellite n'a pas de « haut »."""
    image = np.rot90(image, k=int(rng.integers(4)), axes=(1, 2))
    if rng.random() < 0.5:
        image = image[:, :, ::-1]
    return image


class PackDataset(Dataset):
    def __init__(self, pack: Path, index: pd.DataFrame, train: bool = False, seed: int = 0):
        self.pack, self.index, self.train = Path(pack), index.reset_index(drop=True), train
        self.labels = np.array([CLASSES.index(label) for label in self.index["label"]])
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, i: int):
        image = read_packed(self.pack / self.index["path"].iat[i])["image"]
        if self.train:
            image = augment(image, self.rng)
        return torch.from_numpy(np.ascontiguousarray(image)), int(self.labels[i])


def balanced_sampler(index: pd.DataFrame, num_samples: int | None = None) -> WeightedRandomSampler:
    """Chaque décision pèse autant ; parmi les normales, la Californie pèse autant que le reste du monde.

    Les normales sont à 76 % californiennes : sans ce rééquilibrage, le modèle pourrait apprendre
    « paysage californien » plutôt que « feu ».
    """
    weights = np.zeros(len(index))
    for label in CLASSES:
        sel = (index["label"] == label).to_numpy()
        if label == NORMAL:
            california = sel & index["source"].isin(CALIFORNIA_SOURCES).to_numpy()
            for part in (california, sel & ~california):
                weights[part] = 0.5 / max(part.sum(), 1)
        else:
            weights[sel] = 1.0 / max(sel.sum(), 1)
    return WeightedRandomSampler(torch.as_tensor(weights), num_samples or len(index), replacement=True)


def band_stats(pack: Path, index: pd.DataFrame, n: int = 200, seed: int = 0) -> tuple[list[float], list[float]]:
    """Moyenne et écart-type de chaque bande, sur un échantillon de l'entraînement."""
    sample = index.sample(min(n, len(index)), random_state=seed)
    images = np.stack([read_packed(pack / p)["image"][:, ::4, ::4] for p in sample["path"]])
    return images.mean(axis=(0, 2, 3)).tolist(), images.std(axis=(0, 2, 3)).tolist()
