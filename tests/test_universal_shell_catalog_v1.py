"""Contract tests: public discovery never becomes app authority."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "interop" / "shell_catalog_v1.py"
SPEC = importlib.util.spec_from_file_location("shell_catalog_v1", MODULE)
assert SPEC is not None and SPEC.loader is not None
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)

def sample():
    return json.loads((ROOT / "interop" / "public-repo-catalog.v1.json").read_text(encoding="utf-8"))

def check_modified(packet):
    with TemporaryDirectory() as temp:
        path = Path(temp) / "catalog.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return catalog.read_catalog(path)

def test_pinned_catalog_225_complete_public_names():
    packet = catalog.read_catalog()
    assert packet["provenance"]["scope"] == "public"
    assert packet["provenance"]["complete"] is True
    assert len(packet["apps"]) == 225
    assert len({item["id"] for item in packet["apps"]}) == 225
    assert all(item["availability"] == "source_only" for item in packet["apps"])

def test_source_metadata_never_grants_authority():
    packet = sample()
    assert not packet["policy"]["automatic_install"]
    assert not packet["policy"]["automatic_launch"]
    packet["policy"]["automatic_install"] = True
    with pytest.raises(ValueError, match="authority"):
        check_modified(packet)

def test_private_scope_refused():
    packet = sample()
    packet["provenance"]["scope"] = "all"
    with pytest.raises(ValueError, match="public"):
        check_modified(packet)

def test_duplicate_id_and_wrong_repo_refused():
    packet = sample()
    packet["apps"][1]["id"] = packet["apps"][0]["id"]
    with pytest.raises(ValueError, match="Duplicate"):
        check_modified(packet)
    packet = sample()
    packet["apps"][0]["repository"] = "https://github.com/OtherOwner/12fold"
    with pytest.raises(ValueError, match="match"):
        check_modified(packet)

def test_metadata_cannot_assert_install_or_launch():
    packet = sample()
    packet["apps"][0]["availability"] = "installed_verified"
    with pytest.raises(ValueError, match="installability"):
        check_modified(packet)

def test_cli_read_only_json(capsys):
    assert catalog.main(["--search", "PhiOS", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema"] == catalog.SCHEMA
    assert output["count"] > 0
    assert all("phios" in x["name"].lower() or "phios" in x["description"].lower() for x in output["apps"])
