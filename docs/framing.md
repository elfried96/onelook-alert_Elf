# Cadrage

Cette page fixe le périmètre du projet. Elle répond à la première question du sujet : qu'est-ce qui mérite une alerte ?

!!! note "Statut"
    Format des images validé avec le mentor le 21 octobre 2026. Périmètre élargi aux incendies le 23 octobre. Reste à confirmer : le niveau de traitement des images d'évaluation (L1C ou L2A).

## Décisions

| Point | Décision |
|---|---|
| Satellite | **Sentinel-2** (optique). Sentinel-1 (radar) est écarté : plus difficile à prendre en main dans le temps imparti. |
| Format | **GeoTIFF multibande** : toutes les bandes sont conservées à l'entrée. |
| Bandes | Libre : on garde celles qui sont utiles (voir plus bas). |
| Taille | Tuiles de **512 × 512 pixels**, soit environ 5 × 5 km au sol. |
| Anomalies | **Inondations et incendies** (zones brûlées récentes). Les autres phénomènes servent à tester l'inconnu. |

## Les quatre décisions du modèle

Le modèle regarde l'image une seule fois et répond par une seule décision :

| Décision | Signification |
|---|---|
| <span class="ol-badge ol-badge--normal">Normal</span> | Rien à signaler, y compris les rivières, les lacs, les champs et les nuages. |
| <span class="ol-badge ol-badge--alert">Alerte · inondation</span> | La part de pixels inondés dépasse un seuil. |
| <span class="ol-badge ol-badge--alert">Alerte · incendie</span> | La part de pixels brûlés récemment dépasse un seuil. |
| <span class="ol-badge ol-badge--unknown">Inconnu</span> | L'image ne ressemble à rien de connu. Elle est envoyée au sol pour vérification. |

Les seuils seront fixés et justifiés pendant la première semaine.

## Pourquoi ces anomalies

### Inondations
- **Sen1Floods11** couvre 11 événements dans des pays différents, avec des masques annotés à la main et des tuiles Sentinel-2 de 512 × 512 pixels.
- On peut entraîner sur certains pays et tester sur d'autres, ce qui répond à l'exigence « zones et dates jamais vues ».
- Le jeu de données distingue l'eau permanente de l'eau d'inondation : une rivière ou un lac ne doit pas déclencher d'alerte.
- L'eau absorbe presque tout l'infrarouge : elle est très sombre dans les bandes B08, B11 et B12.

### Incendies
- **CaBuAr** fournit des tuiles Sentinel-2 de 512 × 512 pixels avant et après des feux en Californie, avec les masques des zones brûlées.
- Le sol brûlé a une signature nette : le proche infrarouge (B08) chute et l'infrarouge à ondes courtes (B12) monte. L'indice NBR mesure cet écart.
- Une alerte « incendie » signale une **zone brûlée récente**. Détecter un feu en cours (flammes, fumée) est un bonus possible si des données adaptées existent.
- Limite connue : toutes les images viennent de Californie. Il faudra compléter avec d'autres régions pour tester des zones jamais vues.

### Pourquoi pas les dégâts de catastrophe (xBD)
Les images de xBD / xView2 viennent d'un autre satellite (Maxar), en RGB à environ 0,5 m par pixel. Elles servent à repérer des **bâtiments endommagés**. Sur Sentinel-2, un pixel fait 10 m : un bâtiment tient dans un ou deux pixels et ses dégâts sont invisibles. Ces images ne correspondent pas non plus au format de l'évaluation. Elles sont donc écartées.

Les catastrophes visibles à 10 m (éruptions, grands glissements de terrain, marées noires) servent à tester la décision <span class="ol-badge ol-badge--unknown">Inconnu</span>.

## Bandes Sentinel-2 retenues (première hypothèse)

| Bande | Domaine | Utilité |
|---|---|---|
| B02, B03, B04 | Bleu, vert, rouge | Image visible, visualisation de la démo |
| B08 | Proche infrarouge | Eau très sombre, végétation très claire, chute après un feu |
| B11, B12 | Infrarouge à ondes courtes (SWIR) | Séparent l'eau des ombres ; montent fortement sur le sol brûlé |

| Indice | Formule | Repère |
|---|---|---|
| NDWI | (B03 − B08) / (B03 + B08) | L'eau |
| MNDWI | (B03 − B11) / (B03 + B11) | L'eau, mieux séparée des villes |
| NBR | (B08 − B12) / (B08 + B12) | Le sol brûlé (valeur basse) |

Passer de 13 à 6 bandes allège le modèle. L'effet de ce choix sera mesuré.

## Ce qui ne doit pas déclencher d'alerte

| Situation | Piège pour | Pourquoi |
|---|---|---|
| Rivières, lacs, littoral | Inondation | De l'eau, mais permanente |
| Rizières et champs irrigués | Inondation | Eau saisonnière normale |
| Neige et glace | Inondation | Très réfléchissantes, confondues avec de l'eau |
| Ombres de nuages, de relief, de bâtiments | Inondation, incendie | Sombres comme l'eau ou le brûlé |
| Champs labourés, sol nu sombre | Incendie | Peuvent ressembler à du sol brûlé |
| Roches volcaniques, asphalte | Incendie | Sombres dans le proche infrarouge |
| Feux agricoles contrôlés | Incendie | Petits et habituels ; le seuil de surface les écarte |

**Images très nuageuses :** le modèle ne lance pas d'alerte sur ce qu'il ne voit pas. Une image où le sol est en grande partie caché est classée <span class="ol-badge ol-badge--normal">Normal</span> ou <span class="ol-badge ol-badge--unknown">Inconnu</span> selon la part de nuages. Le seuil sera fixé pendant la première semaine.

## Le point clé : harmoniser L1C et L2A

Sen1Floods11 est en niveau **L1C** (réflectance au sommet de l'atmosphère). CaBuAr est en niveau **L2A** (réflectance de surface). Les valeurs des pixels n'ont pas le même sens.

Mélanger les deux sans précaution crée une **fuite** : le modèle apprendrait « L1C = inondation, L2A = incendie » au lieu de reconnaître l'eau et le brûlé. Toutes les images sont donc relues en **L2A depuis une source unique** (Microsoft Planetary Computer), aux mêmes lieux et aux mêmes dates. La méthode et les contrôles sont décrits dans le carnet de données. Si le mentor indique que l'évaluation sera en L1C, la même méthode s'appliquera avec une source L1C.

## Question ouverte

Les images d'évaluation seront-elles en niveau **L1C** ou **L2A** ? La réponse fixe le niveau de toutes les données d'entraînement.

## Planning

| Période | Objectif |
|---|---|
| 23 → 29 oct | Harmoniser les données, constituer inondations, incendies et images normales, approches simples (NDWI, NBR et seuils) |
| 30 oct → 7 nov | Réseau léger à quatre décisions, détection de l'inconnu, tableau comparatif |
| 8 → 13 nov | Allègement (ONNX, quantification), cas d'échec, démo, carnet de données |
| 14 → 16 nov | Marge, relecture, répétition de la démo |

**Filet de sécurité :** si la partie incendies prend du retard, le modèle inondation seul reste un projet complet, validé par le mentor.
