# Carnet de données

Le sujet impose de documenter la provenance, les licences, la composition, le découpage et les risques de fuite de chaque source. Cette page est le carnet de données du projet.

!!! note "À compléter"
    Rempli au fur et à mesure de la constitution des données (semaine 1).

## Sources

| Source | Contenu | Capteur | Licence | Utilisée pour |
|---|---|---|---|---|
| Sen1Floods11 | Inondations, 11 événements, tuiles 512 × 512 | Sentinel-2 L1C (Sentinel-1 non utilisé) | À vérifier | Alerte inondation |
| CaBuAr | Zones brûlées, Californie, avant et après feu, tuiles 512 × 512 | Sentinel-2 L2A | À vérifier | Alerte incendie |
| CloudSEN12 | Nuages et ombres | Sentinel-2 | À vérifier | Images normales difficiles |
| Copernicus Browser / Copernicus EMS | Éruptions, glissements de terrain, marées noires… | Sentinel-2 | À vérifier | Test de l'inconnu |
| xBD / xView2 | Dégâts aux bâtiments | Maxar, RGB ~0,5 m | – | **Écarté** : résolution et capteur incompatibles avec Sentinel-2 (voir Cadrage) |

## Format des images

Toutes les images sont des **GeoTIFF Sentinel-2 de 512 × 512 pixels**, le format retenu avec le mentor pour l'évaluation. Les bandes conservées sont listées dans la page Cadrage.

**Harmonisation des niveaux :** Sen1Floods11 est en L1C, CaBuAr en L2A. Toutes les images seront ramenées au même niveau, celui des images d'évaluation, en retéléchargeant les scènes aux mêmes lieux et aux mêmes dates. La méthode sera décrite ici.

## Composition

| Partie | Normal | Alerte · inondation | Alerte · incendie | Inconnu |
|---|---|---|---|---|
| Entraînement | – | – | – | – |
| Validation | – | – | – | – |
| Test | – | – | – | – |

Les images « inconnu » ne servent qu'à la validation et au test, jamais à l'entraînement.

## Découpage et risques de fuite

Le découpage se fait **par événement et par région**, jamais au hasard entre tuiles. Deux tuiles voisines d'une même image ne peuvent pas se retrouver l'une en entraînement et l'autre en test.

Risques de fuite identifiés :

| Risque | Parade |
|---|---|
| Tuiles voisines d'une même scène réparties entre entraînement et test | Découpage par événement |
| Niveau L1C pour les inondations, L2A pour les incendies : le modèle reconnaîtrait la source au lieu du phénomène | Harmonisation au même niveau |
| Avant et après d'un même feu dans deux parties différentes | Un feu entier dans une seule partie |
| Toutes les zones brûlées en Californie | Test sur des feux d'autres régions

## Biais et limites

À documenter : répartition géographique, saisons, types de terrain, qualité des annotations.
