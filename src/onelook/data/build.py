"""Constitution du jeu de données harmonisé : une tuile L2A de 512 × 512 pixels à 10 m par ligne d'index.

Trois sources, une seule chaîne de lecture (`onelook.data.l2a`) :

- inondations : les 446 tuiles annotées de Sen1Floods11, relues le jour de l'événement ;
- incendies : les 534 tuiles CaBuAr (10 × 10 km à 20 m), relues à 10 m et découpées en 4,
  plus une image avant le feu par tuile CaBuAr (exemple normal du même lieu) ;
- normales : sites du catalogue sur plusieurs années, et points tirés au hasard par région.

Chaque tuile produit un GeoTIFF 12 bandes, sa carte SCL et, si elle existe, une carte de vérité
terrain (`*_mask.tif`). L'index ne stocke que des parts (inondé, brûlé, nuages…) : les étiquettes
NORMAL / ALERTE se calculent ensuite avec un seuil, sans tout reconstruire.
"""

from __future__ import annotations

import json
import random
import threading
from datetime import date, datetime
from pathlib import Path

import h5py
import hdf5plugin  # noqa: F401  (décompression BZip2 des fichiers CaBuAr)
import numpy as np
import pandas as pd
import rasterio
from affine import Affine

from onelook.data import l2a, sources

# Carte de vérité terrain des inondations
FLOOD_NODATA, FLOOD_DRY, FLOOD_PERMANENT, FLOOD_WATER = 0, 1, 2, 3
MAX_NO_DATA = 0.05  # part maximale de pixels sans donnée dans une tuile gardée

_lock = threading.Lock()


# --- Utilitaires -----------------------------------------------------------------

def append_row(path: Path, row: dict) -> None:
    """Ajoute une ligne à un index JSON Lines (sûr entre fils d'exécution)."""
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def done_ids(path: Path) -> set[str]:
    """Identifiants déjà traités avec succès (les échecs seront retentés)."""
    if not path.exists():
        return set()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["id"] for r in rows if "error" not in r}


def write_mask(path: Path, mask: np.ndarray, grid: l2a.Grid) -> None:
    with rasterio.open(path, "w", driver="GTiff", width=grid.width, height=grid.height, count=1,
                       dtype="uint8", crs=grid.crs, transform=grid.transform, compress="deflate") as dst:
        dst.write(mask.astype(np.uint8), 1)


def center_lonlat(grid: l2a.Grid) -> tuple[float, float]:
    west, south, east, north = grid.bounds_wgs84()
    return round((west + east) / 2, 5), round((south + north) / 2, 5)


def base_row(tile_id: str, source: str, category: str, group: str, grid: l2a.Grid, day: date,
             used: list[str], scl: np.ndarray, root: Path, image_path: Path) -> dict:
    lon, lat = center_lonlat(grid)
    return {
        "id": tile_id, "source": source, "category": category, "group": group,
        "date": day.isoformat(), "lon": lon, "lat": lat, "scenes": used,
        "image": str(image_path.relative_to(root)),
        **{f"scl_{k}": round(v, 4) for k, v in l2a.scl_fractions(scl).items()},
    }


# --- Inondations : Sen1Floods11 ------------------------------------------------

EVENT_NAMES = {"Mekong": "Cambodia"}  # préfixe des tuiles → nom de l'événement dans les métadonnées


def sen1floods11_dates() -> dict[str, date]:
    import requests

    url = "https://storage.googleapis.com/sen1floods11/v1.1/Sen1Floods11_Metadata.geojson"
    features = requests.get(url, timeout=60).json()["features"]
    return {f["properties"]["location"]: datetime.strptime(f["properties"]["s2_date"], "%Y/%m/%d").date()
            for f in features}


def flood_tile(tile: str, day: date, raw: Path, root: Path) -> dict:
    label_path = sources.download(sources.sen1floods11_url(tile, "LabelHand"), raw / "LabelHand" / f"{tile}_LabelHand.tif")
    jrc_path = sources.download(sources.sen1floods11_url(tile, "JRCWaterHand"), raw / "JRCWaterHand" / f"{tile}_JRCWaterHand.tif")
    grid = l2a.Grid.from_file(label_path)
    image, scl, used = l2a.read_tile(l2a.search(grid, day), grid)
    if l2a.scl_fractions(scl)["no_data"] > MAX_NO_DATA:
        return {"id": tile, "error": "tuile L2A incomplète"}

    label = sources.read_band_stack(label_path)[0]
    permanent = sources.read_band_stack(jrc_path)[0]
    mask = np.full(label.shape, FLOOD_DRY, dtype=np.uint8)
    mask[label == sources.LABEL_NODATA] = FLOOD_NODATA
    mask[(label == sources.LABEL_WATER) & (permanent > 0)] = FLOOD_PERMANENT
    mask[(label == sources.LABEL_WATER) & (permanent == 0)] = FLOOD_WATER

    out = root / "floods" / f"{tile}.tif"
    l2a.write_tile(out, image, grid, scl=scl)
    write_mask(out.with_name(f"{tile}_mask.tif"), mask, grid)
    stats = sources.flood_stats(label, permanent)
    return {
        **base_row(tile, "sen1floods11", "inondation", tile.split("_")[0], grid, day, used, scl, root, out),
        "mask": str(out.with_name(f"{tile}_mask.tif").relative_to(root)),
        "frac_valid": round(stats["valid"], 4), "frac_flood": round(stats["flood"], 4),
        "frac_permanent": round(stats["permanent"], 4), "frac_burned": 0.0,
    }


