# One Look

Modèle d'IA léger et embarquable qui analyse une image satellite en une seule passe et décide si elle mérite une alerte.

**Documentation complète : https://onelook-alert-elf.readthedocs.io/fr/latest/**

Projet individuel de la Piscine Intelligence Lab · Makers (16 octobre → 16 novembre 2026).

## Ce que fait le modèle

Pour chaque image, une décision :

| Décision | Signification |
|---|---|
| **NORMAL** | Rien à signaler (nuages, rivières, lacs et champs compris) |
| **ALERTE** | L'image contient une inondation |
| **INCONNU** | L'image sort de ce que le modèle connaît, à vérifier au sol |

## Installation

Le projet utilise [uv](https://docs.astral.sh/uv/) pour Python et ses dépendances.

```bash
git clone https://github.com/elfried96/onelook-alert_Elf.git
cd onelook-alert_Elf
uv sync
```

## Organisation du dépôt

```
configs/        réglages des entraînements
data/           images satellites (non versionnées)
docs/           site de documentation (MkDocs)
notebooks/      explorations
src/onelook/    code principal : données, modèles, entraînement, évaluation, inconnu, export
scripts/        commandes : téléchargement, entraînement, évaluation, export
demo/           interface de démonstration
checkpoints/    modèles entraînés (non versionnés)
tests/          tests automatiques
```

## Livrables

- [Carnet de données](https://onelook-alert-elf.readthedocs.io/fr/latest/data_card/) : sources, licences, découpage, biais
- [Résultats](https://onelook-alert-elf.readthedocs.io/fr/latest/results/) : tableau comparatif des approches
- [Limites et échecs](https://onelook-alert-elf.readthedocs.io/fr/latest/failure_cases/)
- Démonstration sur une image jamais vue : à venir

## Licence

Code sous licence MIT. Les données gardent la licence de leur source, voir le carnet de données.
