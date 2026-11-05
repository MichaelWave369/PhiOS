"""Φ Universal App Shelf R2: explicit source-only persistence and cross-platform JSON."""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
INTEROP=ROOT/"interop"
if str(INTEROP) not in sys.path:
    sys.path.insert(0,str(INTEROP))
shelf=importlib.import_module("app_shelf_v1")
catalog=importlib.import_module("shell_catalog_v1")


def known_ids():
    return [x["id"] for x in catalog.read_catalog()["apps"]]


def test_contract_portability_and_no_install_claims():
    ids=known_ids()
    packet=shelf.encode_shelf(ids[:2],timestamp=datetime(2026,11,5,22,0,tzinfo=timezone.utc))
    assert packet["format"]=="phios-app-shelf"
    assert packet["version"]==1
    assert packet["catalog_source_sha"]=="e295f6265e60032de98a2acd8e53295505fc47e8"
    assert packet["exported_at"]=="2026-11-05T22:00:00.000Z"
    assert shelf.decode_shelf(packet)==ids[:2]
    assert shelf.LIMIT==24
    js=(INTEROP/"shelf-portable.v1.js").read_text(encoding="utf-8")
    assert "phios-app-shelf" in js and "LIMIT=24" in js
    assert "automatic_install!==false" in js


def test_rejects_unknown_duplicate_and_capability_injection():
    ids=known_ids()
    packet=shelf.encode_shelf(ids[:2])
    with pytest.raises(ValueError,match="fields"):
        shelf.decode_shelf(dict(packet,install_authority=True))
    with pytest.raises(ValueError,match="duplicate"):
        shelf.decode_shelf(dict(packet,pinned=[ids[0],ids[0]]))
    with pytest.raises(ValueError,match="unknown"):
        shelf.decode_shelf(dict(packet,pinned=["github:999999999999999"]))
    with pytest.raises(ValueError,match="snapshot"):
        shelf.decode_shelf(dict(packet,catalog_source_sha="0"*40))
    with pytest.raises(ValueError,match="24"):
        shelf.validate_pins(ids[:25],{x:None for x in ids})


def test_cli_pin_order_export_import_roundtrip(tmp_path, capsys):
    ids=known_ids()
    target=tmp_path/"shelf.json"
    output=tmp_path/"portable.json"
    shelf.main(["--shelf",str(target),"pin",ids[0]])
    shelf.main(["--shelf",str(target),"pin",ids[1]])
    assert shelf.read_shelf(target)==ids[:2]
    shelf.main(["--shelf",str(target),"move",ids[1],"up"])
    assert shelf.read_shelf(target)==[ids[1],ids[0]]
    shelf.main(["--shelf",str(target),"export","--output",str(output)])
    assert shelf.decode_shelf(json.loads(output.read_text()))==[ids[1],ids[0]]
    with pytest.raises(ValueError,match="exists"):
        shelf.main(["--shelf",str(target),"export","--output",str(output)])
    shelf.main(["--shelf",str(target),"unpin",ids[1]])
    assert shelf.read_shelf(target)==[ids[0]]
    with pytest.raises(ValueError,match="confirm"):
        shelf.main(["--shelf",str(target),"import","--input",str(output)])
    shelf.main(["--shelf",str(target),"import","--input",str(output),"--confirm-replace"])
    assert shelf.read_shelf(target)==[ids[1],ids[0]]
    assert "no installs" in capsys.readouterr().out


def test_symlink_and_corrupt_backup_rejected(tmp_path):
    ids=known_ids()
    destination=tmp_path/"target.json"
    destination.write_text(json.dumps(shelf.encode_shelf([ids[0]])),encoding="utf-8")
    link=tmp_path/"link.json"
    link.symlink_to(destination)
    with pytest.raises(ValueError,match="Symlink|symlink"):
        shelf.read_shelf(link)
    destination.write_text('{"format":"unknown"}',encoding="utf-8")
    with pytest.raises(ValueError):
        shelf.read_shelf(destination)


def test_manifest_schema_blocks_install_and_launch_authority():
    schema=json.loads((INTEROP/"app-descriptor.v1.schema.json").read_text(encoding="utf-8"))
    props=schema["properties"]
    assert schema["additionalProperties"] is False
    assert props["install_authority"]["const"] is False
    assert props["launch_authority"]["const"] is False
    assert props["review_status"]["const"]=="unreviewed"
    assert sorted(props["runtime_kind"]["enum"])==sorted(
        ["unknown","web","android","linux","service","library","research"])