# --- Incendies : CaBuAr --------------------------------------------------------

COARSE = 16  # 20 m → 320 m pour retrouver une tuile dans sa scène


class CabuarScene:
    """Une scène CaBuAr : ses 121 positions de tuiles et sa bande B08 en basse résolution (lue une fois)."""

    def __init__(self, candidates: pd.DataFrame):
        self.candidates = candidates
        self.lefts = candidates["x"].map(lambda v: float(v[0]) - 10)
        self.tops = candidates["y"].map(lambda v: float(v[0]) + 10)
        self.n = 512 // COARSE
        res = 20 * COARSE
        width = int(round((self.lefts.max() - self.lefts.min()) / res)) + self.n
        height = int(round((self.tops.max() - self.tops.min()) / res)) + self.n
        self.res = res
        self.grid = l2a.Grid(f"EPSG:{int(candidates['crs'].iloc[0])}",
                             Affine(res, 0, self.lefts.min(), 0, -res, self.tops.max()), width, height)
        self.day = datetime.fromisoformat(candidates["timestamp"].iloc[0]).date()
        scene, _, _ = l2a.read_tile(l2a.search(self.grid, self.day), self.grid, bands=["B08"])
        self.b08 = scene[0].astype(np.float32)

    def locate(self, post_b08: np.ndarray) -> tuple[pd.Series | None, float]:
        """Position candidate la plus corrélée avec la bande B08 (512 × 512, 20 m) d'une tuile CaBuAr."""
        n = self.n
        ref = post_b08.astype(np.float32).reshape(n, COARSE, n, COARSE).mean(axis=(1, 3))
        best, best_r = None, -1.0
        for (_, row), left, top in zip(self.candidates.iterrows(), self.lefts, self.tops):
            c = int(round((left - self.lefts.min()) / self.res))
            r = int(round((self.tops.max() - top) / self.res))
            window = self.b08[r:r + n, c:c + n]
            ok = (window > 0) & (ref > 0)
            if window.shape != ref.shape or ok.sum() < n * n // 4:
                continue
            score = float(np.corrcoef(window[ok], ref[ok])[0, 1])
            if score > best_r:
                best, best_r = row, score
        return best, best_r


def cabuar_grid(row: pd.Series) -> l2a.Grid:
    """Grille à 10 m (1024 × 1024) couvrant exactement une tuile CaBuAr de 512 pixels de 20 m."""
    return l2a.Grid(f"EPSG:{int(row['crs'])}",
                    Affine(10, 0, float(row["x"][0]) - 10, 0, -10, float(row["y"][0]) + 10), 1024, 1024)


QUADRANTS = [(0, 0), (0, 512), (512, 0), (512, 512)]


