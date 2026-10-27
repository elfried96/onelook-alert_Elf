"""Découpage spatial : des zones géographiques entières, jamais des tuiles isolées, vont dans une partie."""

from __future__ import annotations

import numpy as np


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def spatial_zones(lat, lon, max_km: float) -> np.ndarray:
    """Numéro de zone de chaque tuile : deux tuiles à moins de max_km sont dans la même zone (de proche en proche)."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    parent = np.arange(len(lat))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(lat)):
        close = np.nonzero(haversine_km(lat[i], lon[i], lat[i + 1:], lon[i + 1:]) < max_km)[0] + i + 1
        for j in close:
            a, b = root(i), root(j)
            if a != b:
                parent[a] = b
    roots = np.array([root(i) for i in range(len(lat))])
    _, zones = np.unique(roots, return_inverse=True)
    return zones


def assign_zones(zones, positives, ratios: dict[str, float]) -> dict[int, str]:
    """Attribue chaque zone à une partie pour approcher les proportions voulues de tuiles positives, puis de tuiles.

    Glouton et déterministe : les zones les plus riches en positifs d'abord, chacune dans la partie la plus en retard.
    """
    zones, positives = np.asarray(zones), np.asarray(positives, bool)
    ids = np.unique(zones)
    pos = {z: int(positives[zones == z].sum()) for z in ids}
    size = {z: int((zones == z).sum()) for z in ids}
    total_pos, total = max(sum(pos.values()), 1), len(zones)
    got_pos = dict.fromkeys(ratios, 0)
    got = dict.fromkeys(ratios, 0)
    out = {}
    for z in sorted(ids, key=lambda z: (-pos[z], -size[z], z)):
        if pos[z]:
            split = max(ratios, key=lambda s: (ratios[s] - got_pos[s] / total_pos, ratios[s] - got[s] / total))
        else:
            split = max(ratios, key=lambda s: ratios[s] - got[s] / total)
        out[int(z)] = split
        got_pos[split] += pos[z]
        got[split] += size[z]
    return out
