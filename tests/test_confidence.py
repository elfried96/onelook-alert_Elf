import numpy as np

from onelook.data.labels import FIRE, FLOOD, NORMAL
from onelook.evaluation.metrics import UNKNOWN
from onelook.ood.confidence import calibrate_threshold, decisions, softmax


def test_softmax_rows_sum_to_one():
    probs = softmax(np.array([[1.0, 2.0, 3.0], [1000.0, 0.0, 0.0]]))
    assert np.allclose(probs.sum(axis=1), 1)
    assert probs[1, 0] > 0.999


def test_threshold_keeps_most_correct_answers_and_flags_doubtful_ones():
    probs = np.array([[0.9, 0.05, 0.05], [0.1, 0.8, 0.1], [0.2, 0.2, 0.6], [0.4, 0.35, 0.25]])
    labels = np.array([0, 1, 2, 0])
    threshold = calibrate_threshold(probs, labels, keep=0.75)
    assert 0.4 < threshold <= 0.6
    assert list(decisions(probs, threshold)) == [NORMAL, FLOOD, FIRE, UNKNOWN]
