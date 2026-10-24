"""Télécharge un petit échantillon de données pour l'exploration.

- Sen1Floods11 : les masques des 446 tuiles (~3 Mo) pour les statistiques,
  et les images Sentinel-2 de quelques tuiles choisies (~2 Mo chacune).
- CaBuAr : quelques tuiles 512 × 512, lues à distance dans le fichier HDF5 sans le télécharger en entier.

Usage : uv run python scripts/download_samples.py
Aucun entraînement : ce script ne fait que télécharger et mesurer.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import fsspec
import h5py
import hdf5plugin  # noqa: F401  (décompression BZip2 des fichiers CaBuAr)
import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from tqdm import tqdm

from onelook.data import sources
from onelook.data.sentinel2 import BANDS_L2A

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw"


def sen1floods11(n_flood_countries: int, n_normal: int) -> None:
    out = DATA / "sen1floods11"
    tiles = sources.list_sen1floods11_tiles()
    print(f"Sen1Floods11 : {len(tiles)} tuiles annotées")

    stats = {}
    for tile in tqdm(tiles, desc="Masques"):
        label_path = sources.download(sources.sen1floods11_url(tile, "LabelHand"), out / "LabelHand" / f"{tile}_LabelHand.tif")
        jrc_path = sources.download(sources.sen1floods11_url(tile, "JRCWaterHand"), out / "JRCWaterHand" / f"{tile}_JRCWaterHand.tif")
        label = sources.read_band_stack(label_path)[0]
        permanent = sources.read_band_stack(jrc_path)[0]
        stats[tile] = {"country": tile.split("_")[0], **sources.flood_stats(label, permanent)}
    sources.save_json(stats, out / "stats.json")

    # Une tuile très inondée par pays, parmi les pays les plus touchés, et quelques tuiles sans inondation
    visible = {t: s for t, s in stats.items() if s["valid"] > 0.8}
    best_by_country: dict[str, str] = {}
    for tile, s in visible.items():
        best = best_by_country.get(s["country"])
        if best is None or s["flood"] > visible[best]["flood"]:
            best_by_country[s["country"]] = tile
    flooded = sorted(best_by_country.values(), key=lambda t: -visible[t]["flood"])[:n_flood_countries]
    dry = sorted((t for t, s in visible.items() if s["flood"] < 0.001), key=lambda t: -visible[t]["valid"])
    normal = dry[:: max(1, len(dry) // n_normal)][:n_normal]

    selection = {"flood": flooded, "normal": normal}
    sources.save_json(selection, out / "samples.json")
    for tile in tqdm(flooded + normal, desc="Images Sentinel-2"):
        sources.download(sources.sen1floods11_url(tile, "S2Hand"), out / "S2Hand" / f"{tile}_S2Hand.tif")
    print("Sen1Floods11 :", selection)


def save_geotiff(array_hwc: np.ndarray, path: Path, descriptions: list[str] | None = None) -> None:
    """Enregistre un tableau (H, W, C) en GeoTIFF (C, H, W). Les tuiles CaBuAr n'ont pas de géoréférence."""
    data = np.transpose(array_hwc, (2, 0, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(
            path, "w", driver="GTiff", width=data.shape[2], height=data.shape[1],
            count=data.shape[0], dtype=data.dtype, compress="deflate",
        ) as dst:
            dst.write(data)
            if descriptions:
                for i, name in enumerate(descriptions, start=1):
                    dst.set_band_description(i, name)


def cabuar(n_candidates: int, n_samples: int) -> None:
    out = DATA / "cabuar"
    print("CaBuAr : lecture à distance (quelques minutes, seules les tuiles utiles sont lues)")
    with fsspec.open(sources.CABUAR_PATCHED_URL, block_size=2**20) as remote, h5py.File(remote, "r") as f:
        keys = list(f.keys())
        print(f"CaBuAr : {len(keys)} tuiles 512 × 512 contenant des zones brûlées")
        candidates = keys[:: max(1, len(keys) // n_candidates)][:n_candidates]
        burned = {}
        for key in tqdm(candidates, desc="Masques"):
            mask = f[key]["mask"][...]
            burned[key] = float((mask > 0).mean())
        chosen = sorted(burned, key=lambda k: -burned[k])[:n_samples]

        meta = {}
        for key in tqdm(chosen, desc="Images avant / après"):
            group = f[key]
            save_geotiff(group["post_fire"][...], out / f"{key}_post.tif", BANDS_L2A)
            if "pre_fire" in group:
                save_geotiff(group["pre_fire"][...], out / f"{key}_pre.tif", BANDS_L2A)
            save_geotiff(group["mask"][...], out / f"{key}_mask.tif", ["burned"])
            meta[key] = {"fold": int(group.attrs["fold"]), "burned": burned[key], "has_pre_fire": "pre_fire" in group}
    sources.save_json(meta, out / "samples.json")
    print("CaBuAr :", meta)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--flood-countries", type=int, default=4, help="Tuiles inondées (une par pays)")
    parser.add_argument("--normal", type=int, default=2, help="Tuiles Sen1Floods11 sans inondation")
    parser.add_argument("--fire-candidates", type=int, default=12, help="Tuiles CaBuAr examinées")
    parser.add_argument("--fire", type=int, default=3, help="Tuiles CaBuAr téléchargées")
    parser.add_argument("--skip-cabuar", action="store_true")
    args = parser.parse_args()

    sen1floods11(args.flood_countries, args.normal)
    if not args.skip_cabuar:
        cabuar(args.fire_candidates, args.fire)


if __name__ == "__main__":
    main()
