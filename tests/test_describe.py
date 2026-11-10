import numpy as np

from onelook.demo.describe import Facts, describe, region

PROBS = {"normal": 0.03, "alerte_inondation": 0.96, "alerte_incendie": 0.01}


def test_region_names_the_heaviest_part_of_the_tile():
    drop = np.zeros((8, 8))
    drop[6:, :2] = 10
    assert region(drop) == "le sud-ouest de la tuile"
    assert region(np.zeros((8, 8))) is None


def test_unusual_water_is_the_water_outside_permanent_water():
    text = describe(Facts("alerte_inondation", PROBS, 0.67, water=0.40, permanent_water=0.02))
    assert "environ 38 % d'eau inhabituelle" in text["constats"][0]


def test_unknown_headline_says_what_the_model_leans_to():
    probs = {"normal": 0.55, "alerte_inondation": 0.40, "alerte_incendie": 0.05}
    title = describe(Facts("inconnu", probs, 0.67))["titre"]
    assert title.startswith("Inconnu") and "« normal »" in title and "0,67" in title


def test_missing_measures_give_no_sentence():
    text = describe(Facts("alerte_inondation", PROBS, 0.67))
    assert text["contexte"] is None
    assert text["constats"] == ["Seconde hypothèse : normal, 3 %."]


def test_neighbours_and_atypicity():
    neighbours = [{"label": "alerte_inondation", "place": "Paraguay"}] * 5
    text = describe(Facts("alerte_inondation", PROBS, 0.67, neighbours=neighbours, atypicity=230,
                          atypicity_limit=175))
    assert any("toutes des inondations (Paraguay)" in c for c in text["constats"])
    assert any(c.startswith("Tuile atypique") for c in text["constats"])
