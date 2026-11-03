"""Produit les figures de la documentation à partir du jeu de données local.

Usage : uv run python scripts/make_figures.py
Écrit dans docs/assets/figures/ (versionné : ce sont des illustrations légères, pas des données).
Prérequis : le jeu complet (scripts/build_dataset.py) et l'échantillon (scripts/download_samples.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import hdf5plugin  # noqa: F401  (filtres de compression du fichier CaBuAr)
import matplotlib
import numpy as np
import pandas as pd
import rasterio

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from onelook.data import sources  # noqa: E402
from onelook.data.sentinel2 import (  # noqa: E402
    BANDS_L2A, composite, false_color_infrared, false_color_swir, get_bands, natural_color, nbr, ndwi,
)
from onelook.data.water import permanent_water  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "dataset"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "assets" / "figures"
NATURAL_EARTH = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson"

# Jetons du Design System One Look (docs/stylesheets/onelook.css)
INK, INK_MUTED, LINE, SURFACE = "#14202b", "#4f5f6b", "#cfd8db", "#ffffff"
LABEL_COLORS = {"normal": "#2b7253", "alerte_inondation": "#1d5f96", "alerte_incendie": "#a3470a", "ambigu": "#8a969e"}
LABEL_NAMES = {"normal": "Normal", "alerte_inondation": "Alerte · inondation",
               "alerte_incendie": "Alerte · incendie", "ambigu": "Ambiguë (écartée)"}
# Palette catégorielle de référence (ordre fixe) pour les parties
SPLIT_COLORS = {"train": "#2a78d6", "val": "#eb6834", "test": "#1baf7a"}
SPLIT_NAMES = {"train": "Entraînement", "val": "Validation", "test": "Test"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
WAVELENGTH_NM = {"B01": 443, "B02": 490, "B03": 560, "B04": 665, "B05": 705, "B06": 740, "B07": 783,
                 "B08": 842, "B8A": 865, "B09": 945, "B11": 1610, "B12": 2190}

plt.rcParams.update({
    "font.size": 10, "text.color": INK, "axes.labelcolor": INK_MUTED, "axes.edgecolor": LINE,
    "xtick.color": INK_MUTED, "ytick.color": INK_MUTED, "axes.titlesize": 10, "axes.titlecolor": INK,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.grid": False,
})


def origin(row) -> str:
    """Provenance lisible d'une tuile (la catégorie brute « incendie » couvre aussi les quarts non brûlés)."""
    names = {"sen1floods11": "Sen1Floods11", "cabuar": "CaBuAr", "cabuar_avant_feu": "CaBuAr avant feu",
             "aleatoire": "point au hasard"}
    return names.get(row.source, row.category.replace("_", " "))


def clearest(index: pd.DataFrame, site: str):
    """L'année la moins nuageuse d'un site du catalogue."""
    return index[index.id.str.startswith(site + "_")].sort_values(["scl_cloud", "id"]).iloc[0]


def read(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read()


def tile(row) -> dict:
    """Image et couches d'une ligne de l'index (Series ou tuple de itertuples)."""
    row = row._asdict() if hasattr(row, "_asdict") else row.to_dict()  # Series.mask est une méthode
    image = DATASET / row["image"]
    stem = image.with_name(image.stem)
    layers = {"image": read(image), "scl": read(Path(f"{stem}_SCL.tif"))[0]}
    if Path(f"{stem}_water.tif").exists():
        layers["water"] = read(Path(f"{stem}_water.tif"))[0]
    if isinstance(row["mask"], str):
        layers["mask"] = read(DATASET / row["mask"])[0]
    return layers


def overlay(rgb: np.ndarray, mask: np.ndarray, color: str, alpha: float = 0.55) -> np.ndarray:
    out = rgb.copy()
    out[mask] = (1 - alpha) * out[mask] + alpha * np.array(matplotlib.colors.to_rgb(color))
    return out


def save(fig, name: str, **kwargs) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    options = {"pil_kwargs": {"quality": 85}} if name.endswith(".jpg") else {}
    fig.savefig(path, bbox_inches="tight", **options, **kwargs)
    plt.close(fig)
    print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} Ko")


def hide_axes(axes) -> None:
    for ax in np.ravel(axes):
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)


# --- Lire une image Sentinel-2 -------------------------------------------------

