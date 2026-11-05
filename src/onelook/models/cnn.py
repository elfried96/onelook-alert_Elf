"""Réseau léger à trois décisions apprises, pour 6 bandes Sentinel-2.

Le modèle exporté contient sa normalisation et son redimensionnement : il prend une tuile brute
(1, 6, 512, 512) en réflectance et rend trois scores. « Inconnu » se décide ensuite sur la confiance.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn
from torchvision import models

ARCHS = ("mobilenet_v3_small", "mobilenet_v3_large", "resnet18")
TILE = 512  # côté des tuiles d'entrée, fixé par le format d'évaluation


def adapt_first_conv(conv: nn.Conv2d, in_channels: int = 6) -> nn.Conv2d:
    """Première convolution RVB → 6 bandes (B02, B03, B04, B08, B11, B12).

    Les poids RVB pré-entraînés vont sur B04, B03, B02 ; les bandes infrarouges reçoivent leur moyenne.
    Le tout est mis à l'échelle pour garder l'amplitude des activations.
    """
    new = nn.Conv2d(in_channels, conv.out_channels, conv.kernel_size, conv.stride, conv.padding,
                    bias=conv.bias is not None)
    with torch.no_grad():
        rgb = conv.weight  # (sorties, 3 = R, V, B, k, k)
        weight = torch.empty(conv.out_channels, in_channels, *conv.kernel_size)
        weight[:, 0], weight[:, 1], weight[:, 2] = rgb[:, 2], rgb[:, 1], rgb[:, 0]
        weight[:, 3:] = rgb.mean(dim=1, keepdim=True)
        new.weight.copy_(weight * 3 / in_channels)
        if conv.bias is not None:
            new.bias.copy_(conv.bias)
    return new


def backbone(arch: str, num_classes: int, pretrained: bool) -> nn.Module:
    if arch.startswith("mobilenet"):
        net = getattr(models, arch)(weights="DEFAULT" if pretrained else None)
        net.features[0][0] = adapt_first_conv(net.features[0][0])
        net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, num_classes)
    elif arch == "resnet18":
        net = models.resnet18(weights="DEFAULT" if pretrained else None)
        net.conv1 = adapt_first_conv(net.conv1)
        net.fc = nn.Linear(net.fc.in_features, num_classes)
    else:
        raise ValueError(f"Architecture inconnue : {arch} (au choix : {ARCHS})")
    return net


class OneLookNet(nn.Module):
    def __init__(self, arch: str, mean: list[float], std: list[float], size: int = 256, num_classes: int = 3,
                 pretrained: bool = True):
        super().__init__()
        self.size = size
        self.register_buffer("mean", torch.tensor(mean).view(1, -1, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, -1, 1, 1))
        self.net = backbone(arch, num_classes, pretrained)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = (x - self.mean) / self.std
        if self.size != TILE:
            x = F.interpolate(x, size=(self.size, self.size), mode="bilinear", align_corners=False)
        return self.net(x)
