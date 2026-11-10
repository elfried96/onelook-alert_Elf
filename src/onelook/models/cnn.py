"""Réseau léger à trois décisions apprises, pour des tuiles Sentinel-2 de 6 ou 12 bandes.

Le modèle exporté contient sa normalisation et son redimensionnement : il prend une tuile brute
(1, n, 512, 512) en réflectance et rend trois scores. « Inconnu » se décide ensuite sur la confiance.
Essai « 12 bandes » : un mélange 1 × 1 appris (BandMixer) choisit quoi garder des 12 bandes L2A.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn
from torchvision import models

from onelook.data.sentinel2 import SELECTED_BANDS

ARCHS = ("mobilenet_v3_small", "mobilenet_v3_large", "resnet18")
TILE = 512  # côté des tuiles d'entrée, fixé par le format d'évaluation


def adapt_first_conv(conv: nn.Conv2d, bands: list[str] = SELECTED_BANDS) -> nn.Conv2d:
    """Première convolution RVB → bandes Sentinel-2 (par défaut B02, B03, B04, B08, B11, B12).

    Les poids RVB pré-entraînés vont sur B04, B03, B02 ; les autres bandes reçoivent leur moyenne.
    Le tout est mis à l'échelle pour garder l'amplitude des activations.
    """
    new = nn.Conv2d(len(bands), conv.out_channels, conv.kernel_size, conv.stride, conv.padding,
                    bias=conv.bias is not None)
    with torch.no_grad():
        rgb = conv.weight  # (sorties, 3 = R, V, B, k, k)
        weight = rgb.mean(dim=1, keepdim=True).repeat(1, len(bands), 1, 1)
        for name, k in (("B04", 0), ("B03", 1), ("B02", 2)):
            if name in bands:
                weight[:, bands.index(name)] = rgb[:, k]
        new.weight.copy_(weight * 3 / len(bands))
        if conv.bias is not None:
            new.bias.copy_(conv.bias)
    return new


def backbone(arch: str, num_classes: int, pretrained: bool, bands: list[str] = SELECTED_BANDS) -> nn.Module:
    if arch.startswith("mobilenet"):
        net = getattr(models, arch)(weights="DEFAULT" if pretrained else None)
        net.features[0][0] = adapt_first_conv(net.features[0][0], bands)
        net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, num_classes)
    elif arch == "resnet18":
        net = models.resnet18(weights="DEFAULT" if pretrained else None)
        net.conv1 = adapt_first_conv(net.conv1, bands)
        net.fc = nn.Linear(net.fc.in_features, num_classes)
    else:
        raise ValueError(f"Architecture inconnue : {arch} (au choix : {ARCHS})")
    return net


class BandMixer(nn.Module):
    """Mélange 1 × 1 appris : chaque canal de sortie est une combinaison des n bandes d'entrée.

    Les poids sont normalisés ligne par ligne (norme 2 égale à 1). La pénalité L1 sur ces poids pousse alors
    chaque canal à n'utiliser que peu de bandes ; sans cette normalisation, la BatchNorm qui suit la première
    convolution laisserait la L1 rétrécir tout le mélange sans rien choisir. Au départ, le canal j recopie la
    bande SELECTED_BANDS[j] (le réseau démarre comme le modèle à 6 bandes), les autres bandes ont un petit poids.
    """

    def __init__(self, bands: list[str], out: list[str] = SELECTED_BANDS):
        super().__init__()
        self.bands = list(bands)
        raw = 0.05 * torch.randn(len(out), len(bands))
        for j, name in enumerate(out):
            raw[j, self.bands.index(name)] = 1.0
        self.raw = nn.Parameter(raw)

    def weight(self) -> torch.Tensor:
        return self.raw / self.raw.norm(dim=1, keepdim=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.conv2d(x, self.weight()[:, :, None, None])

    def penalty(self) -> torch.Tensor:
        return self.weight().abs().sum()

    def importance(self) -> dict[str, float]:
        """Poids total de chaque bande d'entrée dans le mélange (somme des valeurs absolues)."""
        return {b: round(float(v), 4) for b, v in zip(self.bands, self.weight().detach().abs().sum(0).cpu())}


class OneLookNet(nn.Module):
    def __init__(self, arch: str, mean: list[float], std: list[float], size: int = 256, num_classes: int = 3,
                 pretrained: bool = True, bands: list[str] = SELECTED_BANDS, mixer: bool = False):
        super().__init__()
        self.size = size
        self.register_buffer("mean", torch.tensor(mean).view(1, -1, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, -1, 1, 1))
        self.mixer = BandMixer(bands) if mixer else None
        self.net = backbone(arch, num_classes, pretrained, SELECTED_BANDS if mixer else list(bands))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = (x - self.mean) / self.std
        if self.mixer is not None:
            x = self.mixer(x)
        if self.size != TILE:
            x = F.interpolate(x, size=(self.size, self.size), mode="bilinear", align_corners=False)
        return self.net(x)
