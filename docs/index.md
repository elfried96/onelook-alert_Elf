# One Look

<p class="ol-lead">Un modèle d'IA léger, capable de tourner à bord d'un satellite, qui regarde une image une seule fois et décide si elle mérite une alerte.</p>

## Une image, quatre décisions

| Décision | Signification |
|---|---|
| <span class="ol-badge ol-badge--normal">Normal</span> | Rien à signaler, y compris les nuages, les rivières, les lacs et les champs. |
| <span class="ol-badge ol-badge--alert">Alerte · inondation</span> | Une part importante de l'image est inondée. |
| <span class="ol-badge ol-badge--alert">Alerte · incendie</span> | Une part importante de l'image a brûlé récemment. |
| <span class="ol-badge ol-badge--unknown">Inconnu</span> | L'image ne ressemble à rien de ce que le modèle connaît. Elle est envoyée au sol pour vérification. |

## Pourquoi c'est utile

Les satellites produisent plus d'images qu'on ne peut en envoyer au sol. Un modèle embarqué qui trie les images à bord permet de transmettre d'abord celles qui comptent. Il doit pour cela tenir dans peu de mémoire, répondre vite et ne pas alerter pour rien.

## Ce que le projet évalue

- **Qualité des alertes** : précision et rappel, avec un protocole documenté.
- **Fausses alertes** : taux d'alertes sur des images normales.
- **L'inconnu** : capacité à signaler ce que le modèle n'a jamais vu.
- **Embarquabilité** : taille du modèle en Mo et temps d'inférence en ms.
- **Cas d'échec** : analyse des erreurs.

## Le projet en bref

| | |
|---|---|
| Cadre | Piscine Intelligence Lab · Makers, projet individuel |
| Période | 16 octobre → 16 novembre 2026 |
| Données | Images Sentinel-2, GeoTIFF 512 × 512 pixels |
| Anomalies | Inondations et incendies |
| Outils | Python, PyTorch, TorchGeo, ONNX Runtime |
| Code | [elfried96/onelook-alert_Elf](https://github.com/elfried96/onelook-alert_Elf) |
