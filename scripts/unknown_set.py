"""Lot « inconnu » : tuiles de phénomènes jamais vus (configs/unknown_events.yaml), et réponse du modèle.

Étapes :
    uv run python scripts/unknown_set.py download             # tuiles L2A dans data/unknown/
    uv run python scripts/unknown_set.py evaluate runs/<nom>  # décisions_unknown_model.csv dans le run
    uv run python scripts/unknown_set.py sheet runs/<nom>     # planche docs/assets/figures/inconnu_*.jpg
Réponse attendue partout : « inconnu ». Ces tuiles ne servent jamais à l'entraînement ni au calibrage.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
import rasterio
import yaml

from onelook.data import build, l2a
from onelook.data.labels import CLASSES
from onelook.data.sentinel2 import BANDS_L2A, SELECTED_BANDS
from onelook.ood.confidence import decisions, softmax

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "unknown_events.yaml"
OUT = ROOT / "data" / "unknown"
FIGURES = ROOT / "docs" / "assets" / "figures"
MAX_CLOUD = 0.10  # au-delà, on garde quand même le passage le moins nuageux trouvé


def events() -> list[dict]:
    return yaml.safe_load(CONFIG.read_text())["events"]


def download_event(event: dict) -> dict:
    """Passage le plus dégagé de la fenêtre : le premier sous MAX_CLOUD, sinon le moins nuageux essayé."""
    grid = l2a.Grid.centered(event["lon"], event["lat"])
    start, end = date.fromisoformat(str(event["start"])), date.fromisoformat(str(event["end"]))
    best = None
    for items in l2a.search_period(grid, start, end, max_cloud=80)[:build.MAX_TRIES]:
        image, scl, used = l2a.read_tile(items, grid)
        frac = l2a.scl_fractions(scl)
        if frac["no_data"] > build.MAX_NO_DATA:
            continue
        if best is None or frac["cloud"] < best[2]["cloud"]:
            best = (image, scl, frac, used, items[0].datetime.date())
        if frac["cloud"] <= MAX_CLOUD:
            break
    if best is None:
        return {"id": event["name"], "error": "aucun passage satisfaisant"}
    image, scl, frac, used, day = best
    l2a.write_tile(OUT / f"{event['name']}.tif", image, grid, scl=scl)
    return {"id": event["name"], "category": event["category"], "date": day.isoformat(), "scenes": used,
            "lat": event["lat"], "lon": event["lon"], "cloud": round(frac["cloud"], 3),
            "no_data": round(frac["no_data"], 3), "note": event.get("note", "")}


def download() -> None:
    log = OUT / "unknown.jsonl"
    done = build.done_ids(log)
    for event in events():
        if event["name"] in done:
            continue
        try:
            row = download_event(event)
        except Exception as exc:  # un événement en échec ne bloque pas les autres
            row = {"id": event["name"], "error": str(exc)[:300]}
        build.append_row(log, row)
        print(row["id"], row.get("date", row.get("error")), f"nuages {row.get('cloud', '–')}", flush=True)


def tiles() -> pd.DataFrame:
    rows = [json.loads(line) for line in (OUT / "unknown.jsonl").read_text().splitlines() if line.strip()]
    df = pd.DataFrame(rows)
    if "error" in df:
        df = df[df["error"].isna()]
    order = {e["name"]: i for i, e in enumerate(events())}
    df = df.drop_duplicates("id", keep="last")
    df = df[df["id"].isin(order)].sort_values("id", key=lambda s: s.map(order)).reset_index(drop=True)
    df["visible"] = df["id"].map({e["name"]: e.get("visible", "?") for e in events()})
    return df


def read_image(tile_id: str) -> np.ndarray:
    """Les 6 bandes du modèle, en réflectance, comme read_packed."""
    with rasterio.open(OUT / f"{tile_id}.tif") as src:
        return src.read([BANDS_L2A.index(b) + 1 for b in SELECTED_BANDS]).astype(np.float32) / 10000


def evaluate(run: Path, model: str) -> pd.DataFrame:
    config = json.loads((run / "config.json").read_text())
    session = ort.InferenceSession(str(run / model), providers=["CPUExecutionProvider"])
    df = tiles()
    logits = np.concatenate([session.run(None, {"image": read_image(t)[None]})[0] for t in df["id"]])
    probs = softmax(logits)
    df["decision"] = decisions(probs, config["seuil_inconnu"])
    df["confiance"] = probs.max(axis=1)
    for i, c in enumerate(CLASSES):
        df[f"p_{c}"] = probs[:, i]
    df.to_csv(run / f"decisions_unknown_{Path(model).stem}.csv", index=False)
    print(f"Seuil « inconnu » : {config['seuil_inconnu']:.3f}\n")
    print(df[["id", "category", "date", "cloud", "visible", "decision", "confiance"]].to_string(index=False))
    seen = df[df["visible"] == "oui"]
    print(f"\nPhénomène visible ({len(seen)} tuiles) :\n", pd.crosstab(seen["category"], seen["decision"]))
    return df


def sheet(run: Path, model: str, prefix: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from failure_figures import stretch

    df = pd.read_csv(run / f"decisions_unknown_{Path(model).stem}.csv")
    names = {"normal": "normal", "alerte_inondation": "alerte inondation", "alerte_incendie": "alerte incendie",
             "inconnu": "inconnu"}
    for category, rows in df.groupby("category", sort=False):
        cols = len(rows)
        fig, axes = plt.subplots(2, cols, figsize=(3.2 * cols, 6.6), squeeze=False)
        for c, row in enumerate(rows.itertuples()):
            image = read_image(row.id)
            natural = stretch(np.dstack([image[2], image[1], image[0]]))
            swir = stretch(np.dstack([image[5], image[3], image[2]]))
            for r, img in enumerate((natural, swir)):
                axes[r, c].imshow(img)
                axes[r, c].set_xticks([])
                axes[r, c].set_yticks([])
                for s in axes[r, c].spines.values():
                    s.set_visible(False)
            axes[0, c].set_title(f"{row.id}\n{row.date} → {names[row.decision]} ({row.confiance:.2f})", fontsize=8)
            axes[1, c].set_title("infrarouge court", fontsize=7, color="#4f5f6b")
        fig.tight_layout()
        out = FIGURES / f"{prefix}_{category}.jpg"
        fig.savefig(out, dpi=55, bbox_inches="tight", pil_kwargs={"quality": 82})
        plt.close(fig)
        print(f"{out.name} : {cols} tuiles")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["download", "evaluate", "sheet"])
    parser.add_argument("run", type=Path, nargs="?", help="Dossier runs/<nom> (evaluate, sheet)")
    parser.add_argument("--model", default="model.onnx")
    parser.add_argument("--prefix", default="inconnu")
    args = parser.parse_args()
    if args.stage == "download":
        download()
    elif args.run is None:
        parser.error("evaluate et sheet demandent un dossier runs/<nom>")
    elif args.stage == "evaluate":
        evaluate(args.run, args.model)
    else:
        sheet(args.run, args.model, args.prefix)


if __name__ == "__main__":
    main()
