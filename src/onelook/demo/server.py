"""Serveur local du Centre de veille : la page, les images des tuiles et l'analyse à la demande."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from onelook.demo.engine import Engine
from onelook.demo.tiles import read_pack_tile, read_unknown_tile, read_upload, render

STATIC = Path(__file__).parent / "static"


def create_app(run: Path, data: Path, pack: Path, unknown: Path, passage: list[dict]) -> FastAPI:
    engine = Engine(run, bank=data / "bank.npz")
    catalog = {row["id"]: row for row in json.loads((data / "catalog.json").read_text())}
    paths = {}
    index = pd.read_csv(pack / "index.csv")
    for r in index[index["split"] == "test"].itertuples():
        paths[r.id] = ("pack", pack / r.path)
    for tile_id, row in catalog.items():
        if row["partie"] == "inconnu":
            paths[tile_id] = ("inconnu", unknown / f"{tile_id}.tif")
    uploads: dict[str, dict] = {}
    evaluation = json.loads((run / "eval_test_model.json").read_text())

    @lru_cache(maxsize=48)
    def load(tile_id: str) -> dict:
        if tile_id in uploads:
            return uploads[tile_id]["tile"]
        if tile_id not in paths:
            raise HTTPException(404, f"Tuile inconnue : {tile_id}")
        kind, path = paths[tile_id]
        return read_pack_tile(path) if kind == "pack" else read_unknown_tile(path)

    def meta_of(tile_id: str) -> dict:
        row = uploads[tile_id]["meta"] if tile_id in uploads else catalog[tile_id]
        return {"date": row.get("date"), "place": row.get("lieu"), "lat": row.get("lat"), "lon": row.get("lon")}

    app = FastAPI(title="One Look · Centre de veille")

    @app.middleware("http")
    async def revalidate(request, call_next):
        # La page et ses scripts changent pendant la mise au point : le navigateur revalide à chaque chargement
        response = await call_next(request)
        if not request.url.path.startswith(("/api/", "/vendor/")):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/meta")
    def meta() -> dict:
        return {"modele": engine.config["arch"].replace("_", " "), "taille_mo": round(engine.size_mb, 1),
                "seuil": engine.threshold, "classes": engine.config["classes"], "test": evaluation,
                "passage": passage, "limite_atypique": engine.bank_meta["limite_atypique"] if engine.bank else None}

    @app.get("/api/catalog")
    def get_catalog() -> list[dict]:
        return list(catalog.values())

    @app.get("/api/tile/{tile_id}/{view}")
    def tile_view(tile_id: str, view: str) -> Response:
        try:
            content, media = render(load(tile_id), view)
        except KeyError:
            raise HTTPException(404, f"Vue inconnue : {view}") from None
        return Response(content, media_type=media, headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/analyse/{tile_id}")
    def analyse(tile_id: str) -> dict:
        tile = load(tile_id)
        result = engine.analyse(tile["image"], tile["scl"], tile["water"], meta_of(tile_id))
        row = uploads[tile_id]["meta"] if tile_id in uploads else catalog[tile_id]
        return {"id": tile_id, "tuile": row, **result}

    @app.post("/api/depot")
    async def depot(file: UploadFile = File(...)) -> dict:
        try:
            tile, meta = read_upload(await file.read())
        except Exception as exc:  # message lisible pour la page
            raise HTTPException(400, str(exc)) from None
        tile_id = f"depot_{len(uploads) + 1}"
        row = {"id": tile_id, "partie": "depot", "verite": None, "lieu": file.filename, "date": None,
               "categorie": "dépôt", **meta}
        uploads[tile_id] = {"tile": tile, "meta": row}
        return row

    @app.get("/")
    def index_page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/", StaticFiles(directory=STATIC), name="static")
    return app
