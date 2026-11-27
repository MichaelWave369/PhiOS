import pytest

from phios.simready_intake import DATASET, MANIFEST, plan


def fixture():
    return {
        "dataset": DATASET,
        "revision": "a" * 40,
        "files": [
            {"path": f"box/{MANIFEST}", "size": 2},
            {"path": "box/model.usd", "size": 8},
            {"path": "box_other/model.usd", "size": 100},
        ],
    }


def test_exact_boundary_and_budget():
    result = plan(fixture(), ["box"], 10)
    assert result["declared_total_bytes"] == 10
    assert result["status"] == "REVIEW_ONLY"
    assert result["license"] == "CC-BY-4.0"
    assert plan(fixture(), ["box"], 9)["status"] == "OVER_BUDGET"


@pytest.mark.parametrize("path", ["../bad", "/bad", "box//bad", "box\\bad", "box/%2e"])
def test_unsafe_path(path):
    data = fixture()
    data["files"].append({"path": path, "size": 1})
    with pytest.raises(ValueError):
        plan(data, ["box"], 10)


def test_duplicate_and_nested_manifest():
    data = fixture()
    data["files"].append(data["files"][0])
    with pytest.raises(ValueError):
        plan(data, ["box"], 10)
    data = fixture()
    data["files"].append({"path": f"box/nested/{MANIFEST}", "size": 1})
    with pytest.raises(ValueError):
        plan(data, ["box"], 10)


@pytest.mark.parametrize("selected", [[], ["box", "box"], ["missing"], ["box"] * 37])
def test_selection(selected):
    with pytest.raises(ValueError):
        plan(fixture(), selected, 10)


def test_unpinned_revision_and_invalid_sizes():
    data = fixture()
    data["revision"] = "main"
    with pytest.raises(ValueError):
        plan(data, ["box"], 10)
    for size in [-1, True, 1.5]:
        data = fixture()
        data["files"][0]["size"] = size
        with pytest.raises(ValueError):
            plan(data, ["box"], 10)
