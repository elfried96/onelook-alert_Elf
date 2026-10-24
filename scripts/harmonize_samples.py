"""Retélécharge les tuiles échantillons en Sentinel-2 L2A, depuis une source unique.

- Sen1Floods11 (L1C à l'origine) : même grille que les masques, même jour d'acquisition.
- CaBuAr (L2A à 20 m à l'origine) : même zone et même date, rééchantillonnée à 10 m ;
  chaque tuile CaBuAr de 10 × 10 km donne 4 tuiles de 512 × 512 pixels.

Résultat dans data/harmonized/ : toutes les tuiles ont le même niveau (L2A), les mêmes 12 bandes,
la même résolution (10 m) et la même convention de valeurs (réflectance × 10 000).

Usage : uv run python scripts/harmonize_samples.py   (après download_samples.py)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from affine import Affine
from tqdm import tqdm

from onelook.data import l2a, sources

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "harmonized"

SEN1FLOODS11_METADATA = "https://storage.googleapis.com/sen1floods11/v1.1/Sen1Floods11_Metadata.geojson"
CABUAR_METADATA = "https://huggingface.co/datasets/DarthReca/california_burned_areas/resolve/main/metadata.parquet"
# Préfixe des tuiles Sen1Floods11 → nom de l'événement dans les métadonnées
EVENT_NAMES = {"Mekong": "Cambodia"}


def sen1floods11_dates() -> dict[str, date]:
    features = requests.get(SEN1FLOODS11_METADATA, timeout=60).json()["features"]
    return {
        f["properties"]["location"]: datetime.strptime(f["properties"]["s2_date"], "%Y/%m/%d").date()
        for f in features
    }


def harmonize_sen1floods11() -> dict:
    src = RAW / "sen1floods11"
    selection = json.loads((src / "samples.json").read_text())
    dates = sen1floods11_dates()
    report = {}
    for tile in tqdm(selection["flood"] + selection["normal"], desc="Sen1Floods11 → L2A"):
        country = tile.split("_")[0]
        day = dates[EVENT_NAMES.get(country, country)]
        grid = l2a.Grid.from_file(src / "LabelHand" / f"{tile}_LabelHand.tif")
        image, scl, used = l2a.read_tile(l2a.search(grid, day), grid)
        l2a.write_tile(OUT / "sen1floods11" / f"{tile}_L2A.tif", image, grid, scl=scl)
        report[tile] = {"date": day.isoformat(), "scenes": used, **l2a.scl_fractions(scl)}
    return report


def cabuar_grid(row: pd.Series) -> l2a.Grid:
    """Grille à 10 m couvrant exactement une tuile CaBuAr (512 pixels de 20 m, coordonnées des centres)."""
    left = float(row["x"][0]) - 10
    top = float(row["y"][0]) + 10
    return l2a.Grid(f"EPSG:{int(row['crs'])}", Affine(10, 0, left, 0, -10, top), 1024, 1024)


COARSE = 16  # facteur de réduction pour retrouver une tuile dans sa scène (20 m → 320 m)


def locate_patch(cabuar_post: Path, candidates: pd.DataFrame) -> tuple[pd.Series, float]:
    """Retrouve la position d'une tuile CaBuAr dans sa scène.

    Le fichier pré-découpé renumérote ses tuiles : son numéro ne correspond pas à celui des
    métadonnées. On lit la bande B08 de toute la scène en basse résolution, en une seule fois,
    et on garde la position candidate la plus corrélée avec la tuile CaBuAr.
    """
    ref = sources.read_band_stack(cabuar_post)[7].astype(np.float32)
    n = 512 // COARSE
    ref = ref.reshape(n, COARSE, n, COARSE).mean(axis=(1, 3))

    lefts = candidates["x"].map(lambda v: float(v[0]) - 10)
    tops = candidates["y"].map(lambda v: float(v[0]) + 10)
    res = 20 * COARSE
    width = int(round((lefts.max() - lefts.min()) / res)) + n
    height = int(round((tops.max() - tops.min()) / res)) + n
    grid = l2a.Grid(f"EPSG:{int(candidates['crs'].iloc[0])}",
                    Affine(res, 0, lefts.min(), 0, -res, tops.max()), width, height)
    day = datetime.fromisoformat(candidates["timestamp"].iloc[0]).date()
    scene, _, _ = l2a.read_tile(l2a.search(grid, day), grid, bands=["B08"])
    scene = scene[0].astype(np.float32)

    best, best_r = None, -1.0
    for _, row in candidates.iterrows():
        c = int(round((float(row["x"][0]) - 10 - lefts.min()) / res))
        r = int(round((tops.max() - float(row["y"][0]) - 10) / res))
        window = scene[r:r + n, c:c + n]
        ok = (window > 0) & (ref > 0)
        if window.shape != ref.shape or ok.sum() < n * n // 4:
            continue
        score = float(np.corrcoef(window[ok], ref[ok])[0, 1])
        if score > best_r:
            best, best_r = row, score
    return best, best_r


def harmonize_cabuar() -> dict:
    src = RAW / "cabuar"
    meta_path = sources.download(CABUAR_METADATA, src / "metadata.parquet")
    meta = pd.read_parquet(meta_path)
    selection = json.loads((src / "samples.json").read_text())
    report = {}
    for key in tqdm(selection, desc="CaBuAr → L2A 10 m"):
        uuid, _ = key.rsplit("_", 1)
        candidates = meta[(meta["uuid"] == uuid) & meta["post"]]
        row, score = locate_patch(src / f"{key}_post.tif", candidates)
        if row is None or score < 0.8:
            report[key] = {"error": f"position introuvable (corrélation {score:.2f})"}
            continue
        day = datetime.fromisoformat(row["timestamp"]).date()
        grid = cabuar_grid(row)
        image, scl, used = l2a.read_tile(l2a.search(grid, day), grid)

        # Masque à 20 m → 10 m (chaque pixel devient 2 × 2), puis découpe en 4 tuiles de 512
        mask20 = sources.read_band_stack(src / f"{key}_mask.tif")[0]
        mask10 = np.kron(mask20, np.ones((2, 2), dtype=mask20.dtype))
        for qi, (r, c) in enumerate([(0, 0), (0, 512), (512, 0), (512, 512)]):
            sub = l2a.Grid(grid.crs, grid.transform * Affine.translation(c, r), 512, 512)
            name = f"{key}_q{qi}"
            l2a.write_tile(OUT / "cabuar" / f"{name}_L2A.tif", image[:, r:r + 512, c:c + 512], sub,
                           scl=scl[r:r + 512, c:c + 512])
            with rasterio.open(OUT / "cabuar" / f"{name}_mask.tif", "w", driver="GTiff", width=512, height=512,
                               count=1, dtype="uint8", crs=sub.crs, transform=sub.transform, compress="deflate") as dst:
                dst.write((mask10[r:r + 512, c:c + 512] > 0).astype(np.uint8), 1)
            report[name] = {
                "date": day.isoformat(), "scene_cabuar": row["name"], "scenes": used,
                "burned": float((mask10[r:r + 512, c:c + 512] > 0).mean()),
                **l2a.scl_fractions(scl[r:r + 512, c:c + 512]),
            }
        report[key] = {"patch_in_scene": int(row["patch"]), "match_score": score,
                       "check_vs_cabuar": alignment_check(src / f"{key}_post.tif", image)}
    return report


def alignment_check(cabuar_post: Path, image10: np.ndarray) -> float:
    """Corrélation entre la bande B08 de CaBuAr (20 m) et la nôtre ramenée à 20 m : proche de 1 si bien alignées."""
    ref = sources.read_band_stack(cabuar_post)[7].astype(np.float32)
    ours = image10[7].astype(np.float32).reshape(512, 2, 512, 2).mean(axis=(1, 3))
    ok = (ref > 0) & (ours > 0)
    return float(np.corrcoef(ref[ok], ours[ok])[0, 1]) if ok.sum() > 100 else float("nan")


def main() -> None:
    report = {"sen1floods11": harmonize_sen1floods11(), "cabuar": harmonize_cabuar()}
    sources.save_json(report, OUT / "report.json")
    print(json.dumps(report, indent=1)[:3000])


if __name__ == "__main__":
    main()
