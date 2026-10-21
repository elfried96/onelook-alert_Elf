# Carnet de données

Le sujet impose de documenter la provenance, les licences, la composition, le découpage et les risques de fuite de chaque source. Cette page est le carnet de données du projet.

!!! note "À compléter"
    Rempli au fur et à mesure de la constitution des données (semaine 1).

## Sources

| Source | Contenu | Capteur | Licence | Utilisée pour |
|---|---|---|---|---|
| Sen1Floods11 | Inondations, 11 événements | Sentinel-1, Sentinel-2 | À vérifier | Alerte inondation |
| CloudSEN12 | Nuages et ombres | Sentinel-2 | À vérifier | Images normales difficiles |
| CaBuAr | Zones brûlées, Californie | Sentinel-2 | À vérifier | Test de l'inconnu |

## Composition

| Partie | Images normales | Images en alerte | Images « inconnu » |
|---|---|---|---|
| Entraînement | – | – | – |
| Validation | – | – | – |
| Test | – | – | – |

## Découpage et risques de fuite

Le découpage se fait **par événement et par région**, jamais au hasard entre tuiles. Deux tuiles voisines d'une même image ne peuvent pas se retrouver l'une en entraînement et l'autre en test.

## Biais et limites

À documenter : répartition géographique, saisons, types de terrain, qualité des annotations.
