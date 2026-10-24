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

## Harmonisation : une seule source, un seul niveau

Sen1Floods11 est en L1C à 10 m, CaBuAr en L2A à 20 m. Pour que le modèle apprenne le phénomène et non la source, **toutes les tuiles sont relues depuis une source unique**, quelle que soit leur classe :

| | Choix |
|---|---|
| Source | Microsoft Planetary Computer, collection `sentinel-2-l2a` (archive complète depuis 2015, accès gratuit sans compte) |
| Niveau | **L2A** (réflectance de surface), 12 bandes |
| Résolution | 10 m ; les bandes à 20 et 60 m sont rééchantillonnées (bilinéaire) |
| Valeurs | Réflectance × 10 000. Le décalage de +1 000 des scènes traitées depuis 2022 (baseline 04.00) est retiré |
| Tuile | 512 × 512 pixels, enregistrée en GeoTIFF avec la carte de classification SCL (nuages, eau, neige) |
| Lecture | À distance (COG) : seuls les octets de la tuile sont lus, environ 3 s par tuile |

**Pourquoi L2A :** c'est le seul niveau disponible gratuitement, sans compte et sur toute l'archive. Il retire l'effet de l'atmosphère, donc les images de régions et de dates différentes se comparent mieux. Si le mentor confirme que l'évaluation sera en L1C, on basculera sur le Copernicus Data Space (compte gratuit requis).

**Comment chaque source est relue :**

- **Sen1Floods11** : même grille que les masques annotés (EPSG:4326, ~10 m), même jour d'acquisition (`s2_date` des métadonnées). Les masques sont réutilisés tels quels.
- **CaBuAr** : le fichier pré-découpé renumérote ses tuiles, sans géoréférence. Chaque tuile est retrouvée dans sa scène par corrélation de la bande B08 en basse résolution (score de 0,98 à 0,997), puis relue à 10 m. Une tuile CaBuAr de 10 × 10 km donne 4 tuiles de 512 × 512 ; le masque est agrandi en conséquence (plus proche voisin).
- **Images normales** : tuiles centrées sur les sites de `configs/normal_sites.yaml`, au passage le moins nuageux de la période (ou le plus nuageux pour la catégorie « nuages »).

**Contrôles sur l'échantillon (25 octobre) :**

| Contrôle | Résultat |
|---|---|
| Alignement Sen1Floods11 L1C / L2A relu (corrélation B08) | 0,985 à 0,996 |
| Alignement CaBuAr d'origine / relu (corrélation B08) | 0,92 à 0,996 |
| Médiane B02 (bleu) : Sen1Floods11 L1C → L2A, CaBuAr | 0,142 → **0,087**, CaBuAr 0,079 |
| Médiane B12 (SWIR) : Sen1Floods11 L2A, CaBuAr | 0,067 contre 0,227 |

Le bleu, très sensible à l'atmosphère, est maintenant au même niveau dans les deux sources : l'écart dû au traitement a disparu. **L'écart restant en SWIR vient des paysages** (zones tropicales humides contre Californie sèche). C'est un biais réel : sans images normales sèches, le modèle pourrait associer « paysage sec » à « incendie ». D'où les sites normaux en Californie, au Sahara, au Sahel et en Mongolie.

## Images normales : premier lot (25 octobre)

28 tuiles, une par site de `configs/normal_sites.yaml`, toutes vérifiées à l'œil sur une planche-contact.

| Famille | Catégories | Tuiles |
|---|---|---|
| Paysages variés | forêt tropicale, désert, savane, cultures, steppe, toundra, plantations, Californie sans feu | 11 |
| Pièges « inondation » | rivière, lac, lagune, littoral, océan côtier, rizières, neige, salar, ombres de relief, nuages | 13 |
| Pièges « incendie » | sol labouré sombre, roche volcanique, villes (asphalte) | 4 |

Constats :

- **La carte SCL se trompe sur certains pièges** : elle classe le salar d'Uyuni en neige (100 %) et une grande partie des laves de Lanzarote en eau (83 %). Ce sont exactement les confusions que le modèle devra éviter.
- La tuile d'océan côtier montre une bande claire à bord net : un raccord entre deux scènes du même passage. Elle est gardée comme normale, car ce genre d'artefact peut apparaître en évaluation.
- Trois sites ont été déplacés après vérification visuelle : le premier site « labours » tombait sur un réservoir, le site « rizières » sur une ville, et le site « océan » au-delà de la zone photographiée par Sentinel-2.
- C'est un premier lot : il faudra plusieurs centaines de tuiles normales, et plusieurs dates par site.

**Seuil NDWI :** en L2A, le seuil NDWI > 0 sous-estime l'eau boueuse. Sur l'échantillon, le meilleur seuil est entre −0,35 et −0,2. Il sera calibré sur la partie entraînement uniquement.

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

- L'eau d'inondation est souvent boueuse : marron en couleurs naturelles, mais très sombre dans la bande B08 (proche infrarouge), d'où sa couleur bleu-cyan dans la composition infrarouge.
- Les annotations ne marquent pas toujours la brume et les nuages fins : une tuile du Ghana est voilée mais comptée visible à 100 %.
- NDWI > 0, sans apprentissage, s'accorde à 73-97 % des pixels sur les tuiles inondées et à 100 % sur les tuiles sèches.
- **L'eau a aussi un NBR très bas** : sur une tuile CaBuAr côtière, l'océan (NBR −0,46) est plus bas que la zone brûlée (−0,31). Le NBR seul confondrait mer et brûlé.
- **L1C et L2A diffèrent fortement**, surtout en SWIR : médiane de B12 à 0,05 dans Sen1Floods11 contre 0,23 dans CaBuAr. Une partie vient du niveau de traitement, une partie des paysages. L'harmonisation est indispensable.
- Les tuiles CaBuAr examinées sont peu brûlées (3 à 10 %) : il faudra en parcourir davantage. À vérifier : le décalage de +1 000 appliqué aux images L2A depuis janvier 2022.

## Biais et limites

À documenter : répartition géographique, saisons, types de terrain, qualité des annotations.
