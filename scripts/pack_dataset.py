"""Construit le paquet d'entraînement compact (data/pack/) à envoyer sur Hugging Face pour Colab.

Usage : uv run python scripts/pack_dataset.py [--workers 6]
Prérequis : le jeu complet (scripts/build_dataset.py) et son rapport (scripts/dataset_report.py).
Une tuile = un GeoTIFF de 9 bandes (voir onelook.data.pack). Environ 7 Go pour 3 312 tuiles.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from onelook.data.pack import PACK_BANDS, pack_tile

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "dataset"
PACK = ROOT / "data" / "pack"
COLUMNS = ["id", "path", "split", "label", "source", "category", "group", "date", "lon", "lat",
           "frac_valid", "frac_flood", "frac_burned", "frac_permanent_jrc", "scl_water_outside_jrc", "scl_cloud", "frac_fire_1y"]

CARD = """---
license: other
pretty_name: One Look · Sentinel-2 L2A, inondations, incendies et normales
tags: [sentinel-2, remote-sensing, flood, burned-area, geotiff]
---

# One Look · paquet d'entraînement

Jeu de données du projet [One Look](https://github.com/elfried96/onelook-alert_Elf) : {n} tuiles Sentinel-2 L2A
de 512 × 512 pixels à 10 m, relues depuis Microsoft Planetary Computer. Documentation complète :
https://onelook-alert-elf.readthedocs.io/fr/latest/data_card/

## Contenu

- `index.csv` : une ligne par tuile (partie train / val / test, décision attendue, parts d'anomalie).
- `tiles/<source>/<id>.tif` : GeoTIFF de 9 bandes uint16, compression zstd :

| Bande | Contenu |
|---|---|
{bands}

## Décisions attendues

{labels}

## Sources et licences

- Inondations : Sen1Floods11 (licence à vérifier) ; zones brûlées : CaBuAr (CDLA-Permissive-2.0).
- Images : Sentinel-2 L2A, données Copernicus (accès libre), via Microsoft Planetary Computer.
- Eau permanente : JRC Global Surface Water 1984-2020 (Commission européenne).

Dépôt privé, pour l'entraînement du projet uniquement.
"""

BAND_NOTES = {"SCL": "classification de scène L2A", "truth": "vérité : 0 rien, 1 eau d'inondation, 2 brûlé, 255 non observé",
              "water": "occurrence de l'eau JRC (0-100 %, 255 pleine mer)"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    index = pd.read_csv(DATASET / "index_labels.csv")
    index["path"] = [f"tiles/{Path(image).parent.name}/{tile_id}.tif" for image, tile_id in zip(index.image, index.id)]
    todo = [row for row in index.to_dict("records") if not (PACK / row["path"]).exists()]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(tqdm(pool.map(lambda row: pack_tile(DATASET, row, PACK / row["path"]), todo), total=len(todo),
                  desc="Paquet"))

    index[COLUMNS].to_csv(PACK / "index.csv", index=False)
    bands = "\n".join(f"| {i} | {BAND_NOTES.get(b, b + ' (réflectance × 10 000)')} |" for i, b in enumerate(PACK_BANDS, 1))
    table = pd.crosstab(index.label, index.split)
    labels = "\n".join(["| décision | " + " | ".join(table.columns) + " |", "|---" * (len(table.columns) + 1) + "|",
                        *(f"| {label} | " + " | ".join(str(v) for v in row) + " |" for label, row in table.iterrows())])
    (PACK / "README.md").write_text(CARD.format(n=len(index), bands=bands, labels=labels))
    size = sum(p.stat().st_size for p in PACK.rglob("*.tif"))
    print(f"{len(index)} tuiles, {size / 1e9:.1f} Go -> {PACK}")


if __name__ == "__main__":
    main()