def fig_reading(index: pd.DataFrame) -> None:
    """Une tuile d'inondation et une tuile d'incendie vues de six façons."""
    flood = tile(index.set_index("id").loc[["Bolivia_129334"]].reset_index().iloc[0])
    fire_row = index[(index.source == "cabuar") & index.frac_burned.between(0.35, 0.6)].sort_values("id").iloc[0]
    fire = tile(fire_row)
    fig, axes = plt.subplots(2, 6, figsize=(15, 5.6))
    for r, (t, name) in enumerate([(flood, "Inondation (Bolivie)"), (fire, "Incendie (Californie)")]):
        img = t["image"]
        mask = t["mask"] == 3 if r == 0 else t["mask"] > 0
        panels = [
            (natural_color(img), "Couleurs naturelles\nB04 · B03 · B02"),
            (false_color_infrared(img), "Infrarouge\nB08 · B04 · B03"),
            (false_color_swir(img), "Infrarouge court\nB12 · B08 · B04"),
            (ndwi(img), "NDWI (eau)\nclair = eau"),
            (nbr(img), "NBR (brûlé)\nsombre = brûlé ou eau"),
            (overlay(natural_color(img), mask, "#1d5f96" if r == 0 else "#a3470a", 0.7),
             "Vérité terrain\n" + ("eau d'inondation" if r == 0 else "zone brûlée")),
        ]
        for c, (data, title) in enumerate(panels):
            ax = axes[r, c]
            if data.ndim == 2:
                ax.imshow(data, cmap="gray", vmin=-0.6, vmax=0.6)
            else:
                ax.imshow(data)
            ax.set_title(title, fontsize=9)
        axes[r, 0].set_ylabel(name, fontsize=10, color=INK)
    hide_axes(axes)
    fig.tight_layout()
    save(fig, "lire_une_image.jpg", dpi=70)


def fig_spectra(index: pd.DataFrame) -> None:
    """Signature spectrale médiane de cinq surfaces, d'après les masques."""
    rng = np.random.default_rng(0)
    groups = {"Eau d'inondation": [], "Eau permanente": [], "Terre sèche (inondations)": [],
              "Sol brûlé": [], "Terrain non brûlé (Californie)": []}
    floods = index[(index.source == "sen1floods11") & (index.frac_flood > 0.1)].sample(40, random_state=0)
    fires = index[(index.source == "cabuar") & index.frac_burned.between(0.2, 0.8)].sample(40, random_state=0)
    for rows, kind in ((floods, "flood"), (fires, "fire")):
        for row in rows.itertuples():
            t = tile(row)
            pixels = t["image"].reshape(len(BANDS_L2A), -1)
            mask = t["mask"].ravel()
            cases = ({"Eau d'inondation": 3, "Eau permanente": 2, "Terre sèche (inondations)": 1} if kind == "flood"
                     else {"Sol brûlé": 1, "Terrain non brûlé (Californie)": 0})
            for name, code in cases.items():
                where = np.nonzero(mask == code)[0]
                if len(where):
                    groups[name].append(pixels[:, rng.choice(where, min(500, len(where)), replace=False)])
    x = [WAVELENGTH_NM[b] for b in BANDS_L2A]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for color, (name, chunks) in zip(SERIES, groups.items()):
        median = np.median(np.concatenate(chunks, axis=1), axis=1) / 10000
        ax.plot(x, median, color=color, lw=2, marker="o", ms=4, label=name)
    for band, nm in WAVELENGTH_NM.items():
        if band in ("B03", "B04", "B08", "B11", "B12"):
            ax.axvline(nm, color=LINE, lw=0.8, zorder=0)
            ax.text(nm, 1.0, band, transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                    fontsize=8, color=INK_MUTED)
    ax.set_xlabel("Longueur d'onde (nm)")
    ax.set_ylabel("Réflectance de surface (médiane)")
    ax.set_xlim(400, 2300)
    ax.set_ylim(0, None)
    ax.yaxis.grid(True, color=LINE, lw=0.6)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", bbox_to_anchor=(1.01, 1))
    save(fig, "signatures_spectrales.png", dpi=110)


# --- Harmonisation ---------------------------------------------------------------

