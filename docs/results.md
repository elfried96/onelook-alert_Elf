# Résultats

Tableau comparatif des approches testées, demandé par le sujet. Toutes les mesures sont faites sur le même **jeu de test** : 747 tuiles de zones jamais vues à l'entraînement, dont 546 hors tuiles ambiguës (433 normales, 25 inondations, 88 incendies). Les définitions sont dans `onelook.evaluation.metrics`.

!!! note "Étiquettes v3 (9 novembre)"
    Toutes les lignes sont mesurées avec les étiquettes v3 : les normales californiennes recouvertes par un feu de l'année de l'image ou de l'année précédente sont écartées (voir [anciens feux](data/labels_splits.md#anciens-feux-des-normales-qui-nen-sont-pas)). Les lignes « entraîné en v1 / v2 » sont d'anciens réseaux, entraînés sur des étiquettes moins propres et gardés pour comparaison. Entraînements sur Colab (`notebooks/03_colab_entrainement.ipynb`), temps mesurés en local. Quantification et piste VLM à venir.

| Approche | Précision (inond. · incendie) | Rappel (inond. · incendie) | Fausses alertes | Fausses alertes sur l'eau | Taille (Mo) | Temps (ms) |
|---|---|---|---|---|---|---|
| Seuils NDWI + NBR | 13 % · 89 % | 52 % · 81 % | 22 % | 88 % | 0,00 | 17 ¹ |
| Classifieur sur statistiques | 50 % · 84 % | 60 % · 65 % | 6,0 % | 31 % | 2,59 | 34 ¹ |
| MobileNetV3-Small, 256 px, entraîné en v1 | 84 % · 97 % | 64 % · 81 % | 1,2 % | 2,1 % | 6,10 | 7,6 ² |
| MobileNetV3-Small, 256 px, entraîné en v2 | 90 % · 84 % | 76 % · 97 % | 4,2 % | 8,3 % | 6,10 | 6,9 ² |
| MobileNetV3-Small, 512 px, entraîné en v2 | 90 % · 95 % | 72 % · 94 % | 1,4 % | 2,1 % | 6,10 | 15,4 ² |
| MobileNetV3-Small, 256 px, entraîné en v3 | 92 % · 100 % | 44 % · 98 % | 0,2 % | 2,1 % | 6,10 | 6,8 ² |
| **MobileNetV3-Small, 512 px, entraîné en v3** | **94 % · 99 %** | **60 % · 94 %** | **0,5 %** | **0 %** | **6,10** | **14,7 ²** |
| MobileNetV3-Small, ONNX quantifié | – | – | – | – | – | – |
| Petit VLM compressé | – | – | – | – | – | – |

Réseaux avec la décision « inconnu » (seuil de confiance calibré sur la validation). ¹ Calcul des indices et statistiques en Python (NumPy), sur Colab. ² ONNX Runtime, un cœur d'un Intel Core i7-10850H ; les quatre derniers réseaux ont été chronométrés ensemble, en alternance, pour être comparables.

**Lecture rapide :**

- Les seuils voient « de l'eau », pas « de l'eau inhabituelle » : 88 % des pièges d'eau (océan, fleuve, lac, rizières) déclenchent une alerte inondation.
- Le classifieur sur statistiques réduit les fausses alertes (6 %), mais rate plus d'un incendie sur trois : une zone brûlée de 5 à 15 % de la tuile se noie dans des moyennes.
- **Avec des étiquettes propres, les fausses alertes deviennent rares.** Le réseau à 512 px entraîné en v3 ne se trompe que sur 2 normales sur 433 (0,5 %) : une tuile de désert prise pour un incendie, des mares en Bolivie prises pour une inondation. Aucune des 48 tuiles pièges d'eau ne déclenche d'alerte. La précision incendie atteint 99 %.
- **Le prix : des inondations plus souvent en « inconnu ».** Le rappel inondation tombe à 60 % (15 sur 25), contre 72 % pour le 512 px v2. L'écart tient en 3 tuiles, dans la marge d'incertitude ; 6 des 10 inondations manquées vont en « inconnu », dont 3 avec une confiance de 0,79 à 0,82, juste sous le seuil (0,83). Sans « inconnu », le rappel inondation remonte à 76 %.
- **Le 512 px v3 devient le modèle de référence**, pour un système d'alerte où une fausse alerte coûte cher. Si la priorité était de rater le moins d'inondations possible, le 512 px v2 ou un seuil « inconnu » plus bas (piste à mesurer) ferait mieux.
- Le 256 px v3 fait encore moins de fausses alertes (1 sur 433), mais rate plus de la moitié des inondations (44 %) : son seuil « inconnu » est plus haut (0,87). La pleine résolution aide surtout les petites zones, pour le double du temps (15 ms au lieu de 7) et la même taille de modèle.
- **Un seul entraînement par ligne** : un écart de 1 à 2 points, ou de 2 à 3 inondations, entre deux lignes n'est pas significatif. Le 256 px v2 l'a montré (une autre meilleure époque, un autre seuil, un autre compromis).

