# Cadrage

Cette page fixe le périmètre du projet. Elle répond à la première question du sujet : qu'est-ce qui mérite une alerte ?

!!! note "Statut"
    Périmètre validé avec le mentor le 21 octobre 2026. Reste à confirmer : le niveau de traitement des images d'évaluation (L1C ou L2A).

## Décisions validées avec le mentor

| Point | Décision |
|---|---|
| Satellite | **Sentinel-2** (optique). Sentinel-1 (radar) est écarté : plus difficile à prendre en main dans le temps imparti. |
| Format | **GeoTIFF multibande** : toutes les bandes sont conservées à l'entrée. |
| Bandes | Libre : on garde celles qui sont utiles (voir plus bas). |
| Taille | Tuiles de **512 × 512 pixels**, la taille des tuiles de Sen1Floods11. |
| Anomalie | **Les inondations uniquement.** Un seul type d'anomalie bien traité suffit. |

## Ce qui mérite une alerte

**Anomalie visée : les inondations**, détectées sur une image Sentinel-2.

Pourquoi ce choix :

- **Données publiques de qualité.** Sen1Floods11 couvre 11 événements dans des pays différents, avec des masques annotés à la main et des images Sentinel-2 de 512 × 512 pixels.
- **Évaluation honnête possible.** On peut entraîner sur certains pays et tester sur d'autres, ce qui répond à l'exigence « zones et dates jamais vues ».
- **Distinction eau permanente / eau d'inondation.** Le jeu de données la fournit : une rivière ou un lac ne doit pas déclencher d'alerte.

Une image déclenche une alerte quand **la part de pixels inondés dépasse un seuil**. Le seuil sera fixé et justifié pendant la première semaine.

## Bandes Sentinel-2 retenues (première hypothèse)

| Bande | Domaine | Utilité |
|---|---|---|
| B02, B03, B04 | Bleu, vert, rouge | Image visible, visualisation de la démo |
| B08 | Proche infrarouge | L'eau y est très sombre, la végétation très claire |
| B11, B12 | Infrarouge à ondes courtes (SWIR) | Séparent l'eau des ombres et de la neige |

Ces bandes permettent de calculer les indices de l'eau NDWI (B03, B08) et MNDWI (B03, B11). Passer de 13 à 6 bandes allège le modèle. L'effet de ce choix sera mesuré.

## Ce qui ne doit pas déclencher d'alerte

| Situation | Pourquoi c'est un piège |
|---|---|
| Rivières, lacs, littoral | De l'eau, mais permanente |
| Nuages et leurs ombres | Masquent le sol ; les ombres ressemblent à de l'eau |
| Rizières et champs irrigués | Eau saisonnière normale |
| Neige et glace | Très réfléchissantes, confondues avec de l'eau |
| Zones urbaines denses | Ombres des bâtiments sombres comme l'eau |

**Images très nuageuses :** le modèle ne lance pas d'alerte sur ce qu'il ne voit pas. Une image où le sol est en grande partie caché est classée <span class="ol-badge ol-badge--normal">Normal</span> ou <span class="ol-badge ol-badge--unknown">Inconnu</span> selon la part de nuages. Le seuil sera fixé pendant la première semaine.

## Ce qui est « inconnu »

Toute image dont le contenu sort de ce que le modèle a appris : zones brûlées, dégâts de catastrophe, image corrompue ou d'un autre capteur. Le modèle doit répondre <span class="ol-badge ol-badge--unknown">Inconnu</span> plutôt que forcer une réponse.

## Question ouverte

Les images d'évaluation seront-elles en niveau **L1C** (réflectance au sommet de l'atmosphère, 13 bandes, comme Sen1Floods11) ou **L2A** (réflectance de surface, 12 bandes) ? Si c'est L2A, il faudra aligner les données d'entraînement ou rendre le modèle robuste aux deux.

## Planning

| Période | Objectif |
|---|---|
| 21 → 27 oct | Cadrage, données, découpage propre, première approche simple |
| 28 oct → 6 nov | Réseau léger, améliorations mesurées, détection de l'inconnu, comparatif |
| 7 → 13 nov | Allègement (ONNX, quantification), cas d'échec, démo, carnet de données |
| 14 → 16 nov | Marge, relecture, répétition de la démo |
