# Cadrage

Cette page fixe le périmètre du projet. Elle répond à la première question du sujet : qu'est-ce qui mérite une alerte ?

!!! note "Statut"
    Proposition initiale du 21 octobre 2026. Le type d'anomalie et le format des images d'évaluation restent à confirmer avec le mentor.

## Ce qui mérite une alerte

**Anomalie visée : les inondations.**

Pourquoi ce choix :

- **Données publiques de qualité.** Sen1Floods11 couvre 11 événements dans des pays différents, avec des masques annotés à la main.
- **Évaluation honnête possible.** On peut entraîner sur certains pays et tester sur d'autres, ce qui répond à l'exigence « zones et dates jamais vues ».
- **Distinction eau permanente / eau d'inondation.** Le jeu de données la fournit : une rivière ou un lac ne doit pas déclencher d'alerte.
- **Sentinel-1 et Sentinel-2.** Le radar voit à travers les nuages, l'optique est plus simple à interpréter.

Une image déclenche une alerte quand **la part de pixels inondés dépasse un seuil**. Le seuil sera fixé et justifié pendant la première semaine.

## Ce qui ne doit pas déclencher d'alerte

| Situation | Pourquoi c'est un piège |
|---|---|
| Rivières, lacs, littoral | De l'eau, mais permanente |
| Nuages et leurs ombres | Ressemblent à de l'eau en optique |
| Rizières et champs irrigués | Eau saisonnière normale |
| Neige et glace | Très réfléchissantes, confondues avec de l'eau |
| Zones urbaines denses | Signal radar trompeur |

## Ce qui est « inconnu »

Toute image dont le contenu sort de ce que le modèle a appris : zones brûlées, dégâts de catastrophe, capteur différent, image corrompue. Le modèle doit répondre <span class="ol-badge ol-badge--unknown">Inconnu</span> plutôt que forcer une réponse.

## Questions ouvertes pour le mentor

- Quel satellite et quelles bandes auront les images d'évaluation ?
- Sous quel format (GeoTIFF multispectral, PNG RGB) et à quelle taille ?
- Un type d'anomalie bien traité suffit-il, ou plusieurs sont-ils attendus ?

## Planning

| Période | Objectif |
|---|---|
| 21 → 27 oct | Cadrage, données, découpage propre, première approche simple |
| 28 oct → 6 nov | Réseau léger, améliorations mesurées, détection de l'inconnu, comparatif |
| 7 → 13 nov | Allègement (ONNX, quantification), cas d'échec, démo, carnet de données |
| 14 → 16 nov | Marge, relecture, répétition de la démo |
