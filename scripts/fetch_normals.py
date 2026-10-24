"""Constitue les images « normales » à partir du catalogue configs/normal_sites.yaml.

Pour chaque site : recherche des passages Sentinel-2 L2A sur la période, choix d'un passage
selon la nébulosité voulue, lecture à distance de la tuile 512 × 512 à 10 m.
Même source et même traitement que scripts/harmonize_samples.py.

Usage : uv run python scripts/fetch_normals.py [--only nom_du_site]
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml
from tqdm import tqdm

from onelook.data import l2a, sources

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "configs" / "normal_sites.yaml"
OUT = ROOT / "data" / "harmonized" / "normal"

MAX_TRIES = 6           # passages essayés par site
CLEAR_MAX_CLOUD = 0.10  # part de nuages tolérée dans la tuile pour un site « clear »
CLOUDY_MIN_CLOUD = 0.50  # part de nuages minimale pour un site « cloudy »


def as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def fetch_site(site: dict) -> dict:
    grid = l2a.Grid.centered(site["lon"], site["lat"])
    start, end = as_date(site["start"]), as_date(site["end"])
    cloudy = site["clouds"] == "cloudy"
    groups = l2a.search_period(grid, start, end, min_cloud=50 if cloudy else 0, max_cloud=100 if cloudy else 40)
    if cloudy:
        groups = groups[::-1]  # les plus nuageux d'abord

    for items in groups[:MAX_TRIES]:
        image, scl, used = l2a.read_tile(items, grid)
        frac = l2a.scl_fractions(scl)
        if frac["no_data"] > 0.01:
            continue
        if (not cloudy and frac["cloud"] <= CLEAR_MAX_CLOUD) or (cloudy and frac["cloud"] >= CLOUDY_MIN_CLOUD):
            l2a.write_tile(OUT / f"{site['name']}_L2A.tif", image, grid, scl=scl)
            return {**{k: site[k] for k in ("category", "group", "lat", "lon")},
                    "date": items[0].datetime.date().isoformat(), "scenes": used, **frac}
    return {"category": site["category"], "group": site["group"], "error": "aucun passage satisfaisant"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="Ne traiter que ce site")
    args = parser.parse_args()

    catalog = yaml.safe_load(CATALOG.read_text())
    sites = [{**catalog["defaults"], **s} for s in catalog["sites"]]
    if args.only:
        sites = [s for s in sites if s["name"] == args.only]

    report_path = OUT / "report.json"
    report = sources.load_json(report_path) if report_path.exists() else {}
    for site in tqdm(sites, desc="Images normales"):
        if site["name"] in report and "error" not in report[site["name"]] and not args.only:
            continue
        try:
            report[site["name"]] = fetch_site(site)
        except Exception as exc:  # un site en échec ne bloque pas les autres
            report[site["name"]] = {"category": site["category"], "group": site["group"], "error": str(exc)[:200]}
        sources.save_json(report, report_path)

    failed = {k: v["error"] for k, v in report.items() if "error" in v}
    print(f"{len(report) - len(failed)} tuiles normales, {len(failed)} échecs", failed or "")


if __name__ == "__main__":
    main()
