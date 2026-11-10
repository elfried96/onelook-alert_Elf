"""Description textuelle d'une décision, sans modèle de langage : des faits mesurés, mis en phrases.

Chaque phrase vient d'une mesure (probabilités, indices spectraux, carte SCL, eau permanente, occlusion,
voisins dans l'espace des descripteurs, distance de Mahalanobis). Rien n'est inventé : une mesure absente
donne une phrase en moins.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

NAMES = {"normal": "normal", "alerte_inondation": "alerte inondation", "alerte_incendie": "alerte incendie",
         "inconnu": "inconnu"}
CLASS_WORDS = {"normal": "normale", "alerte_inondation": "inondation", "alerte_incendie": "incendie"}
PLURALS = {"normal": "des tuiles normales", "alerte_inondation": "des inondations", "alerte_incendie": "des incendies"}
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]


@dataclass
class Facts:
    decision: str
    probs: dict[str, float]
    threshold: float
    date: str | None = None
    place: str | None = None
    lat: float | None = None
    lon: float | None = None
    water: float | None = None  # part de la tuile en eau (NDWI > 0, hors nuages)
    permanent_water: float | None = None  # part en eau permanente connue (JRC)
    vegetation: float | None = None  # NDVI > 0,4
    burn_like: float | None = None  # NBR < −0,1 hors eau
    cloud: float | None = None  # nuages et ombres (SCL)
    occlusion: np.ndarray | None = None  # baisse de confiance (points) quand on masque chaque case
    neighbours: list[dict] = field(default_factory=list)  # [{"label", "place"}], du plus proche au moins proche
    atypicity: float | None = None
    atypicity_limit: float | None = None


def pct(x: float) -> str:
    return f"{round(100 * x)} %"


def num(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def when(day: str) -> str:
    year, month, d = (int(v) for v in day.split("-"))
    return f"{'1er' if d == 1 else d} {MONTHS[month - 1]} {year}"


def coords(lat: float, lon: float) -> str:
    return f"{num(abs(lat), 1)}° {'N' if lat >= 0 else 'S'} · {num(abs(lon), 1)}° {'E' if lon >= 0 else 'O'}"


def region(drop: np.ndarray) -> str | None:
    """Zone de la tuile où masquer l'image fait le plus baisser la confiance (centre de gravité des baisses)."""
    weights = np.clip(drop, 0, None)
    if weights.sum() == 0:
        return None
    rows, cols = np.indices(drop.shape)
    y = (rows * weights).sum() / weights.sum() / (drop.shape[0] - 1)
    x = (cols * weights).sum() / weights.sum() / (drop.shape[1] - 1)
    vertical = "nord" if y < 0.4 else "sud" if y > 0.6 else ""
    horizontal = "ouest" if x < 0.4 else "est" if x > 0.6 else ""
    if not vertical and not horizontal:
        return "le centre de la tuile"
    if vertical and horizontal:
        return f"le {vertical}-{horizontal} de la tuile"
    return f"la moitié {vertical or horizontal}"


def confidence_words(p: float) -> str:
    return "très sûr de lui" if p >= 0.9 else "assez sûr" if p >= 0.75 else "hésitant"


def headline(f: Facts) -> str:
    best = max(f.probs, key=f.probs.get)
    p = f.probs[best]
    if f.decision == "inconnu":
        return (f"Inconnu : le modèle est trop peu sûr pour trancher (confiance {num(p)}, sous le seuil "
                f"{num(f.threshold)}). Il pencherait pour « {NAMES[best]} ».")
    return f"{NAMES[f.decision].capitalize()}, le modèle est {confidence_words(p)} (confiance {num(p)})."


def context(f: Facts) -> str | None:
    parts = []
    if f.date:
        parts.append(f"Image du {when(f.date)}")
    if f.place:
        parts.append(f.place)
    if f.lat is not None and f.lon is not None:
        parts.append(f"({coords(f.lat, f.lon)})")
    return " · ".join(parts) + ", 5,12 km de côté." if parts else None


