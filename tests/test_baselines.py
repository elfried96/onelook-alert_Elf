import numpy as np

from onelook.data.labels import FIRE, FLOOD, NORMAL
from onelook.models.baselines import INDEX_GRID, decide, fit_thresholds, stat_features, threshold_features


def tile(water=0.0, burned=0.0, size=64):
    """Tuile synthétique : végétation, avec une part d'eau (PIR bas) et une part brûlée (SWIR haut)."""
    image = np.zeros((6, size, size), dtype=np.float32)
    image[:] = np.array([0.04, 0.07, 0.05, 0.35, 0.18, 0.08])[:, None, None]
    rows_w, rows_b = int(water * size), int(burned * size)
    image[:, :rows_w] = np.array([0.06, 0.08, 0.07, 0.03, 0.01, 0.01])[:, None, None]
    image[:, size - rows_b:] = np.array([0.04, 0.05, 0.06, 0.12, 0.20, 0.22])[:, None, None]
    return image


def test_features_see_water_and_burned_area():
    water_frac, fire_frac = threshold_features(tile(water=0.25, burned=0.5))
    i0, j0 = np.argmin(abs(INDEX_GRID)), np.argmin(abs(INDEX_GRID))
    assert abs(water_frac[i0] - 0.25) < 0.05
    assert abs(fire_frac[i0, j0] - 0.5) < 0.05
    assert stat_features(tile()).shape == (45,)


def test_decide_and_fit_recover_simple_rules():
    assert list(decide(np.array([0.3, 0.0, 0.0]), np.array([0.0, 0.4, 0.0]), 0.05, 0.05)) == [FLOOD, FIRE, NORMAL]
    tiles = [tile(water=0.4), tile(burned=0.5), tile(), tile(water=0.3), tile(burned=0.3), tile()]
    labels = np.array([FLOOD, FIRE, NORMAL, FLOOD, FIRE, NORMAL], dtype=object)
    feats = [threshold_features(t) for t in tiles]
    rule, score = fit_thresholds(np.stack([f[0] for f in feats]), np.stack([f[1] for f in feats]), labels)
    assert score == 1.0
    assert list(rule.predict(np.stack([f[0] for f in feats]), np.stack([f[1] for f in feats]))) == list(labels)