def fire_patch(key: str, h5: h5py.File, scene: CabuarScene, meta: pd.DataFrame, root: Path) -> list[dict]:
    group = h5[key]
    fold = int(group.attrs["fold"])
    row, score = scene.locate(group["post_fire"][..., 7])
    if row is None or score < 0.8:
        return [{"id": key, "error": f"position introuvable (corrélation {score:.2f})"}]

    grid = cabuar_grid(row)
    day = datetime.fromisoformat(row["timestamp"]).date()
    image, scl, used = l2a.read_tile(l2a.search(grid, day), grid)
    mask10 = np.kron(group["mask"][..., 0] > 0, np.ones((2, 2), dtype=bool))

    rows, best_q, best_burn = [], None, -1.0
    for qi, (r, c) in enumerate(QUADRANTS):
        tile_id = f"{key}_q{qi}"
        sub = l2a.Grid(grid.crs, grid.transform * Affine.translation(c, r), 512, 512)
        q_scl = scl[r:r + 512, c:c + 512]
        if l2a.scl_fractions(q_scl)["no_data"] > MAX_NO_DATA:
            rows.append({"id": tile_id, "error": "tuile L2A incomplète"})
            continue
        out = root / "fires" / f"{tile_id}.tif"
        l2a.write_tile(out, image[:, r:r + 512, c:c + 512], sub, scl=q_scl)
        q_mask = mask10[r:r + 512, c:c + 512]
        write_mask(out.with_name(f"{tile_id}_mask.tif"), q_mask, sub)
        burned = float(q_mask.mean())
        rows.append({
            **base_row(tile_id, "cabuar", "incendie", f"cabuar_fold{fold}", sub, day, used, q_scl, root, out),
            "mask": str(out.with_name(f"{tile_id}_mask.tif").relative_to(root)),
            "frac_valid": 1.0, "frac_flood": 0.0, "frac_permanent": 0.0, "frac_burned": round(burned, 4),
            "cabuar_key": key, "cabuar_match": round(score, 4),
        })
        if burned > best_burn:
            best_q, best_burn = (qi, r, c, sub), burned

    # Image avant le feu, au même endroit que le quart le plus brûlé : un exemple normal difficile
    pre = meta[(meta["uuid"] == row["uuid"]) & (meta["patch"] == row["patch"]) & ~meta["post"]]
    if best_q is not None and not pre.empty:
        qi, r, c, sub = best_q
        pre_day = datetime.fromisoformat(pre["timestamp"].iloc[0]).date()
        pre_image, pre_scl, pre_used = l2a.read_tile(l2a.search(sub, pre_day), sub)
        if l2a.scl_fractions(pre_scl)["no_data"] <= MAX_NO_DATA:
            tile_id = f"{key}_q{qi}_avant"
            out = root / "normals" / f"{tile_id}.tif"
            l2a.write_tile(out, pre_image, sub, scl=pre_scl)
            rows.append({
                **base_row(tile_id, "cabuar_avant_feu", "californie_avant_feu", f"cabuar_fold{fold}",
                           sub, pre_day, pre_used, pre_scl, root, out),
                "frac_valid": 1.0, "frac_flood": 0.0, "frac_permanent": 0.0, "frac_burned": 0.0,
                "cabuar_key": key,
            })
    return rows


# --- Images normales -----------------------------------------------------------

CLEAR_MAX_CLOUD = 0.10
CLOUDY_MIN_CLOUD = 0.50
MAX_TRIES = 6


def normal_tile(tile_id: str, lon: float, lat: float, start: date, end: date, cloudy: bool,
                category: str, group: str, root: Path, source: str) -> dict:
    grid = l2a.Grid.centered(lon, lat)
    groups = l2a.search_period(grid, start, end, min_cloud=50 if cloudy else 0, max_cloud=100 if cloudy else 40)
    if cloudy:
        groups = groups[::-1]
    for items in groups[:MAX_TRIES]:
        image, scl, used = l2a.read_tile(items, grid)
        frac = l2a.scl_fractions(scl)
        if frac["no_data"] > MAX_NO_DATA:
            continue
        if (cloudy and frac["cloud"] >= CLOUDY_MIN_CLOUD) or (not cloudy and frac["cloud"] <= CLEAR_MAX_CLOUD):
            out = root / "normals" / f"{tile_id}.tif"
            l2a.write_tile(out, image, grid, scl=scl)
            return {
                **base_row(tile_id, source, category, group, grid, items[0].datetime.date(), used, scl, root, out),
                "frac_valid": 1.0, "frac_flood": 0.0, "frac_permanent": 0.0, "frac_burned": 0.0,
            }
    return {"id": tile_id, "error": "aucun passage satisfaisant"}


def catalog_jobs(catalog: dict) -> list[dict]:
    """Une tâche par site et par année : même fenêtre saisonnière, années différentes."""
    defaults = catalog["defaults"]
    jobs = []
    for site in catalog["sites"]:
        s = {**defaults, **site}
        start, end = date.fromisoformat(str(s["start"])), date.fromisoformat(str(s["end"]))
        for year in s["years"]:
            jobs.append({
                "id": f"{s['name']}_{year}", "lon": s["lon"], "lat": s["lat"],
                "start": start.replace(year=year), "end": end.replace(year=year + (end.year - start.year)),
                "cloudy": s["clouds"] == "cloudy", "category": s["category"], "group": s["group"],
                "source": "catalogue",
            })
    return jobs


def random_jobs(config: dict) -> list[dict]:
    """Points tirés au hasard dans des boîtes régionales, chacun à une date au hasard (graine fixe)."""
    rng = random.Random(config["seed"])
    jobs = []
    for box in config["boxes"]:
        years = box.get("years", config["years"])
        for i in range(box["n"]):
            lon = round(rng.uniform(box["west"], box["east"]), 4)
            lat = round(rng.uniform(box["south"], box["north"]), 4)
            year, month = rng.choice(years), rng.randint(1, 12)
            start = date(year, month, 1)
            end = date(year + (month == 12), month % 12 + 1, 1)
            jobs.append({
                "id": f"aleatoire_{box['name']}_{i:03d}", "lon": lon, "lat": lat, "start": start, "end": end,
                "cloudy": False, "category": "aleatoire", "group": box["group"], "source": "aleatoire",
            })
    return jobs
