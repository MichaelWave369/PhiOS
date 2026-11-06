"""R5: enforce bounded local artifact integrity without pretending provenance review."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"interop"))
import artifact_preflight_v1 as p

APP_ID="github:1442243366"
REPO="https://github.com/MichaelWave369/phi-field"

def example(payload: bytes) -> dict:
    return {
        "schema":"phios.artifact-intake.v1",
        "app_id":APP_ID,"repository":REPO,"target":"web",
        "source_commit_sha":"a"*40,
        "artifact":{"file_name":"release.zip","size_bytes":len(payload),
                    "sha256":hashlib.sha256(payload).hexdigest()},
        "assertions":{"publisher_signature_verified":False,"license_cleared":False,
                      "device_compatibility_verified":False,"operator_approved":False,
                      "install_authority":False,"requested_action":"verify_only"},
    }

def write(root:Path, manifest:dict,payload:bytes):
    item=root/"release.zip"
    item.write_bytes(payload)
    doc=root/"manifest.json"
    doc.write_text(json.dumps(manifest),encoding="utf-8")
    return doc,item


def test_real_bytes_match_without_native_install(tmp_path, capsys):
    payload=b"fixed inert application bundle for hash acceptance"
    doc,artifact=write(tmp_path,example(payload),payload)
    receipt=p.verify_artifact(p.read_proposal(doc),artifact)
    assert receipt["content_sha256_matches_manifest"] is True
    assert receipt["artifact"]["sha256"]==hashlib.sha256(payload).hexdigest()
    assert receipt["publisher_signature_verified"] is False
    assert receipt["license_cleared"] is False
    assert receipt["device_compatibility_verified"] is False
    assert receipt["install_authority"] is False
    assert receipt["effect_performed"] is False
    assert p.main(["--manifest",str(doc),"--artifact",str(artifact)])==0
    assert json.loads(capsys.readouterr().out)["next_gate"].startswith("independent")


def test_tamper_size_signature_licensing_and_unknown_identity_refused(tmp_path):
    payload=b"trusted-looking but untrusted bytes"
    manifest=example(payload)
    doc,artifact=write(tmp_path,manifest,payload)
    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError,match="length"):
        p.verify_artifact(p.read_proposal(doc),artifact)
    artifact.write_bytes(b"different content with same length"[:len(payload)])
    with pytest.raises(ValueError,match="SHA-256"):
        p.verify_artifact(p.read_proposal(doc),artifact)
    for name,value in (
        ("publisher_signature_verified",True),("operator_approved",True),
        ("license_cleared",True),("device_compatibility_verified",True),
        ("install_authority",True),("requested_action","install"),
    ):
        bad=example(payload)
        bad["assertions"][name]=value
        doc.write_text(json.dumps(bad))
        with pytest.raises(ValueError,match="authority"):
            p.read_proposal(doc)
    bad=example(payload)
    bad["app_id"]="github:99999999999999"
    doc.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match="catalog"):
        p.read_proposal(doc)


def test_extra_fields_traversal_unknown_runtime_and_bad_digest_refused(tmp_path):
    payload=b"hello"
    doc,artifact=write(tmp_path,example(payload),payload)
    for mutate in (
        lambda x: x.update({"command":"sudo pacman -U app"}),
        lambda x: x["artifact"].update({"file_name":"../evil.sh"}),
        lambda x: x["artifact"].update({"sha256":"0"*64}),
        lambda x: x.update({"target":"firmware"}),
        lambda x: x.update({"source_commit_sha":"HEAD"}),
        lambda x: x["artifact"].update({"size_bytes":True}),
    ):
        changed=example(payload)
        mutate(changed)
        doc.write_text(json.dumps(changed))
        if changed["artifact"]["sha256"]=="0"*64:
            assert p.read_proposal(doc)["artifact"]["sha256"]=="0"*64
            with pytest.raises(ValueError,match="SHA-256"):
                p.verify_artifact(p.read_proposal(doc),artifact)
        else:
            with pytest.raises(ValueError):
                p.read_proposal(doc)


def test_symlink_large_manifest_and_wrong_filename_refused(tmp_path):
    payload=b"hello"
    doc,artifact=write(tmp_path,example(payload),payload)
    alias=tmp_path/"alias.zip"
    alias.symlink_to(artifact)
    with pytest.raises(OSError):
        p.verify_artifact(p.read_proposal(doc),alias)
    bad_manifest=tmp_path/"linked.json"
    bad_manifest.symlink_to(doc)
    with pytest.raises(OSError):
        p.read_proposal(bad_manifest)
    doc.write_text(" "* (p.MAX_MANIFEST+1))
    with pytest.raises(ValueError,match="bounded"):
        p.read_proposal(doc)
    doc.write_text(json.dumps(example(payload)))
    renamed=tmp_path/"another.zip"
    renamed.write_bytes(payload)
    with pytest.raises(ValueError,match="basename"):
        p.verify_artifact(p.read_proposal(doc),renamed)


def test_schema_document_has_no_install_authority():
    schema=json.loads((ROOT/"interop/artifact-intake.v1.schema.json").read_text())
    assert schema["additionalProperties"] is False
    claims=schema["properties"]["assertions"]["properties"]
    for field in ("publisher_signature_verified","license_cleared","device_compatibility_verified","operator_approved","install_authority"):
        assert claims[field]["const"] is False
    assert claims["requested_action"]["const"]=="verify_only"
