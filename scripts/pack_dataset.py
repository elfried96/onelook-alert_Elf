"""Construit le paquet d'entraînement compact (data/pack/) à envoyer sur Hugging Face pour Colab.

Usage : uv run python scripts/pack_dataset.py [--workers 6] [--bandes 12]
Prérequis : le jeu complet (scripts/build_dataset.py) et son rapport (scripts/dataset_report.py).
Une tuile = un GeoTIFF de 6 bandes d'image + 3 couches (voir onelook.data.pack) : environ 7 Go pour
3 312 tuiles dans data/pack/. Avec --bandes 12 (essai « 12 bandes ») : les 12 bandes L2A, dans data/pack12/.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from onelook.data.pack import LAYERS, pack_tile
from onelook.data.sentinel2 import BANDS_L2A, SELECTED_BANDS

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "dataset"
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
- `tiles/<source>/<id>.tif` : GeoTIFF de {count} bandes uint16, compression zstd :

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
    parser.add_argument("--bandes", type=int, choices=[6, 12], default=6, help="Bandes d'image par tuile")
    args = parser.parse_args()
    bands = SELECTED_BANDS if args.bandes == 6 else BANDS_L2A
    pack = ROOT / "data" / ("pack" if args.bandes == 6 else "pack12")

    index = pd.read_csv(DATASET / "index_labels.csv")
    index["path"] = [f"tiles/{Path(image).parent.name}/{tile_id}.tif" for image, tile_id in zip(index.image, index.id)]
    todo = [row for row in index.to_dict("records") if not (pack / row["path"]).exists()]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(tqdm(pool.map(lambda row: pack_tile(DATASET, row, pack / row["path"], bands), todo), total=len(todo),
                  desc="Paquet"))

    index[COLUMNS].to_csv(pack / "index.csv", index=False)
    table_bands = "\n".join(f"| {i} | {BAND_NOTES.get(b, b + ' (réflectance × 10 000)')} |"
                            for i, b in enumerate([*bands, *LAYERS], 1))
    table = pd.crosstab(index.label, index.split)
    labels = "\n".join(["| décision | " + " | ".join(table.columns) + " |", "|---" * (len(table.columns) + 1) + "|",
                        *(f"| {label} | " + " | ".join(str(v) for v in row) + " |" for label, row in table.iterrows())])
    card = CARD.format(n=len(index), count=len(bands) + len(LAYERS), bands=table_bands, labels=labels)
    (pack / "README.md").write_text(card)
    size = sum(p.stat().st_size for p in pack.rglob("*.tif"))
    print(f"{len(index)} tuiles, {size / 1e9:.1f} Go -> {pack}")


if __name__ == "__main__":
    main()