def scene(f: Facts) -> list[str]:
    out = []
    if f.water is not None and f.water >= 0.01:
        line = f"De l'eau couvre {pct(f.water)} de la tuile (indice NDWI)"
        if f.permanent_water is not None:
            unusual = max(f.water - f.permanent_water, 0)
            if f.permanent_water < 0.01:
                line += ", et aucune eau permanente n'est connue ici : cette eau est inhabituelle"
            elif unusual < 0.03:
                line += f", presque entièrement de l'eau permanente connue ({pct(f.permanent_water)}) : rien d'inhabituel"
            else:
                line += (f", dont {pct(f.permanent_water)} d'eau permanente connue : environ {pct(unusual)} "
                         "d'eau inhabituelle")
        out.append(line + ".")
    elif f.water is not None:
        out.append("Presque pas d'eau visible.")
    if f.burn_like is not None and f.burn_like >= 0.02:
        out.append(f"Signature de sol brûlé ou très sec en infrarouge court (NBR bas) sur {pct(f.burn_like)} de la tuile.")
    if f.vegetation is not None and f.vegetation >= 0.01:
        out.append(f"Végétation dense sur {pct(f.vegetation)}.")
    if f.cloud is not None and f.cloud >= 0.02:
        out.append(f"{pct(f.cloud).capitalize()} de nuages et d'ombres.")
    return out


def attention(f: Facts) -> str | None:
    if f.occlusion is None:
        return None
    drop = f.occlusion
    if drop.max() < 1:
        return "Décision robuste : masquer n'importe quelle zone de l'image change la confiance de moins d'un point."
    if drop.max() < 3:
        points = "d'un point" if drop.max() < 1.5 else f"de {num(drop.max(), 0)} points"
        return f"Décision robuste : masquer une zone de l'image ne fait jamais baisser la confiance de plus {points}."
    where = region(drop)
    return (f"Le modèle s'appuie surtout sur {where} : y masquer l'image fait baisser sa confiance "
            f"jusqu'à {num(drop.max(), 0)} points.")


def resemblance(f: Facts) -> str | None:
    if not f.neighbours:
        return None
    labels = [n["label"] for n in f.neighbours]
    counts = {lab: labels.count(lab) for lab in dict.fromkeys(labels)}
    places = [n["place"] for n in f.neighbours if n["label"] == labels[0] and n.get("place")]
    top = f"{counts[labels[0]]} {CLASS_WORDS[labels[0]]}{'s' if counts[labels[0]] > 1 else ''}"
    where = f" ({', '.join(dict.fromkeys(places))})" if places else ""
    if len(counts) == 1:
        return f"Les {len(labels)} tuiles d'entraînement qui lui ressemblent le plus sont toutes {PLURALS[labels[0]]}{where}."
    others = ", ".join(f"{n} {CLASS_WORDS[lab]}{'s' if n > 1 else ''}" for lab, n in counts.items() if lab != labels[0])
    return f"Parmi les {len(labels)} tuiles d'entraînement les plus proches : {top}{where}, {others}."


def novelty(f: Facts) -> str | None:
    if f.atypicity is None or f.atypicity_limit is None:
        return None
    if f.atypicity > f.atypicity_limit:
        return (f"Tuile atypique : elle s'éloigne de ce que le modèle a vu à l'entraînement (distance de "
                f"Mahalanobis {num(f.atypicity, 0)}, au-delà de 95 % des tuiles de test) : décision à lire avec prudence.")
    return None


def second_choice(f: Facts) -> str | None:
    ranked = sorted(f.probs, key=f.probs.get, reverse=True)
    second = ranked[1]
    if f.probs[second] < 0.01:
        return None
    return f"Seconde hypothèse : {NAMES[second]}, {pct(f.probs[second])}."


def describe(f: Facts) -> dict:
    """Titre, contexte et liste de constats, prêts à afficher."""
    points = [*scene(f), attention(f), resemblance(f), novelty(f), second_choice(f)]
    return {"titre": headline(f), "contexte": context(f), "constats": [p for p in points if p]}
