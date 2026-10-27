"""Constitue le jeu de données complet, harmonisé en Sentinel-2 L2A, et son découpage.

Étapes (chacune reprend là où elle s'est arrêtée) :

    uv run python scripts/build_dataset.py floods    # 446 tuiles Sen1Floods11
    uv run python scripts/build_dataset.py fires     # 534 tuiles CaBuAr → ~2 100 tuiles + images avant feu
    uv run python scripts/build_dataset.py normals   # catalogue sur plusieurs années + points au hasard
    uv run python scripts/build_dataset.py index     # index.csv avec le découpage train / val / test
    uv run python scripts/build_dataset.py all       # tout, dans l'ordre

Options : --limit N pour un essai sur quelques tuiles, --workers N pour le nombre de lectures parallèles.
Aucun entraînement : ce script ne fait que télécharger, harmoniser et indexer.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import h5py
import pandas as pd
import yaml
from tqdm import tqdm

from onelook.data import build, sources
from onelook.data.labels import LabelRules
from onelook.data.splits import assign_zones, haversine_km, spatial_zones

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DATASET = ROOT / "data" / "dataset"
CONFIGS = ROOT / "configs"
CABUAR_H5 = RAW / "cabuar" / "512x512.hdf5"
CABUAR_METADATA = "https://huggingface.co/datasets/DarthReca/california_burned_areas/resolve/main/metadata.parquet"


def run_jobs(jobs: list, worker, log: Path, workers: int, desc: str) -> None:
    """Exécute les tâches en parallèle (lectures réseau), écrit chaque résultat dans le journal."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, job): job for job in jobs}
        for future in tqdm(as_completed(futures), total=len(futures), desc=desc):
            try:
                results = future.result()
            except Exception as exc:  # une tuile en échec ne bloque pas les autres
                job = futures[future]
                results = {"id": job if isinstance(job, str) else job["id"], "error": str(exc)[:300]}
            for row in results if isinstance(results, list) else [results]:
                build.append_row(log, row)


def stage_floods(limit: int | None, workers: int) -> None:
    log = DATASET / "floods.jsonl"
    done = build.done_ids(log)
    tiles = [t for t in sources.list_sen1floods11_tiles() if t not in done][:limit]
    dates = build.sen1floods11_dates()

    def worker(tile: str) -> dict:
        country = tile.split("_")[0]
        return build.flood_tile(tile, dates[build.EVENT_NAMES.get(country, country)], RAW / "sen1floods11", DATASET)

    run_jobs(tiles, worker, log, workers, "Inondations")


def stage_fires(limit: int | None, workers: int) -> None:
    log = DATASET / "fires.jsonl"
    done = {i.rsplit("_q", 1)[0] for i in build.done_ids(log)}
    meta = pd.read_parquet(sources.download(CABUAR_METADATA, RAW / "cabuar" / "metadata.parquet"))
    with h5py.File(CABUAR_H5, "r") as h5:
        keys = [k for k in h5.keys() if k not in done][:limit]
    by_uuid: dict[str, list[str]] = {}
    for key in keys:
        by_uuid.setdefault(key.rsplit("_", 1)[0], []).append(key)

    def worker(uuid: str) -> list[dict]:
        # Une scène à la fois : sa bande B08 basse résolution sert à placer toutes ses tuiles
        scene = build.CabuarScene(meta[(meta["uuid"] == uuid) & meta["post"]])
        rows = []
        with h5py.File(CABUAR_H5, "r") as h5:
            for key in by_uuid[uuid]:
                try:
                    rows += build.fire_patch(key, h5, scene, meta, DATASET)
                except Exception as exc:
                    rows.append({"id": key, "error": str(exc)[:300]})
        return rows

    run_jobs(list(by_uuid), worker, log, workers, f"Incendies ({len(keys)} tuiles CaBuAr)")


