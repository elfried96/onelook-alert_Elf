import pandas as pd

from onelook.data.labels import AMBIGUOUS, FIRE, FLOOD, NORMAL
from onelook.evaluation.metrics import UNKNOWN, confusion, decision_metrics


def make_index():
    return pd.DataFrame({
        "label": [FLOOD, FLOOD, FIRE, NORMAL, NORMAL, NORMAL, AMBIGUOUS],
        "source": ["sen1floods11", "sen1floods11", "cabuar", "catalogue", "cabuar", "catalogue", "cabuar"],
        "category": ["inondation", "inondation", "incendie", "ocean", "incendie", "desert", "incendie"],
    })


def test_precision_recall_and_false_alerts():
    preds = [FLOOD, UNKNOWN, FIRE, FLOOD, NORMAL, NORMAL, FIRE]
    m = decision_metrics(make_index(), preds)
    assert m["tuiles"] == 6  # la tuile ambiguë est écartée
    assert m["rappel_inondation"] == 0.5  # « inconnu » sur une inondation compte comme manquée
    assert m["precision_inondation"] == 0.5  # l'océan pris pour une inondation
    assert m["rappel_incendie"] == 1.0
    assert abs(m["fausses_alertes"] - 1 / 3) < 1e-9
    assert m["fausses_alertes_eau"] == 1.0
    assert m["fausses_alertes_hors_californie"] == 0.5


def test_confusion_has_all_decisions():
    table = confusion(make_index(), [FLOOD, UNKNOWN, FIRE, FLOOD, NORMAL, NORMAL, FIRE])
    assert list(table.columns) == [NORMAL, FLOOD, FIRE, UNKNOWN]
    assert table.loc[FLOOD, UNKNOWN] == 1
