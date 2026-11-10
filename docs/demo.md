# Démo : le Centre de veille

Une application locale qui montre le modèle au travail sur des images qu'il n'a jamais vues : une tuile Sentinel-2 en entrée, une passe, une décision, et ce qui l'explique. Elle tourne sur un ordinateur portable, sans GPU ni réseau.

## Lancer

```bash
uv sync --group demo
uv run --group demo python scripts/demo.py prepare
uv run --group demo python scripts/demo.py
```

La préparation, à faire une fois, copie en local les bibliothèques, la texture du globe, les polices et les contours des pays, puis construit le catalogue des tuiles et la banque de voisins (`data/demo/`). Elle demande le paquet de données (`data/pack/`), le lot « inconnu » (`data/unknown/`) et le run de référence (`runs/mobilenet_v3_small_512_v3/`, avec ses décisions sur le test et sur le lot « inconnu »). Le serveur ouvre ensuite le navigateur sur `http://127.0.0.1:8080`.

## Ce qu'on voit

| Zone | Contenu |
|---|---|
| Globe | Les 747 tuiles du test et les 16 du lot « inconnu », à leur position, colorées par la décision. Globe 3D animé (WebGL) ; repli sur un globe 2D si WebGL manque. Clic sur un point : analyse de la tuile |
| Tuile | Couleurs naturelles, infrarouge court ou proche infrarouge ; vérité terrain en contour ; carte « où le modèle regarde » |
| Décision | Badge avec son libellé, trois probabilités, vérité terrain et verdict, temps de la passe sur un cœur |
| Seuil « inconnu » | Curseur : toutes les décisions du globe et les indicateurs du test se recalculent en direct |
| Description | Texte généré à partir de mesures, sans modèle de langage (voir plus bas) |
| Cube | Les 6 bandes reçues par le modèle, empilées en 3D ; le survol les écarte |
| Journal | Les décisions de la séance, avec ✓ ou ✗ quand la vérité est connue |

**Passage satellite** (bouton ou barre d'espace) : la démo enchaîne 8 tuiles choisies dans `configs/demo.yaml`, avec une phrase de récit pour chacune. Une inondation et un incendie détectés, un piège d'eau évité, une ancienne cicatrice de feu, puis des échecs assumés : une petite inondation manquée, un désert pris pour du brûlé, une coulée de lave et un glissement de terrain déclarés normaux.

**Dépôt d'un GeoTIFF** : glisser un fichier sur la page (6 bandes B02, B03, B04, B08, B11, B12, ou une tuile Sentinel-2 complète de 12 ou 13 bandes, au moins 512 × 512 pixels, recadrée au centre).

## La description, sans modèle de langage

Chaque phrase vient d'une mesure (`onelook.demo.describe`) ; une mesure absente donne une phrase en moins, rien n'est inventé.

| Phrase | Mesure |
|---|---|
| Décision et confiance | Probabilités du modèle et seuil « inconnu » |
| Eau, eau inhabituelle | Indice NDWI, comparé à l'eau permanente connue (JRC) |
| Sol de type brûlé, végétation | Indices NBR et NDVI |
| Nuages | Carte de classification de scène (SCL) |
| Où le modèle regarde | Occlusion : chacune des 64 cases de la tuile est remplacée par la moyenne de l'image, et on mesure la baisse de confiance (64 passes, 1 à 2 s) |
| À quoi la tuile ressemble | Les 5 tuiles d'entraînement aux descripteurs les plus proches (774 tuiles en banque) |
| Tuile atypique | Distance de Mahalanobis au-delà de 95 % des tuiles du test |

Exemple, la coulée de lave de La Palma : le modèle répond « normal », et parmi les tuiles d'entraînement les plus proches figurent des pièges « roche volcanique » (laves anciennes de Lanzarote et d'Islande, étiquetées normales). La description montre ainsi pourquoi le modèle se trompe : pour lui, une lave fraîche ressemble à une lave ancienne.

## Architecture

| Fichier | Rôle |
|---|---|
| `scripts/demo.py` | Préparation (copie locale, catalogue, banque) et lancement |
| `src/onelook/demo/engine.py` | Passe ONNX chronométrée, occlusion, indices, voisins, distance de Mahalanobis |
| `src/onelook/demo/describe.py` | Mise en phrases des mesures |
| `src/onelook/demo/tiles.py` | Lecture des tuiles et des GeoTIFF déposés, rendu des vues |
| `src/onelook/demo/server.py` | Serveur local (FastAPI) |
| `src/onelook/demo/static/` | Page, style et script ; `vendor/` est rempli par la préparation et n'est pas versionné |

Le temps affiché est celui d'une passe sur un seul cœur ; il dépend de la charge de la machine (environ 15 ms sur un i7-10850H au repos).
