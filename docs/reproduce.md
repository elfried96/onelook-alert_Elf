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

Chaque étape (`floods`, `fires`, `normals`, `water`, `fire_history`, `index`) peut se lancer seule et reprend là où elle s'est arrêtée. Durée : environ une heure, surtout des lectures réseau. Résultat dans `data/dataset/` :

- `floods/`, `fires/`, `normals/` : une tuile GeoTIFF 12 bandes par image, sa carte SCL et, si elle existe, sa vérité terrain (`*_mask.tif`) ;
- `fire_history.jsonl` : la part de chaque tuile de Californie couverte par un feu récent (périmètres NIFC, téléchargés une fois dans `data/raw/fire_history/`) ;
- `*_water.tif` : la carte d'eau permanente JRC de chaque tuile (occurrence de l'eau 1984-2020, 255 en pleine mer) ;
- `index.csv` : une ligne par tuile, avec ses parts d'anomalie et sa partie (train, val, test) ;
- `index_labels.csv` et `report.md` : décisions attendues selon `configs/labels.yaml`, et contrôle de fuite spatiale.

### Figures de la documentation

```bash
uv run python scripts/make_figures.py
```

Le script régénère toutes les images de la documentation (`docs/assets/figures/`) à partir du jeu local. Il télécharge une fois les contours des terres de Natural Earth pour les cartes.

### Paquet d'entraînement pour Colab

```bash
uv run python scripts/pack_dataset.py
uv run python scripts/check_pack.py
```

Envoi (une fois, après `uv run hf auth login`) : `uv run python scripts/upload_pack.py`, par lots, avec reprise après coupure.

Le paquet (`data/pack/`, environ 7,5 Go) contient une tuile par fichier : un GeoTIFF de 9 bandes (les 6 bandes retenues, la carte SCL, la vérité terrain unifiée et l'eau permanente), et son index. Il est envoyé une fois dans un dépôt de données **privé** sur Hugging Face, d'où Colab le télécharge en quelques minutes (`notebooks/02_colab_donnees.ipynb`).

## Entraînement et évaluation

Les entraînements tournent sur un GPU distant (Google Colab ou Kaggle), pas en local. Les notebooks d'entraînement, dans `notebooks/`, clonent ce dépôt, installent l'environnement avec `uv sync` et récupèrent les données sur place.

| Étape | Où | Commande ou notebook |
|---|---|---|
| Préparer la session, télécharger et vérifier les données | Colab | `notebooks/02_colab_donnees.ipynb` |
| Baselines, entraînement, évaluation, rangement des résultats | Colab (GPU T4) | `notebooks/03_colab_entrainement.ipynb` |
| Récupérer les résultats | Local | `uv run hf download Elfried9684/onelook-alert-runs --include "runs/*" --local-dir .` |
| Réévaluer un modèle exporté (mesures, taille, temps sur un cœur) | Local ou Colab | `uv run python scripts/evaluate.py runs/<nom> --split test` |
| Recalibrer le seuil « inconnu » sans réentraîner (après `evaluate.py --split val`), puis réévaluer le test | Local | `uv run python scripts/calibrate.py runs/<nom> [--figure docs/assets/figures/seuil.png]` |
| Quantifier un modèle exporté (`--mode int8`, `a16w8` ou `poids`), puis l'évaluer avec `--model model_<mode>.onnx` | Local | `uv run python scripts/quantize.py runs/<nom> --mode poids` |
| Lot « inconnu » : télécharger les tuiles, puis évaluer un modèle et tracer les planches | Local | `uv run python scripts/unknown_set.py download`, puis `evaluate runs/<nom>` et `sheet runs/<nom>` |
| Démo « Centre de veille » : préparer une fois, puis lancer | Local | `uv run --group demo python scripts/demo.py prepare`, puis `uv run --group demo python scripts/demo.py` |
| Importance des bandes (brouillage d'une bande, sans réentraîner) | Local | `uv run python scripts/band_importance.py runs/<nom> --split test --figure docs/assets/figures/importance_bandes.png` |

Les scripts appelés par les notebooks sont dans `scripts/` : `baselines.py`, `train.py` (`--smoke` pour un essai de deux pas sur 24 tuiles) et `evaluate.py` ; les planches d'erreurs de la page Limites et échecs viennent de `uv run python scripts/failure_figures.py runs/<nom>`. Les résultats (`runs/`) vont dans un dépôt privé Hugging Face, jamais dans Git.

Le matériel utilisé pour chaque entraînement est indiqué dans la page Résultats.

## Tests

```bash
uv run pytest
```

## Site de documentation en local

```bash
uv run mkdocs serve
```

Le site est alors visible sur `http://127.0.0.1:8000`.
