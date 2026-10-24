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

Harmonisation en L2A (même source pour toutes les classes) et images normales :

```bash
uv run python scripts/harmonize_samples.py
uv run python scripts/fetch_normals.py
```

Les tuiles harmonisées sont écrites dans `data/harmonized/`, avec un rapport `report.json` par source.

Le jeu complet et sa préparation seront ajoutés dans `scripts/`.

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
