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

Jeu complet constitué le 28 octobre (`scripts/build_dataset.py`) : **3 228 tuiles** 512 × 512 à 10 m, 12 bandes L2A, environ 16 Go. Décision attendue de chaque tuile selon `configs/labels.yaml` : parts d'anomalie calculées sur la tuile entière, alerte à partir de 5 %, normale sous 0,5 %, ambiguë entre les deux.

| Partie | Normal | Alerte · inondation | Alerte · incendie | Ambiguë (écartée) | Total |
|---|---|---|---|---|---|
| Entraînement | 1 336 | 88 | 286 | 277 | 1 987 |
| Validation | 396 | 15 | 66 | 53 | 530 |
| Test | 494 | 25 | 88 | 104 | 711 |
| **Total** | **2 226** | **128** | **440** | **434** | **3 228** |

Origine des tuiles :

| Source | Tuiles | Rôle |
|---|---|---|
| Sen1Floods11, relu en L2A | 434 | inondations, et normales quand l'eau d'inondation est absente |
| CaBuAr, relu en L2A | 2 108 | zones brûlées ; les quarts non touchés sont des normales |
| CaBuAr, image avant feu | 352 | normales : le même lieu, avant l'incendie |
| Catalogue de sites | 149 | normales variées et pièges (neige, désert, lave, rizières…) |
| Points au hasard | 185 | normales tirées dans 15 régions du monde |

Pertes : 76 tâches n'ont pas abouti, soit 2,3 % :
- 34 sites normaux sans passage assez clair ou assez nuageux ;
- 20 tuiles L2A incomplètes au bord des orbites ;
- 17 tuiles CaBuAr dont la lecture distante échoue à chaque essai ;
- 5 tuiles CaBuAr dont la position n'a pas été retrouvée (corrélation trop faible).

Les images « inconnu » (éruptions, glissements, marées noires) formeront un lot à part, seulement en test, jamais en entraînement.

## Découpage et risques de fuite

Le découpage se fait **par groupe**, jamais au hasard entre tuiles (`configs/splits.yaml`). Chaque groupe entier va dans une seule partie :

- **Inondations :** groupe = pays de l'événement.
  - Test : Bolivie, Espagne, Sri Lanka.
  - Validation : Nigeria, Somalie.
  - Entraînement : les six autres pays.
- **Incendies :** groupe = zone spatiale.
  - Les tuiles CaBuAr reliées de proche en proche à moins de 10 km forment une zone.
  - Chaque zone entière va dans une partie, en visant 65 / 15 / 20 % des tuiles brûlées (`onelook.data.splits`).
  - Une image avant feu, ou une normale située à moins de 10 km, suit sa zone.
- **Normales du catalogue et points au hasard :** groupe = grande région.
  - Test : Asie du Sud, Australie, Himalaya, Californie du Sud.
  - Validation : Europe du Nord, Afrique de l'Est, Afrique australe, Moyen-Orient.

Au total, 95 groupes vont en entraînement, 24 en validation et 25 en test.

**Contrôle de fuite spatiale** (`scripts/dataset_report.py`) : aucune paire de tuiles de parties différentes à moins de 10 km.

Ce contrôle a corrigé un premier découpage. Les plis fournis par CaBuAr séparent des scènes, pas des lieux : la même zone revient à plusieurs dates dans des plis différents. Le premier découpage, par pli, laissait 1 805 paires de tuiles de parties différentes à moins de 10 km, certaines au même endroit exact. Le site `californie_collines` du catalogue touchait aussi des zones CaBuAr de test.

| Risque | Parade |
|---|---|
| Tuiles voisines d'une même scène réparties entre entraînement et test | Découpage par groupe, contrôle à 10 km |
| Même lieu brûlé à plusieurs dates dans des parties différentes | Zones spatiales au lieu des plis CaBuAr |
| Avant et après d'un même feu dans deux parties différentes | L'image avant feu suit sa zone |
| Niveaux L1C et L2A mélangés : le modèle reconnaîtrait la source au lieu du phénomène | Tout relu en L2A depuis Planetary Computer |
| Toutes les zones brûlées en Californie | Limite assumée ; test complémentaire sur des feux d'autres régions à prévoir |

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

- **Californie surreprésentée chez les normales.** 1 764 des 2 226 normales, soit 79 %, sont des quarts CaBuAr non brûlés ou des images avant feu. Un modèle pourrait associer « paysage californien » et « feu ». Parades prévues : pondérer les normales par source à l'entraînement, et mesurer les fausses alertes séparément sur les normales hors Californie.
- **Peu d'inondations.** 128 alertes seulement, dont 25 en test : les mesures de rappel sur les inondations auront une forte incertitude, à indiquer avec un intervalle.
- **Inondations nuageuses.** Beaucoup de tuiles d'inondation sont prises en saison des pluies, avec des nuages : la part d'inondation est comptée sur la tuile entière, donc l'eau cachée ne déclenche pas d'alerte attendue.
- **Feux d'une seule région et d'un seul type** (végétation méditerranéenne californienne) : la généralisation à d'autres biomes n'est pas garantie.
- **Points au hasard non vérifiés un par un** : un point peut tomber sur une anomalie non annotée (crue locale, brûlis agricole).
- **Tuiles ambiguës écartées** (434) : elles seront analysées à part, car c'est là que le modèle hésitera le plus.
