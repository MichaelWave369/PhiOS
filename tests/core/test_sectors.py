from __future__ import annotations

from phios.core.sectors import (
    get_visual_bloom_sector,
    infer_visual_bloom_sector_weights,
    list_visual_bloom_sectors,
)


def test_sector_ontology_list_and_lookup():
    all_rows = list_visual_bloom_sectors()
    assert all_rows
    hg = list_visual_bloom_sectors("HG")
    assert hg and all(r["family"] == "HG" for r in hg)
    g = get_visual_bloom_sector("geometry", "HG")
    assert g is not None
    assert g["sector_id"] == "geometry"


def test_infer_sector_weights_is_deterministic():
    w1 = infer_visual_bloom_sector_weights({"coherenceC": 0.81, "frequency": 7.83, "noiseScale": 0.004, "tags": ["a", "b"]})
    w2 = infer_visual_bloom_sector_weights({"coherenceC": 0.81, "frequency": 7.83, "noiseScale": 0.004, "tags": ["a", "b"]})
    assert w1 == w2
    assert abs(sum(w1.values()) - 1.0) < 1e-9
