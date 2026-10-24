# Carnet de données

Le sujet impose de documenter la provenance, les licences, la composition, le découpage et les risques de fuite de chaque source. Cette page est le carnet de données du projet.

!!! note "À compléter"
    Rempli au fur et à mesure de la constitution des données (semaine 1).

## Sources

| Source | Contenu | Capteur | Licence | Utilisée pour |
|---|---|---|---|---|
| Sen1Floods11 | Inondations, 11 événements, 446 tuiles 512 × 512 annotées à la main | Sentinel-2 L1C (Sentinel-1 non utilisé) | À vérifier : aucune licence dans le dépôt GitHub | Alerte inondation |
| CaBuAr | Zones brûlées, Californie, avant et après feu, 534 tuiles 512 × 512 | Sentinel-2 L2A (masques CAL FIRE) | CDLA-Permissive-2.0 | Alerte incendie |
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
| Toutes les zones brûlées en Californie | Test sur des feux d'autres régions  |

## Premiers constats (exploration du 24 octobre)

Source : `notebooks/01_exploration.ipynb`, sur 6 tuiles Sen1Floods11 et 3 tuiles CaBuAr, plus les masques des 446 tuiles Sen1Floods11.

**Sen1Floods11**

| Pays | Tuiles | | Pays | Tuiles |
|---|---|---|---|---|
| USA | 69 | | Somalie | 26 |
| Inde | 68 | | Nigeria | 18 |
| Paraguay | 67 | | Bolivie | 15 |
| Ghana | 53 | | Espagne | 30 |
| Sri Lanka | 42 | | Mékong | 30 |
| Pakistan | 28 | | | |

En moyenne, 86 % des pixels d'une tuile sont visibles (le reste : nuages ou hors image).

| Seuil de part inondée | Tuiles en alerte | Part des tuiles |
|---|---|---|
| 1 % | 273 | 61 % |
| 2 % | 216 | 48 % |
| 5 % | 139 | 31 % |
| 10 % | 89 | 20 % |
| 20 % | 43 | 10 % |

Sen1Floods11 ne contient que des scènes d'inondation : il faudra d'autres sources pour les images normales.

**Constats**

- L'eau d'inondation est souvent boueuse : marron en couleurs naturelles, mais noire en infrarouge.
- NDWI > 0, sans apprentissage, s'accorde à 73-97 % des pixels sur les tuiles inondées et à 100 % sur les tuiles sèches.
- **L'eau a aussi un NBR très bas** : sur une tuile CaBuAr côtière, l'océan (NBR −0,46) est plus bas que la zone brûlée (−0,31). Le NBR seul confondrait mer et brûlé.
- **L1C et L2A diffèrent fortement**, surtout en SWIR : médiane de B12 à 0,05 dans Sen1Floods11 contre 0,23 dans CaBuAr. Une partie vient du niveau de traitement, une partie des paysages. L'harmonisation est indispensable.
- Les tuiles CaBuAr examinées sont peu brûlées (3 à 10 %) : il faudra en parcourir davantage. À vérifier : le décalage de +1 000 appliqué aux images L2A depuis janvier 2022.

## Biais et limites

À documenter : répartition géographique, saisons, types de terrain, qualité des annotations.
