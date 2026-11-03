import numpy as np

from onelook.data.pack import TRUTH_BURNED, TRUTH_FLOOD, TRUTH_NONE, TRUTH_UNSEEN, unified_truth


def test_flood_mask_keeps_only_flood_water_and_marks_unseen():
    # codes d'origine : 0 non observé, 1 sec, 2 eau permanente, 3 eau d'inondation
    mask = np.array([[0, 1], [2, 3]], dtype=np.uint8)
    truth = unified_truth(mask, "sen1floods11", mask.shape)
    assert truth.tolist() == [[TRUTH_UNSEEN, TRUTH_NONE], [TRUTH_NONE, TRUTH_FLOOD]]


def test_burned_mask_and_unannotated_normals():
    mask = np.array([[0, 1]], dtype=np.uint8)
    assert unified_truth(mask, "cabuar", mask.shape).tolist() == [[TRUTH_NONE, TRUTH_BURNED]]
    assert unified_truth(None, "catalogue", (2, 2)).max() == TRUTH_NONE
