# Reproduire

## Installation

Le projet utilise [uv](https://docs.astral.sh/uv/) : il installe la bonne version de Python et les versions exactes des dépendances, figées dans `uv.lock`.

```bash
git clone https://github.com/elfried96/onelook-alert_Elf.git
cd onelook-alert_Elf
uv sync
```

## Données

Les scripts de téléchargement et de préparation seront ajoutés dans `scripts/`.

## Entraînement et évaluation

Les entraînements tournent sur un GPU distant (Google Colab ou Kaggle), pas en local. Les notebooks d'entraînement, dans `notebooks/`, clonent ce dépôt, installent l'environnement avec `uv sync` et récupèrent les données sur place.

Le matériel utilisé pour chaque entraînement est indiqué dans la page Résultats.

À venir.

## Site de documentation en local

```bash
uv run mkdocs serve
```

Le site est alors visible sur `http://127.0.0.1:8000`.
