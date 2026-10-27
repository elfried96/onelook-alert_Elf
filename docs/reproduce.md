# Reproduire

## Installation

Le projet utilise [uv](https://docs.astral.sh/uv/) : il installe la bonne version de Python et les versions exactes des dépendances, figées dans `uv.lock`.

```bash
git clone https://github.com/elfried96/onelook-alert_Elf.git
cd onelook-alert_Elf
uv sync
```

## Données

Échantillon d'exploration (environ 40 Mo) :

```bash
uv run python scripts/download_samples.py
```

Le script télécharge les masques des 446 tuiles Sen1Floods11, quelques images Sentinel-2, et lit à distance quelques tuiles CaBuAr sans télécharger le fichier complet (6 Go). Les données sont écrites dans `data/raw/`, qui n'est pas versionné.

L'exploration se trouve dans `notebooks/01_exploration.ipynb`.

### Jeu de données complet

Toutes les tuiles, de toutes les classes, sont relues en Sentinel-2 L2A depuis la même source (Microsoft Planetary Computer). Le fichier CaBuAr pré-découpé (5,9 Go) est d'abord téléchargé dans `data/raw/cabuar/512x512.hdf5` :

```bash
curl -L -o data/raw/cabuar/512x512.hdf5 https://huggingface.co/datasets/DarthReca/california_burned_areas/resolve/main/raw/patched/512x512.hdf5
uv run python scripts/build_dataset.py all
uv run python scripts/dataset_report.py
```

Chaque étape (`floods`, `fires`, `normals`, `index`) peut se lancer seule et reprend là où elle s'est arrêtée. Durée : environ une heure, surtout des lectures réseau. Résultat dans `data/dataset/` :

- `floods/`, `fires/`, `normals/` : une tuile GeoTIFF 12 bandes par image, sa carte SCL et, si elle existe, sa vérité terrain (`*_mask.tif`) ;
- `index.csv` : une ligne par tuile, avec ses parts d'anomalie et sa partie (train, val, test) ;
- `index_labels.csv` et `report.md` : décisions attendues selon `configs/labels.yaml`, et contrôle de fuite spatiale.

## Entraînement et évaluation

Les entraînements tournent sur un GPU distant (Google Colab ou Kaggle), pas en local. Les notebooks d'entraînement, dans `notebooks/`, clonent ce dépôt, installent l'environnement avec `uv sync` et récupèrent les données sur place.

Le matériel utilisé pour chaque entraînement est indiqué dans la page Résultats.

À venir.

## Tests

```bash
uv run pytest
```

## Site de documentation en local

```bash
uv run mkdocs serve
```

Le site est alors visible sur `http://127.0.0.1:8000`.