def fig_harmonization(index: pd.DataFrame) -> None:
    """Même lieu, même date : L1C d'origine (Sen1Floods11) contre L2A relu sur Planetary Computer."""
    tile_id = "Mekong_1248200"
    l1c = read(RAW / "sen1floods11" / "S2Hand" / f"{tile_id}_S2Hand.tif").astype(float)
    l2a = tile(index.set_index("id").loc[[tile_id]].reset_index().iloc[0])["image"].astype(float)
    fixed = lambda img: np.clip(np.transpose(get_bands(img, ["B04", "B03", "B02"]), (1, 2, 0)) / 0.25, 0, 1)  # noqa: E731
    fig = plt.figure(figsize=(13, 4.2))
    grid = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.6])
    for i, (img, title) in enumerate([(l1c, "L1C (Sen1Floods11 d'origine)\nhaut de l'atmosphère"),
                                      (l2a, "L2A (relu, Planetary Computer)\nréflectance de surface")]):
        ax = fig.add_subplot(grid[0, i])
        ax.imshow(fixed(img))
        ax.set_title(title, fontsize=9)
        hide_axes(ax)
    ax = fig.add_subplot(grid[0, 2])
    bands = ["B02", "B03", "B04", "B08", "B11", "B12"]
    for img, name, color in ((l1c, "L1C", SERIES[0]), (l2a, "L2A", SERIES[1])):
        values = np.median(get_bands(img, bands).reshape(len(bands), -1), axis=1)
        ax.plot(bands, values, color=color, lw=2, marker="o", ms=5, label=name)
        ax.annotate(name, (len(bands) - 1, values[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9)
    ax.set_title("Réflectance médiane de la tuile, par bande", fontsize=9)
    ax.set_ylim(0, None)
    ax.yaxis.grid(True, color=LINE, lw=0.6)
    ax.legend(frameon=False, fontsize=9)
    fig.text(0.01, -0.02, "Même étirement des couleurs pour les deux images : le voile bleuté du L1C vient de "
             "l'atmosphère, que le L2A retire.", fontsize=8.5, color=INK_MUTED)
    save(fig, "harmonisation_l1c_l2a.jpg", dpi=80)


def fig_cabuar_location(index: pd.DataFrame) -> None:
    """Tuile CaBuAr d'origine (20 m, sans coordonnées) et sa position retrouvée en L2A à 10 m."""
    patches = index[index.source == "cabuar"].groupby("cabuar_key").agg(n=("id", "size"), burned=("frac_burned", "mean"))
    keys = patches[(patches.n == 4) & patches.burned.between(0.2, 0.5)].index.sort_values()
    picks = [keys[0], keys[len(keys) // 2]]
    fig, axes = plt.subplots(len(picks), 3, figsize=(11, 3.8 * len(picks)))
    with h5py.File(RAW / "cabuar" / "512x512.hdf5", "r") as h5:
        for r, key in enumerate(picks):
            original = np.transpose(h5[key]["post_fire"][...], (2, 0, 1))
            mosaic = np.zeros((len(BANDS_L2A), 1024, 1024), dtype=np.uint16)
            mask = np.zeros((1024, 1024), dtype=bool)
            for qi, (y, x) in enumerate([(0, 0), (0, 512), (512, 0), (512, 512)]):
                t = tile(index[index.id == f"{key}_q{qi}"].iloc[0])
                mosaic[:, y:y + 512, x:x + 512] = t["image"]
                mask[y:y + 512, x:x + 512] = t["mask"] > 0
            score = index[index.cabuar_key == key].cabuar_match.iloc[0]
            panels = [(natural_color(original), "CaBuAr d'origine\n512 × 512 à 20 m, sans coordonnées"),
                      (natural_color(mosaic), f"Retrouvée en L2A à 10 m\ncorrélation {score:.3f}"),
                      (overlay(natural_color(mosaic), mask, "#a3470a", 0.6), "Masque reporté\n→ 4 tuiles 512 × 512")]
            for c, (data, title) in enumerate(panels):
                axes[r, c].imshow(data)
                axes[r, c].set_title(title, fontsize=9)
            for v in (512,):
                axes[r, 2].axhline(v, color="white", lw=1)
                axes[r, 2].axvline(v, color="white", lw=1)
    hide_axes(axes)
    fig.tight_layout()
    save(fig, "cabuar_position.jpg", dpi=70)


# --- Étiquettes et découpage -------------------------------------------------------

def fig_examples(index: pd.DataFrame) -> None:
    """Exemples de chaque décision attendue, avec la vérité terrain en surimpression."""
    fig, axes = plt.subplots(4, 5, figsize=(14, 12.2))
    for r, label in enumerate(LABEL_NAMES):
        rows = index[index.label == label]
        if label == "normal":
            rows = rows[rows.source.isin(["catalogue", "aleatoire", "cabuar"])]
        for c, row in enumerate(rows.sample(5, random_state=3).itertuples()):
            t = tile(row)
            rgb = natural_color(t["image"])
            if "mask" in t:
                hit = t["mask"] == 3 if row.source == "sen1floods11" else t["mask"] > 0
                color = "#1d5f96" if row.source == "sen1floods11" else "#a3470a"
                rgb = overlay(rgb, hit, color, 0.5)
            ax = axes[r, c]
            ax.imshow(rgb)
            share = row.frac_flood * row.frac_valid if row.source == "sen1floods11" else row.frac_burned
            ax.set_title(f"{SPLIT_NAMES[row.split]} · {origin(row)}\nanomalie {share:.1%}", fontsize=8.5)
        axes[r, 0].set_ylabel(LABEL_NAMES[label], fontsize=11, color=LABEL_COLORS[label], fontweight="bold")
    hide_axes(axes)
    fig.tight_layout()
    save(fig, "exemples_decisions.jpg", dpi=60)


def fig_traps(index: pd.DataFrame) -> None:
    """Pièges : ressemblent à une anomalie, mais sont normaux."""
    cases = [("golfe_bengale_ocean", "Océan"), ("niger_niamey_fleuve", "Fleuve"), ("volta_reservoir", "Réservoir"),
             ("mekong_rizieres", "Rizières"), ("hooghly_estuaire", "Estuaire turbide"), ("alpes_neige", "Neige"),
             ("gabon_nuages", "Nuages"), ("lanzarote_lave", "Lave sombre"), ("ukraine_labours", "Labours sombres"),
             ("everest_relief", "Ombres de relief"), ("paris_ville", "Ville"), ("uyuni_salar", "Salar")]
    fig, axes = plt.subplots(2, 6, figsize=(15, 5.8))
    for ax, (site, name) in zip(axes.ravel(), cases):
        row = clearest(index, site)
        ax.imshow(natural_color(tile(row)["image"]))
        ax.set_title(f"{name}\n{site.replace('_', ' ')} · {row.id[-4:]}", fontsize=8.5)
    hide_axes(axes)
    fig.tight_layout()
    save(fig, "pieges.jpg", dpi=65)


def fig_composition(index: pd.DataFrame) -> None:
    """Décisions attendues par partie, en barres empilées horizontales."""
    table = pd.crosstab(index.split, index.label).reindex(index=["train", "val", "test"], columns=list(LABEL_NAMES))
    fig, ax = plt.subplots(figsize=(9, 2.8))
    left = np.zeros(len(table))
    for label in table.columns:
        values = table[label].to_numpy()
        ax.barh([SPLIT_NAMES[s] for s in table.index], values, left=left, color=LABEL_COLORS[label],
                edgecolor=SURFACE, linewidth=2, height=0.6, label=LABEL_NAMES[label])
        for y, (l, v) in enumerate(zip(left, values)):
            if v >= 60:
                ax.text(l + v / 2, y, f"{v}", ha="center", va="center", fontsize=8.5, color="white")
        left += values
    for y, total in enumerate(left):
        ax.text(total + 15, y, f"{int(total)} tuiles", va="center", fontsize=8.5, color=INK_MUTED)
    ax.invert_yaxis()
    ax.set_xlim(0, left.max() * 1.15)
    ax.set_xlabel("Nombre de tuiles")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(frameon=False, ncol=4, fontsize=8.5, loc="lower left", bbox_to_anchor=(0, 1.02))
    save(fig, "composition.png", dpi=110)


def land_polygons():
    path = sources.download(NATURAL_EARTH, RAW / "naturalearth" / "ne_50m_land.geojson")
    for feature in json.loads(Path(path).read_text())["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            yield np.array(polygon[0])


def draw_land(ax) -> None:
    for ring in land_polygons():
        ax.fill(ring[:, 0], ring[:, 1], color="#e6ebea", lw=0, zorder=0)


def fig_maps(index: pd.DataFrame) -> None:
    """Carte du monde des tuiles par partie, et zoom sur les zones CaBuAr en Californie."""
    markers = {"sen1floods11": ("o", "Inondations (Sen1Floods11)"), "cabuar": ("^", "Incendies (CaBuAr)"),
               "catalogue": ("s", "Normales du catalogue"), "aleatoire": ("D", "Normales au hasard")}
    fig, ax = plt.subplots(figsize=(13, 6.2))
    draw_land(ax)
    for source, (marker, _) in markers.items():
        rows = index[index.source == source]
        for split, color in SPLIT_COLORS.items():
            sub = rows[rows.split == split]
            ax.scatter(sub.lon, sub.lat, s=26, marker=marker, color=color, edgecolor="white", lw=0.6, zorder=3)
    handles = [Patch(color=c, label=SPLIT_NAMES[s]) for s, c in SPLIT_COLORS.items()]
    handles += [plt.Line2D([], [], marker=m, ls="", color=INK_MUTED, label=n) for m, n in markers.values()]
    ax.legend(handles=handles, frameon=False, fontsize=8.5, loc="lower left", ncol=2)
    ax.set_xlim(-170, 180)
    ax.set_ylim(-56, 75)
    ax.set_aspect("equal")
    hide_axes(ax)
    save(fig, "carte_monde.png", dpi=100)

    fig, ax = plt.subplots(figsize=(7, 7.5))
    draw_land(ax)
    fires = index[index.source.str.startswith("cabuar") | index.group.str.startswith("cabuar_zone")]
    for split, color in SPLIT_COLORS.items():
        sub = fires[fires.split == split]
        ax.scatter(sub.lon, sub.lat, s=14, color=color, edgecolor="white", lw=0.4, zorder=3,
                   label=f"{SPLIT_NAMES[split]} · {sub.group.nunique()} zones, {len(sub)} tuiles")
    ax.set_xlim(-124.6, -114)
    ax.set_ylim(32.3, 42.2)
    ax.set_aspect(1 / np.cos(np.radians(37)))
    ax.legend(frameon=False, fontsize=8.5, loc="lower left")
    hide_axes(ax)
    save(fig, "carte_californie.png", dpi=100)


# --- Eau permanente -------------------------------------------------------------------

def fig_water(index: pd.DataFrame) -> None:
    """Eau permanente (JRC) et eau inattendue sur quatre tuiles."""
    rows = [(clearest(index, "golfe_bengale_ocean"), "Océan (Golfe du Bengale)"),
            (clearest(index, "niger_niamey_fleuve"), "Fleuve (Niamey)"),
            (index[index.id == "Bolivia_129334"].iloc[0], "Inondation (Bolivie)"),
            (index[index.id == "volta_reservoir_2021"].iloc[0], "Réservoir (lac Volta)")]
    fig, axes = plt.subplots(2, 4, figsize=(13, 7.6))
    for c, (row, name) in enumerate(rows):
        t = tile(row)
        rgb = natural_color(t["image"])
        permanent = permanent_water(t["water"])
        unexpected = (t["scl"] == 6) & ~permanent
        axes[0, c].imshow(rgb)
        axes[0, c].set_title(name, fontsize=9.5)
        shown = overlay(overlay(rgb, permanent, "#1d5f96", 0.65), unexpected, "#d1495b", 0.8)
        axes[1, c].imshow(shown)
        axes[1, c].set_title(f"permanente {permanent.mean():.0%} · inattendue {unexpected.mean():.0%}", fontsize=9)
    fig.legend(handles=[Patch(color="#1d5f96", label="Eau permanente (JRC, ≥ 50 % du temps)"),
                        Patch(color="#d1495b", label="Eau vue sur l'image (SCL) hors de l'eau permanente")],
               frameon=False, loc="lower center", ncol=2, fontsize=9, bbox_to_anchor=(0.5, -0.02))
    hide_axes(axes)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "eau_permanente.jpg", dpi=70)


def main() -> None:
    index = pd.read_csv(DATASET / "index_labels.csv")
    for make in (fig_reading, fig_spectra, fig_harmonization, fig_cabuar_location, fig_examples, fig_traps,
                 fig_composition, fig_maps, fig_water):
        make(index)


if __name__ == "__main__":
    main()
