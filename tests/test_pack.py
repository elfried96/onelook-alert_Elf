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


def test_pack_keeps_band_names_for_six_and_twelve_bands(tmp_path):
    import numpy as np
    import rasterio
    from affine import Affine

    from onelook.data.pack import pack_band_names, pack_tile, read_packed
    from onelook.data.sentinel2 import BANDS_L2A

    profile = dict(driver="GTiff", width=512, height=512, crs="EPSG:32631", transform=Affine(10, 0, 0, 0, -10, 0))
    image = np.arange(12, dtype=np.uint16)[:, None, None] * 1000 + np.zeros((12, 512, 512), np.uint16)
    with rasterio.open(tmp_path / "t.tif", "w", count=12, dtype="uint16", **profile) as dst:
        dst.write(image)
    for name in ("t_SCL.tif", "t_water.tif"):
        with rasterio.open(tmp_path / name, "w", count=1, dtype="uint8", **profile) as dst:
            dst.write(np.zeros((1, 512, 512), np.uint8))
    row = {"image": "t.tif", "source": "catalogue"}
    for bands in (["B02", "B03", "B04", "B08", "B11", "B12"], BANDS_L2A):
        out = tmp_path / f"pack_{len(bands)}.tif"
        pack_tile(tmp_path, row, out, bands)
        tile = read_packed(out)
        assert pack_band_names(out) == list(bands)
        assert tile["image"].shape == (len(bands), 512, 512)
        assert tile["image"][bands.index("B08"), 0, 0] == BANDS_L2A.index("B08") / 10
        assert (tile["truth"] == 0).all()
