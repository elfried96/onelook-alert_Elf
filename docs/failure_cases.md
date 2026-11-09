# Limites et échecs

Le sujet demande une analyse des cas d'échec. Cette page décrit d'abord les erreurs du premier réseau (MobileNetV3-Small, 256 px, étiquettes v1, avec « inconnu ») sur le **jeu de test**, puis ce qui reste après la correction des étiquettes et le réentraînement à 512 px ([plus bas](#apres-correction-512-px-etiquettes-v3)), image par image : ce que le modèle a répondu, la bonne réponse, et l'explication la plus probable.

Les planches sont produites par `scripts/failure_figures.py` à partir des décisions enregistrées (`runs/mobilenet_v3_small_256/decisions_test_model.csv`). Chaque tuile est montrée deux fois : en couleurs naturelles, puis en **infrarouge court** (B12, B08, B04), où le sol brûlé ressort en rouge-brun, l'eau en noir ou bleu sombre et la végétation en vert. Le contour bleu marque l'eau d'inondation annotée, le contour jaune la zone brûlée annotée. Le titre donne la vérité, la décision et la confiance du modèle.

## Vue d'ensemble

| Erreur | Nombre (test) | Explication principale |
|---|---|---|
| Normale → alerte incendie | 17 sur 530 | Anciennes cicatrices de feu absentes du masque (erreur d'étiquette), sols sombres |
| Normale → alerte inondation | 3 sur 530 | Eau saisonnière : rizières, petits réservoirs |
| Inondation manquée | 9 sur 25 | Réservoirs et rizières annotés « inondation », eau en filets fins, nuages |
| Incendie manqué | 17 sur 88 | Petites zones brûlées coupées par le bord de la tuile, périmètres qui englobent de la végétation intacte |

## Fausses alertes incendie : d'anciennes cicatrices

Les 17 fausses alertes incendie sont **toutes californiennes** : 12 quarts CaBuAr sans brûlé annoté et 5 images avant feu. Hors Californie, aucune normale n'est prise pour un incendie.

<figure markdown="span">
  ![Fausses alertes incendie](assets/figures/echecs_fausses_alertes_incendie.jpg)
  <figcaption>Les 8 fausses alertes les plus sûres. En infrarouge court, la plupart montrent de grandes zones rouge-brun, la couleur du brûlé, parfois à bord net (2e tuile).</figcaption>
</figure>

Le rouge-brun peut venir d'une ancienne cicatrice de feu, ou de sol nu et d'herbe sèche d'été. Les **images avant feu** permettent de trancher : prises avant l'incendie annoté, elles ne devraient montrer aucun brûlé lié à cet incendie.

<figure markdown="span">
  ![Images avant feu prises pour un incendie](assets/figures/echecs_avant_feu.jpg)
  <figcaption>Les 5 images avant feu prises pour un incendie. Les deux premières (fin août 2019) montrent déjà des zones noires à bord net, rouge vif en infrarouge court : la cicatrice d'un feu plus ancien. Les deux dernières montrent un lit de rivière sombre : une vraie erreur du modèle.</figcaption>
</figure>

Mesure à l'appui : la part de pixels au « brûlé apparent » (NBR < −0,05 et hors eau) couvre en moyenne **42 %** de la tuile sur les 17 fausses alertes, contre **18 %** sur les 400 normales californiennes bien classées.

**Conclusion :** une partie de ces fausses alertes sont des **erreurs d'étiquette**. CaBuAr n'annote que l'incendie de l'événement ; les cicatrices des feux précédents, réelles et parfois récentes, restent « normales ». Deux conséquences :

- le taux de fausses alertes incendie mesuré (3,2 % des normales) est **surestimé** ;
- à l'entraînement, ces tuiles apprennent au modèle à ignorer de vraies cicatrices, ce qui peut lui coûter des détections.

**Correction appliquée (étiquettes v3, 9 novembre) :** les périmètres de l'historique fédéral NIFC (qui regroupe ceux de CAL FIRE) de l'année de l'image et de l'année précédente sont croisés avec chaque tuile de Californie. Une normale recouverte à plus de 0,5 % passe en ambiguë (détail dans [Étiquettes et découpage](data/labels_splits.md#anciens-feux-des-normales-qui-nen-sont-pas)).

- **15 des 17 fausses alertes** sont recouvertes par un feu récent. Les deux images avant feu de fin août 2019 le sont par le feu Long Valley de juillet 2019 : la « cicatrice plus ancienne » vue sur la planche était fraîche de quelques semaines.
- Les normales recouvertes déclenchent une fausse alerte incendie dans 15 % des cas, les autres dans 0,6 % des cas.
- **Même modèle, étiquettes v3 :** la précision incendie passe de 81 à 97 %, et les fausses alertes de 3,8 à 1,2 %. Rien n'a changé dans le modèle, seulement dans ce qu'on lui reprochait.

Les 2 fausses alertes restantes sont les images avant feu du lit de rivière sombre : de vraies erreurs du modèle.

Une première version de cette correction (v2, 6 novembre) utilisait un historique presque vide après 2019 et n'expliquait que 9 des 17 fausses alertes. L'examen des erreurs du réseau à 512 px a révélé le trou.

## Fausses alertes inondation : l'eau saisonnière

<figure markdown="span">
  ![Fausses alertes inondation](assets/figures/echecs_fausses_alertes_inondation.jpg)
  <figcaption>Les 3 fausses alertes inondation : petits plans d'eau épars en Inde (point au hasard), rizières en eau au Bangladesh, et une tuile de Bolivie sous le seuil d'alerte (rivière et mares).</figcaption>
</figure>

Les trois cas mêlent de l'eau saisonnière normale à un paysage agricole. Sur les 48 pièges d'eau du test (océan, fleuves, lacs, réservoirs, rizières), c'est la seule erreur, sur les rizières : l'océan et les grands fleuves ne posent plus de problème.

## Inondations manquées : une frontière floue

<figure markdown="span">
  ![Inondations manquées](assets/figures/echecs_inondations_manquees.jpg)
  <figcaption>Les 9 inondations manquées, de la plus petite à la plus grande part d'inondation. 7 sont passées en « inconnu », 2 en « normal ».</figcaption>
</figure>

| Cas | Tuiles | Ce qu'on voit |
|---|---|---|
| Plan d'eau compact | 2 (Sri Lanka) | Un seul lac aux bords nets, sans doute un **réservoir d'irrigation saisonnier**, absent de l'eau permanente JRC et donc annoté « inondation » |
| Eau éparse dans les champs | 2 (Sri Lanka) | Des parcelles en eau, très proches des **rizières** qui sont des normales dans le catalogue |
| Filets d'eau fins | 3 (Espagne, Sri Lanka) | Eau le long des cours d'eau, des parcelles ou du littoral, sur 9 à 17 % de la tuile |
| Nuages | 1 (Sri Lanka) | Tuile couverte à 96 % de nuages |
| Vraie erreur | 1 (Espagne, 36 %) | Image très sombre, grande nappe ; le modèle hésite (confiance 0,48) |

**Conclusion :** la moitié des inondations manquées tient à une **frontière de définition** plutôt qu'à une faiblesse du modèle. Le jeu de données dit à la fois « rizières en eau = normal » (pièges du catalogue) et « parcelles en eau au Sri Lanka = inondation » (Sen1Floods11). Le modèle hésite donc, ce qui est cohérent, et répond le plus souvent « inconnu », ce qui envoie quand même la tuile au sol.

C'est exactement la question du contexte (où est l'eau habituellement ?) que la piste du petit VLM, ouverte par le mentor, ou une carte d'eau permanente embarquée pourraient aider à résoudre.

## Incendies manqués : petites zones, périmètres larges

<figure markdown="span">
  ![Incendies manqués](assets/figures/echecs_incendies_manques.jpg)
  <figcaption>Les 8 incendies manqués les plus petits (5 à 9 % de la tuile). La zone brûlée annotée (contour jaune) touche souvent le bord de la tuile, ou englobe de la végétation restée verte.</figcaption>
</figure>

- La zone brûlée médiane des incendies manqués couvre **9 %** de la tuile, contre **32 %** pour les incendies détectés.
- Les zones touchent souvent le **bord de la tuile** : le modèle n'en voit qu'un morceau, sans le contexte du feu.
- Les masques viennent des **périmètres** CAL FIRE : ils englobent des îlots de végétation intacte ou peu touchée (3e tuile). Une partie du « brûlé annoté » n'est pas visible comme tel.
- Une image réduite à 256 × 256 perd les détails fins : l'essai à 512 px dira si la pleine résolution aide.

## Après correction : 512 px, étiquettes v3

Réseau de référence : réentraîné à pleine résolution sur les étiquettes v3, même jeu de test. La colonne « 512 px v2 » est le réseau à pleine résolution entraîné avant la correction, mesuré lui aussi avec les étiquettes v3.

<figure markdown="span">
  ![Matrice de confusion du réseau à 512 px v3](assets/figures/echecs512v3_matrice_confusion.png)
  <figcaption>Matrice de confusion du réseau à 512 px entraîné en v3, sur le test (546 tuiles hors ambiguës).</figcaption>
</figure>

| Erreur | Premier réseau | 512 px v2 | 512 px v3 | Ce qui reste |
|---|---|---|---|---|
| Normale → alerte incendie | 2 | 4 | 1 | 1 tuile de désert (sol nu et roches sombres) |
| Normale → alerte inondation | 3 | 2 | 1 | Mares en Bolivie, sous le seuil d'alerte |
| Inondation manquée | 9 | 7 | 10 | 7 entre 5 et 10 % de la tuile ; 3 entre 16 et 36 %, en « inconnu » juste sous le seuil |
| Incendie manqué | 17 | 5 | 5 | 2 petites zones (5 à 7 %), 3 tuiles à 21 ou 22 % (2 prises pour normales, 1 en « inconnu ») |

<figure markdown="span">
  ![Inondations manquées par le réseau à 512 px v3](assets/figures/echecs512v3_inondations_manquees.jpg)
  <figcaption>Les 10 inondations manquées par le réseau à 512 px v3, de la plus petite à la plus grande part d'inondation (titre : vérité, décision et confiance). 4 sont prises pour normales (3 au Sri Lanka, 1 en Espagne), les 6 autres vont en « inconnu ».</figcaption>
</figure>

- **Les étiquettes propres ont surtout supprimé les fausses alertes incendie** : de 4 à 1. Les 2 lits de rivière des images avant feu, pris pour du brûlé par le 512 px v2, passent en « inconnu » : le réseau hésite au lieu d'alerter. Reste une tuile de désert (nord du Mojave), dont la signature en infrarouge court ressemble à celle du brûlé. Aucune pièce d'eau ne déclenche d'alerte.
- **Les inondations manquées restent à la frontière.** 7 des 10 font entre 5 et 10 % de la tuile, juste au-dessus du seuil d'alerte (4 détectées sur 11 dans cette tranche, contre 11 sur 14 au-delà de 10 %). Les 3 grandes inondations manquées, en Espagne (16, 20 et 36 %), vont en « inconnu », avec une probabilité d'inondation de 0,51 à 0,82 : le réseau penche vers la bonne réponse sans atteindre le seuil.
- **Ce n'est pas un effet du déséquilibre des classes** : les inondations manquées vont surtout en « inconnu » (6 sur 10), pas en « normal ». Les petites inondations pèsent autant à l'entraînement (43 %) qu'en test (48 %) ; le vrai manque, c'est la **variété** (88 inondations d'entraînement, 6 pays).
- **Les incendies manqués sont presque les mêmes** qu'avec le 512 px v2 : 4 des 5 sont communs. La tuile brûlée à 97 % qui passait en « inconnu » est maintenant détectée ; une tuile à 22 %, voisine d'une autre tuile manquée du même feu, la remplace.

<figure markdown="span">
  ![Fausses alertes incendie du réseau à 512 px v2](assets/figures/echecs512_fausses_alertes_incendie.jpg)
  <figcaption>Pour mémoire : les 12 fausses alertes incendie du réseau à 512 px v2 avec les étiquettes v2. Avec l'historique complet des feux, 8 sont recouvertes par un feu de l'année de l'image ou de la précédente (les tuiles rouge-brun en infrarouge court) ; restent les 2 tuiles de désert et les 2 lits de rivière. Le réseau v3 ne garde qu'une tuile de désert.</figcaption>
</figure>

## Inconnus et tuiles ambiguës

- **55 tuiles du test (7 %) passent en « inconnu »** avec le réseau v3, dont 16 normales (3,7 %), 6 inondations et 3 incendies. « Inconnu » attrape surtout des cas limites, ce qui est son rôle. Son efficacité sur de vrais phénomènes jamais vus (éruptions, glissements, marées noires) reste à mesurer avec le lot dédié.
- Sur les **201 tuiles ambiguës**, le réseau répond « normal » 121 fois, « inconnu » 30 fois et alerte 50 fois. 159 de ces tuiles sont des normales recouvertes par un feu récent : le réseau alerte incendie sur 49 d'entre elles, ce qui confirme que ces cicatrices se voient bien sur l'image.

## Pistes d'amélioration, par ordre d'effet attendu

1. ~~Nettoyer les étiquettes incendie~~ avec l'historique des périmètres de feux : fait (étiquettes v3, 9 novembre), puis réentraînement : les fausses alertes passent de 1,4 à 0,5 %.
2. **Clarifier l'eau saisonnière** : décider, avec le mentor, si une rizière ou un réservoir saisonnier en eau mérite une alerte, et rendre les étiquettes cohérentes avec ce choix.
3. **Plus d'inondations, et plus variées** (WorldFloods, licence à vérifier) : 88 tuiles de 6 pays, c'est le point faible.
4. **Régler le seuil « inconnu »** selon la priorité : moins de fausses alertes, ou plus de détections. 3 inondations manquées sont à moins de 0,05 du seuil.
5. ~~Entraîner à 512 px~~ : fait, la pleine résolution aide les petites zones pour le double du temps.

## Limites connues

- 25 inondations en test : une tuile représente 4 points de rappel.
- Tous les incendies sont californiens, y compris en test.
- Le seuil « inconnu » est calibré sur 447 tuiles de validation (hors ambiguës), dont 15 inondations.
- Les étiquettes incendie v3 écartent les cicatrices de l'année de l'image et de l'année précédente connues de l'historique ; un brûlis plus ancien ou non répertorié peut encore rester dans une normale.