### Réseau de référence (512 px, v3) : matrice de confusion sur le test

Chaque ligne est une vérité, chaque colonne une décision du modèle. La diagonale compte les bonnes réponses ; hors diagonale, la ligne « Normal » donne les **faux positifs** (fausses alertes), et la colonne « Normal » les **faux négatifs** (anomalies manquées). La teinte suit la part de la ligne.

<figure markdown="span">
  ![Matrice de confusion du réseau à 512 px v3 sur le test](assets/figures/echecs512v3_matrice_confusion.png)
  <figcaption>Réseau à 512 px entraîné en v3, 546 tuiles de test. Les erreurs sont détaillées tuile par tuile dans <a href="../failure_cases/">Limites et échecs</a>.</figcaption>
</figure>

| Vérité \ Décision | Normal | Alerte · inondation | Alerte · incendie | Inconnu |
|---|---|---|---|---|
| Normal (433) | 415 | 1 | 1 | 16 |
| Alerte · inondation (25) | 4 | 15 | 0 | 6 |
| Alerte · incendie (88) | 2 | 0 | 83 | 3 |

Sans la décision « inconnu » (on garde toujours la classe la plus probable), le même réseau atteint 76 % de rappel inondation et 95 % de rappel incendie, pour 2,3 % de fausses alertes. « Inconnu » concerne 4,6 % des tuiles. Pour comparaison, le 512 px v2 : 417 / 2 / 4 / 10 sur les normales, 2 / 18 / 0 / 5 sur les inondations, 2 / 0 / 83 / 3 sur les incendies.

### Courbes d'entraînement

15 époques pour chaque réseau, environ 52 s chacune sur un T4, à 256 comme à 512 px (la lecture des tuiles domine). À 512 px, le F1 macro de validation atteint 0,94 (époque 14, retenue), contre 0,92 à 256 px (époque 13). En validation, le rappel des inondations atteint 87 % (13 sur 15) et celui des incendies 88 %, contre environ 70 % avec les étiquettes v2 : les normales recouvertes par un ancien feu brouillaient aussi la validation.

## Comment lire le tableau

| Colonne | Définition |
|---|---|
| Précision | Parmi les alertes levées, la part qui est juste |
| Rappel | Parmi les vraies anomalies, la part détectée. Une réponse « inconnu » compte comme manquée |
| Fausses alertes | Part des tuiles normales qui déclenchent une alerte |
| Fausses alertes sur l'eau | Idem, sur les 48 normales avec océan, fleuve, lac, réservoir ou rizières |
| Taille | Fichier du modèle (ONNX, ou seuils et classifieur pour les baselines) |
| Temps | Médiane par tuile 512 × 512, sur un seul cœur de processeur : l'approximation la plus proche d'un calculateur embarqué |

Mesures complémentaires, dans les fichiers `runs/<nom>/eval_test_*.json` : F1 macro, part d'« inconnu », fausses alertes hors Californie. Les runs v1, v2 et v3 sont rangés dans le dépôt privé `Elfried9684/onelook-alert-runs`.

**Incertitude :** avec 25 inondations en test, une seule tuile manquée fait varier le rappel de 4 points.

## Matériel

- Entraînement : Google Colab, GPU NVIDIA T4.
- Temps d'inférence : un cœur de processeur, ONNX Runtime ; la machine de mesure est indiquée avec chaque résultat.
