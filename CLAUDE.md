# One Look

Projet de la Piscine Intelligence Lab · Makers (16 oct → 16 nov 2026, individuel). Mentor : Lilian Rage.
Modèle d'IA léger et embarquable : une image satellite en entrée, une passe, une décision NORMAL / ALERTE / INCONNU.
Anomalie visée : inondations (Sen1Floods11), à confirmer avec le mentor.

## Règles du projet

- Langue : français pour la documentation, les commentaires et les messages de commit.
- Découpage des données par événement / région, jamais au hasard entre tuiles (risque de fuite).
- Chaque source de données et chaque modèle pré-entraîné est documenté avec sa licence dans `docs/data_card.md`.
- Chaque approche testée est mesurée (précision, rappel, fausses alertes, taille Mo, temps ms) et ajoutée à `docs/results.md`.
- Ne jamais versionner les données (`data/`) ni les poids (`checkpoints/`, `*.pt`, `*.onnx`).
- Commits réguliers : l'activité GitHub est suivie par la plateforme de la piscine.

## Environnement

- Python géré uniquement avec **uv** : jamais `pip`, `python -m venv` ni `requirements.txt`.
- Dépendances dans `pyproject.toml` (groupes `dev` et `docs`), versions figées dans `uv.lock` (versionné).
- Python 3.12.
- **Aucun entraînement sur l'ordinateur local.** Les entraînements tournent sur GPU distant (Google Colab ou Kaggle) via des notebooks dans `notebooks/` qui clonent le dépôt et lancent `uv sync`. En local : code, tests sur petits échantillons, évaluation, export ONNX, démo.
- Commandes :
  - Installer : `uv sync` (docs seules : `uv sync --only-group docs`)
  - Ajouter une dépendance : `uv add <paquet>` (`uv add --group dev <paquet>` pour les outils)
  - Doc en local : `uv run mkdocs serve`
  - Tests : `uv run pytest`

## Design

- Design System « One Look » dans Claude Design : https://claude.ai/artifact/NEGDA9QFcZmk3qdhDHp5rv
- Le thème du site (`docs/stylesheets/onelook.css`) reprend ses jetons ; modifier les deux ensemble.
- Polices : Barlow Semi Condensed (titres), IBM Plex Sans (texte), IBM Plex Mono (données).
- Décisions toujours affichées avec leur libellé (badges `ol-badge--normal|alert|unknown`), jamais la couleur seule.

## Documentation

Site MkDocs Material, publié de deux façons à chaque push sur `main` :
- Read the Docs (`.readthedocs.yaml`, installation avec uv) : https://onelook-alert-elf.readthedocs.io/fr/latest/ (solution principale tant que le compte GitHub est bloqué pour un problème de facturation : Actions désactivées, ticket au support en cours).
- GitHub Pages (`.github/workflows/docs.yml`) : https://elfried96.github.io/onelook-alert_Elf/, actif une fois le compte débloqué.

`site_url` prend `READTHEDOCS_CANONICAL_URL` sur Read the Docs, l'adresse GitHub Pages sinon.
