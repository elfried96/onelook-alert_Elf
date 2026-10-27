import pandas as pd

from onelook.data.labels import AMBIGUOUS, FIRE, FLOOD, NORMAL, LabelRules, add_labels, label_row

RULES = LabelRules(flood_alert=0.05, fire_alert=0.05, normal_max=0.005)


def test_clearly_flooded_tile_is_flood_alert():
    assert label_row(frac_flood=0.6, frac_valid=1.0, frac_burned=0.0, rules=RULES) == FLOOD


def test_flood_hidden_by_clouds_does_not_alert():
    # 60 % de la partie visible est inondée, mais seuls 5 % de la tuile sont visibles : 3 % de la tuile
    assert label_row(frac_flood=0.6, frac_valid=0.05, frac_burned=0.0, rules=RULES) == AMBIGUOUS


def test_burned_tile_is_fire_alert():
    assert label_row(frac_flood=0.0, frac_valid=1.0, frac_burned=0.2, rules=RULES) == FIRE


def test_tiny_anomaly_is_ambiguous_and_nothing_is_normal():
    assert label_row(frac_flood=0.01, frac_valid=1.0, frac_burned=0.0, rules=RULES) == AMBIGUOUS
    assert label_row(frac_flood=0.0, frac_valid=1.0, frac_burned=0.0, rules=RULES) == NORMAL


def test_add_labels_handles_missing_fractions():
    index = pd.DataFrame({"frac_flood": [0.5, None], "frac_valid": [1.0, None], "frac_burned": [0.0, None]})
    assert list(add_labels(index, RULES)["label"]) == [FLOOD, NORMAL]
