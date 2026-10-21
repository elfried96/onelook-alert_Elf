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

À venir.

## Site de documentation en local

```bash
uv run mkdocs serve
```

Le site est alors visible sur `http://127.0.0.1:8000`.
