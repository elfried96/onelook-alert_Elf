# Résultats

Tableau comparatif des approches testées, demandé par le sujet. Toutes les mesures sont faites sur le même **jeu de test** : 747 tuiles de zones jamais vues à l'entraînement, dont 643 hors tuiles ambiguës (530 normales, 25 inondations, 88 incendies). Les définitions sont dans `onelook.evaluation.metrics`.

!!! note "Premiers résultats (5 novembre)"
    Baselines et premier réseau entraînés sur Colab (`notebooks/03_colab_entrainement.ipynb`). Quantification et piste VLM à venir.

| Approche | Précision (inond. · incendie) | Rappel (inond. · incendie) | Fausses alertes | Fausses alertes sur l'eau | Taille (Mo) | Temps (ms) |
|---|---|---|---|---|---|---|
| Seuils NDWI + NBR | 11 % · 76 % | 52 % · 77 % | 22 % | 88 % | 0,00 | 17 ¹ |
| Classifieur sur statistiques | 50 % · 75 % | 52 % · 61 % | 6 % | 27 % | 2,80 | 25 ¹ |
| MobileNetV3-Small, 256 px, sans « inconnu » | 79 % · 75 % | 76 % · 91 % | 5,8 % | 6,2 % | 6,10 | 9,6 ² |
| **MobileNetV3-Small, 256 px, avec « inconnu »** | **84 % · 81 %** | **64 % · 81 %** | **3,8 %** | **2,1 %** | **6,10** | **9,6 ²** |
| MobileNetV3-Small, ONNX quantifié | – | – | – | – | – | – |
| Petit VLM compressé | – | – | – | – | – | – |

¹ Calcul des indices et statistiques en Python (NumPy), sur Colab. ² ONNX Runtime, un cœur d'un Intel Core i7-10850H (6,4 ms sur un cœur de Colab).

**Lecture rapide :**

- Les seuils voient « de l'eau », pas « de l'eau inhabituelle » : 88 % des pièges d'eau (océan, fleuve, lac, rizières) déclenchent une alerte inondation.
- Le classifieur sur statistiques réduit les fausses alertes (6 %), mais rate 39 % des incendies : une zone brûlée de 5 à 15 % de la tuile se noie dans des moyennes.
- Le réseau léger voit la forme et le contexte. Sur les 48 pièges d'eau du test, une seule fausse alerte (des rizières au Bangladesh). Il divise les fausses alertes par six par rapport aux seuils.
- La décision « inconnu » (7 % des tuiles, envoyées au sol) fait baisser les fausses alertes de 5,8 à 3,8 %, au prix du rappel : 3 inondations et 9 incendies passent de « détectés » à « inconnu ». Le seuil (confiance 0,84) se règle selon ce que l'on préfère.

### Réseau léger : matrice de confusion sur le test

| Vérité \ Décision | Normal | Alerte · inondation | Alerte · incendie | Inconnu |
|---|---|---|---|---|
| Normal (530) | 484 | 3 | 17 | 26 |
| Alerte · inondation (25) | 2 | 16 | 0 | 7 |
| Alerte · incendie (88) | 3 | 0 | 71 | 14 |

### Courbes d'entraînement

15 époques, environ 55 s chacune sur un T4. Le F1 macro de validation monte de 0,48 à 0,89 (époque 13, retenue). Le rappel des inondations en validation atteint 100 % dès l'époque 11, mais sur 15 tuiles seulement ; celui des incendies plafonne autour de 73 %.

## Comment lire le tableau

| Colonne | Définition |
|---|---|
| Précision | Parmi les alertes levées, la part qui est juste |
| Rappel | Parmi les vraies anomalies, la part détectée. Une réponse « inconnu » compte comme manquée |
| Fausses alertes | Part des tuiles normales qui déclenchent une alerte |
| Fausses alertes sur l'eau | Idem, sur les 48 normales avec océan, fleuve, lac, réservoir ou rizières |
| Taille | Fichier du modèle (ONNX, ou seuils et classifieur pour les baselines) |
| Temps | Médiane par tuile 512 × 512, sur un seul cœur de processeur : l'approximation la plus proche d'un calculateur embarqué |

Mesures complémentaires, dans les fichiers `runs/<nom>/eval_test_*.json` : F1 macro, part d'« inconnu », fausses alertes hors Californie.

**Incertitude :** avec 25 inondations en test, une seule tuile manquée fait varier le rappel de 4 points.

## Matériel

- Entraînement : Google Colab, GPU NVIDIA T4.
- Temps d'inférence : un cœur de processeur, ONNX Runtime ; la machine de mesure est indiquée avec chaque résultat.
