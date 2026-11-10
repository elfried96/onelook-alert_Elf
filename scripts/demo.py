"""Centre de veille One Look : préparation et lancement de la démo locale.

    uv run --group demo python scripts/demo.py prepare   # une fois : bibliothèques, catalogue, banque de voisins
    uv run --group demo python scripts/demo.py           # lance le serveur et ouvre le navigateur

« prepare » copie en local tout ce que la page charge (bibliothèques, textures, polices, contours des pays) :
la démo tourne ensuite sans internet. Les fichiers produits (static/vendor, data/demo) ne sont pas versionnés.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import webbrowser
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml
from matplotlib.path import Path as Polygon
from tqdm import tqdm

from onelook.data.labels import CLASSES
from onelook.demo.engine import Engine
from onelook.demo.tiles import read_pack_tile, read_unknown_tile
from onelook.evaluation.metrics import WATER_TRAPS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "onelook" / "demo" / "static"
VENDOR = STATIC / "vendor"
DATA = ROOT / "data" / "demo"
PACK = ROOT / "data" / "pack"
UNKNOWN = ROOT / "data" / "unknown"
CONFIG = ROOT / "configs" / "demo.yaml"
COUNTRIES = ROOT / "data" / "raw" / "naturalearth" / "ne_50m_admin_0_countries.geojson"

# Versions figées ; tout est copié en local par « prepare »
ASSETS = {
    "globe.gl.min.js": "https://cdn.jsdelivr.net/npm/globe.gl@2.27.2/dist/globe.gl.min.js",
    "d3.min.js": "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js",
    "topojson-client.min.js": "https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js",
    "countries-110m.json": "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json",
    "earth-night.jpg": "https://cdn.jsdelivr.net/npm/three-globe@2.30.0/example/img/earth-night.jpg",
    "earth-topology.png": "https://cdn.jsdelivr.net/npm/three-globe@2.30.0/example/img/earth-topology.png",
}
FONTS = ("https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700"
         "&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap")
COUNTRIES_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
                 "ne_50m_admin_0_countries.geojson")
FLOOD_COUNTRIES = {"Bolivia": "Bolivie", "Ghana": "Ghana", "India": "Inde", "Mekong": "Mékong", "Nigeria": "Nigeria",
                   "Pakistan": "Pakistan", "Paraguay": "Paraguay", "Somalia": "Somalie", "Spain": "Espagne",
                   "Sri-Lanka": "Sri Lanka", "USA": "États-Unis"}


def download(url: str, out: Path, headers: dict | None = None) -> None:
    if out.exists():
        return
    response = requests.get(url, headers=headers or {}, timeout=120)
    response.raise_for_status()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(response.content)


def vendor() -> None:
    for name, url in ASSETS.items():
        download(url, VENDOR / name)
    css_path = VENDOR / "fonts.css"
    if not css_path.exists():
        browser = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
        css = requests.get(FONTS, headers=browser, timeout=60).text
        for i, url in enumerate(dict.fromkeys(re.findall(r"url\((https://[^)]+\.woff2)\)", css))):
            download(url, VENDOR / "fonts" / f"{i}.woff2")
            css = css.replace(url, f"fonts/{i}.woff2")
        css_path.write_text(css)
    download(COUNTRIES_URL, COUNTRIES)
    print(f"Bibliothèques, textures et polices copiées dans {VENDOR.relative_to(ROOT)}")


class Places:
    """Nom du pays (en français) d'un point, d'après les contours Natural Earth au 1:50 millions."""

    def __init__(self, path: Path):
        self.shapes = []
        for feature in json.loads(path.read_text())["features"]:
            name = feature["properties"].get("NAME_FR") or feature["properties"]["NAME"]
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            for polygon in polygons:
                ring = np.asarray(polygon[0])
                self.shapes.append((name, (*ring.min(0), *ring.max(0)), Polygon(ring)))

    def __call__(self, lon: float, lat: float) -> str:
        for name, (x0, y0, x1, y1), shape in self.shapes:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and shape.contains_point((lon, lat)):
                return name
        best = min(self.shapes, key=lambda s: np.abs(s[2].vertices - (lon, lat)).sum(axis=1).min())
        return f"au large · {best[0]}"


def place_of(row, places: Places) -> str:
    if str(row.source).startswith("cabuar"):
        return "Californie, États-Unis"
    if row.source == "sen1floods11":
        return FLOOD_COUNTRIES.get(row.id.rsplit("_", 1)[0], places(row.lon, row.lat))
    return places(row.lon, row.lat)


def bank_place(row) -> str:
    if row.source == "sen1floods11":
        return FLOOD_COUNTRIES.get(row.id.rsplit("_", 1)[0], "")
    if str(row.source).startswith("cabuar"):
        return "Californie"
    return {"aleatoire": "paysage au hasard"}.get(row.category, str(row.category).replace("_", " "))


def catalog(run: Path, places: Places) -> list[dict]:
    index = pd.read_csv(PACK / "index.csv")
    test = index[index["split"] == "test"]
    probs = pd.read_csv(run / "decisions_test_model.csv").drop(columns="label")
    test = test.merge(probs, on="id")
    rows = []
    for r in test.itertuples():
        rows.append({"id": r.id, "lon": round(r.lon, 4), "lat": round(r.lat, 4), "partie": "test", "verite": r.label,
                     "categorie": r.category, "source": r.source, "date": str(r.date), "lieu": place_of(r, places),
                     "inondation": round(float(r.frac_flood), 3) if pd.notna(r.frac_flood) else 0,
                     "brule": round(float(r.frac_burned), 3) if pd.notna(r.frac_burned) else 0,
                     "piege_eau": r.category in WATER_TRAPS, "probs": [round(float(getattr(r, f"p_{c}")), 4) for c in CLASSES]})
    unknown = pd.read_csv(run / "decisions_unknown_model.csv")
    for r in unknown.itertuples():
        rows.append({"id": r.id, "lon": r.lon, "lat": r.lat, "partie": "inconnu", "verite": "inconnu",
                     "categorie": r.category, "source": "lot_inconnu", "date": r.date, "lieu": places(r.lon, r.lat),
                     "note": r.note, "visible": r.visible, "inondation": 0, "brule": 0, "piege_eau": False,
                     "probs": [round(float(getattr(r, f"p_{c}")), 4) for c in CLASSES]})
    return rows


def bank(engine: Engine, normals: int = 400) -> None:
    """Descripteurs de tuiles d'entraînement (voisins), nuages par classe et limite d'atypicité (test)."""
    index = pd.read_csv(PACK / "index.csv")
    train = index[(index["split"] == "train") & index["label"].isin(CLASSES)]
    train = pd.concat([train[train["label"] != "normal"],
                       train[train["label"] == "normal"].sample(normals, random_state=0)])
    feats = np.stack([engine.forward(read_pack_tile(PACK / p)["image"])[1]
                      for p in tqdm(train["path"], desc="Banque (entraînement)")])
    labels = train["label"].to_numpy()
    means = np.stack([feats[labels == c].mean(0) for c in CLASSES])
    centred = np.concatenate([feats[labels == c] - means[i] for i, c in enumerate(CLASSES)])
    precision = np.linalg.inv(np.cov(centred.T) + 0.1 * np.eye(feats.shape[1]))
    test = index[(index["split"] == "test") & index["label"].isin(CLASSES)]
    test_feats = np.stack([engine.forward(read_pack_tile(PACK / p)["image"])[1]
                           for p in tqdm(test["path"], desc="Limite (test)")])
    dist = np.min([np.einsum("ij,jk,ik->i", test_feats - m, precision, test_feats - m) for m in means], axis=0)
    meta = {"limite_atypique": float(np.quantile(dist, 0.95)), "tuiles": len(train)}
    DATA.mkdir(parents=True, exist_ok=True)
    np.savez(DATA / "bank.npz", features=feats.astype(np.float32), labels=labels.astype(str),
             ids=train["id"].to_numpy().astype(str), places=np.array([bank_place(r) for r in train.itertuples()]),
             means=means.astype(np.float32), precision=precision.astype(np.float32), meta=np.array(json.dumps(meta)))
    print(f"Banque : {len(train)} tuiles d'entraînement, limite d'atypicité {meta['limite_atypique']:.0f}")


def prepare() -> None:
    vendor()
    config = yaml.safe_load(CONFIG.read_text())
    run = ROOT / config["run"]
    rows = catalog(run, Places(COUNTRIES))
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "catalog.json").write_text(json.dumps(rows, ensure_ascii=False))
    print(f"Catalogue : {len(rows)} tuiles")
    bank(Engine(run))


def serve(port: int, open_browser: bool) -> None:
    import uvicorn

    from onelook.demo.server import create_app

    if not (DATA / "catalog.json").exists() or not (VENDOR / "globe.gl.min.js").exists():
        raise SystemExit("Lancer d'abord : uv run --group demo python scripts/demo.py prepare")
    config = yaml.safe_load(CONFIG.read_text())
    app = create_app(ROOT / config["run"], DATA, PACK, UNKNOWN, config["passage"])
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"Centre de veille One Look : {url}  (Ctrl+C pour arrêter)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", default="serve", choices=["prepare", "serve"])
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    prepare() if args.action == "prepare" else serve(args.port, not args.no_browser)


if __name__ == "__main__":
    main()