def stage_normals(limit: int | None, workers: int) -> None:
    log = DATASET / "normals.jsonl"
    done = build.done_ids(log)
    jobs = build.catalog_jobs(yaml.safe_load((CONFIGS / "normal_sites.yaml").read_text()))
    jobs += build.random_jobs(yaml.safe_load((CONFIGS / "normal_random.yaml").read_text()))
    jobs = [j for j in jobs if j["id"] not in done][:limit]

    def worker(job: dict) -> dict:
        return build.normal_tile(job["id"], job["lon"], job["lat"], job["start"], job["end"], job["cloudy"],
                                 job["category"], job["group"], DATASET, job["source"])

    run_jobs(jobs, worker, log, workers, "Images normales")


def cabuar_zone_splits(df: pd.DataFrame, config: dict) -> dict[str, str]:
    """Regroupe les tuiles CaBuAr (et leurs images avant feu) en zones spatiales, renomme leur groupe en
    « cabuar_zoneN » et renvoie la partie de chaque zone. Les plis CaBuAr ne suffisent pas : la même
    zone revient à plusieurs dates dans des plis différents. Une normale du catalogue ou tirée au hasard
    à moins de distance_km d'une tuile CaBuAr rejoint sa zone."""
    cabuar = df["source"].str.startswith("cabuar")
    lat, lon = df.loc[cabuar, "lat"].to_numpy(), df.loc[cabuar, "lon"].to_numpy()
    near = [not c and bool((haversine_km(la, lo, lat, lon) < config["distance_km"]).any())
            for c, la, lo in zip(cabuar, df["lat"], df["lon"])]
    cabuar = cabuar | pd.Series(near, index=df.index)
    zones = spatial_zones(df.loc[cabuar, "lat"], df.loc[cabuar, "lon"], config["distance_km"])
    fire_alert = LabelRules.from_yaml(CONFIGS / "labels.yaml").fire_alert
    burned = df.loc[cabuar, "frac_burned"].fillna(0).to_numpy() >= fire_alert
    df.loc[cabuar, "group"] = [f"cabuar_zone{z}" for z in zones]
    return {f"cabuar_zone{z}": split for z, split in assign_zones(zones, burned, config["ratios"]).items()}


def stage_index() -> None:
    rows = []
    for name in ("floods", "fires", "normals"):
        path = DATASET / f"{name}.jsonl"
        if path.exists():
            rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    df = pd.DataFrame(rows)
    if "error" not in df:
        df["error"] = None
    errors = df[df["error"].notna()]
    df = df[df["error"].isna()].drop(columns="error").drop_duplicates("id", keep="last")
    errors = errors[~errors["id"].isin(df["id"])].drop_duplicates("id", keep="last")

    splits = yaml.safe_load((CONFIGS / "splits.yaml").read_text())
    group_split = {g: split for split, groups in splits["groups"].items() for g in groups}
    group_split.update(cabuar_zone_splits(df, splits["cabuar_zones"]))
    df["split"] = df["group"].map(group_split).fillna(splits["default"])
    df["scenes"] = df["scenes"].map(lambda s: ";".join(s) if isinstance(s, list) else s)
    df.sort_values(["split", "source", "id"]).to_csv(DATASET / "index.csv", index=False)

    unknown_groups = sorted(set(df["group"]) - set(group_split))
    print(f"\n{len(df)} tuiles indexées, {len(errors)} échecs -> {DATASET / 'index.csv'}")
    if unknown_groups:
        print(f"Groupes sans découpage explicite (mis en « {splits['default']} ») :", unknown_groups)
    print(pd.crosstab(df["source"], df["split"], margins=True))
    if len(errors):
        print("\nÉchecs par cause :")
        print(errors["error"].str.slice(0, 60).value_counts().head(10))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["floods", "fires", "normals", "index", "all"])
    parser.add_argument("--limit", type=int, help="Nombre maximal de tâches (essai)")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    if args.stage in ("floods", "all"):
        stage_floods(args.limit, args.workers)
    if args.stage in ("fires", "all"):
        stage_fires(args.limit, args.workers)
    if args.stage in ("normals", "all"):
        stage_normals(args.limit, args.workers)
    if args.stage in ("index", "all"):
        stage_index()


if __name__ == "__main__":
    main()
