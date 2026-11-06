"""R4: reviewed browser-app metadata cannot authorize native/install operations."""
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
INTEROP=ROOT/"interop"
if str(INTEROP) not in sys.path:sys.path.insert(0,str(INTEROP))
reviews=importlib.import_module("app_center_reviews_v1")


def packet():
    return json.loads(reviews.REGISTRY.read_text(encoding="utf-8"))


def test_exact_first_party_review_without_production_claim():
    data=reviews.read_reviews()
    assert data["catalog_source_sha"]=="e295f6265e60032de98a2acd8e53295505fc47e8"
    assert len(data["reviewed_web_apps"])==1
    entry=data["reviewed_web_apps"][0]
    assert entry["app_id"]=="github:1442243366"
    assert entry["launch_url"]=="https://phi-field.com/os/"
    assert entry["review_status"]=="ci_reviewed_browser_app"
    assert entry["evidence"]["live_endpoint_independently_verified"] is False
    assert entry["actions"]["native_install"] is False


def reject(tmp_path,changed):
    testfile=tmp_path/"review.json"
    testfile.write_text(json.dumps(changed),encoding="utf-8")
    with pytest.raises(ValueError):
        reviews.read_reviews(testfile)


def test_cannot_add_arbitrary_repository_or_install_authority(tmp_path):
    data=packet()
    data["reviewed_web_apps"][0]["actions"]["native_install"]=True
    reject(tmp_path,data)
    data=packet()
    data["reviewed_web_apps"][0]["actions"]["automatic_execution"]=True
    reject(tmp_path,data)
    data=packet()
    data["policy"]["autonomous_installs"]=True
    reject(tmp_path,data)
    data=packet()
    data["reviewed_web_apps"].append(data["reviewed_web_apps"][0])
    reject(tmp_path,data)


def test_url_and_review_evidence_bounded_to_exact_pwa(tmp_path):
    data=packet()
    data["reviewed_web_apps"][0]["launch_url"]="https://evil.example/app"
    reject(tmp_path,data)
    data=packet()
    data["reviewed_web_apps"][0]["launch_url"]="https://phi-field.com/os/?inject=1"
    reject(tmp_path,data)
    data=packet()
    data["reviewed_web_apps"][0]["evidence"]["live_endpoint_independently_verified"]=True
    reject(tmp_path,data)
    data=packet()
    data["reviewed_web_apps"][0]["evidence"]["source_pr"]=123
    reject(tmp_path,data)
    data=packet()
    data["catalog_source_sha"]="0"*40
    reject(tmp_path,data)


def test_rejects_unrecognized_fields(tmp_path):
    data=packet()
    data["reviewed_web_apps"][0]["approval_token"]="invented"
    reject(tmp_path,data)
    data=packet()
    data["credential"]="unrelated"
    reject(tmp_path,data)
