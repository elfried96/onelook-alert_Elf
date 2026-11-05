# Limites et échecs

Le sujet demande une analyse des cas d'échec. Chaque erreur notable est décrite avec l'image, la décision du modèle, la bonne réponse et l'explication probable.

!!! note "Premières observations (5 novembre)"
    D'après les décisions du premier réseau sur le test (`runs/mobilenet_v3_small_256/decisions_test_model.csv`). L'analyse image par image vient ensuite.

## Fausses alertes

- **Incendie, 17 tuiles normales, toutes californiennes** : 12 quarts CaBuAr non brûlés et 5 images avant feu. Hors Californie, aucune normale n'est prise pour un incendie. Hypothèse à vérifier à l'œil : ces tuiles portent d'**anciennes cicatrices de feu**, réelles mais absentes du masque de l'événement annoté. Ce serait alors une erreur d'étiquette plutôt que du modèle.
- **Inondation, 3 tuiles** : des rizières au Bangladesh (le seul piège d'eau raté sur 48), un point au hasard en Asie du Sud, et une tuile Sen1Floods11 de Bolivie sous le seuil d'alerte.

## Alertes manquées

- **Inondations, 9 sur 25** (7 en « inconnu », 2 en « normal ») : surtout de **petites inondations**, entre 5 et 10 % de la tuile, juste au-dessus du seuil d'alerte, principalement au Sri Lanka. Une tuile manquée est couverte à 96 % de nuages.
- **Incendies, 17 sur 88** (14 en « inconnu », 3 en « normal ») : des zones brûlées plus petites (médiane 9 % de la tuile, contre 32 % pour les incendies détectés).

## Inconnus

47 tuiles du test (7 %) passent en « inconnu », dont 26 normales, souvent des quarts CaBuAr. La décision « inconnu » attrape donc surtout des cas limites (petites anomalies, bords de zones brûlées), ce qui est son rôle. Son efficacité sur de vrais phénomènes jamais vus (éruptions, glissements, marées noires) reste à mesurer avec le lot dédié.

## Tuiles ambiguës

Sur les 104 tuiles ambiguës du test (entre 0,5 et 5 % d'anomalie), le réseau répond « normal » 56 fois, « inconnu » 28 fois, et alerte 20 fois. C'est cohérent : ces tuiles sont exactement à la frontière.

## Limites connues

- 25 inondations en test : une tuile représente 4 points de rappel.
- Tous les incendies sont californiens, y compris en test.
- Le seuil « inconnu » est calibré sur 501 tuiles de validation, dont 15 inondations.
