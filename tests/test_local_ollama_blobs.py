import hashlib
import json
import struct

import pytest

from phios import local_ollama_blobs as li


@pytest.fixture
def model(tmp_path):
    root = tmp_path / "models"
    blobs = root / "blobs"
    blobs.mkdir(parents=True)
    relative = "manifests/registry.ollama.ai/library/example/latest"
    manifest = root / relative
    manifest.parent.mkdir(parents=True)

    def blob(body, media):
        digest = hashlib.sha256(body).hexdigest()
        (blobs / ("sha256-" + digest)).write_bytes(body)
        return {"digest": "sha256:" + digest, "size": len(body), "mediaType": media}

    config = blob(b"{}", "application/vnd.docker.container.image.v1+json")
    weight = blob(b"GGUF" + struct.pack("<IQQ", 3, 0, 0), li.WEIGHT_TYPE)
    data = {"schemaVersion": 2, "config": config, "layers": [weight]}
    manifest.write_text(json.dumps(data))
    return root, relative, data, manifest


def test_matching_blob_bytes(model):
    root, relative, _, _ = model
    report = li.verify(root, relative)
    assert report["status"] == "BLOB_BYTES_MATCH_REVIEW_ONLY"
    assert report["verified_selection_bytes"] == 26
    assert report["weight_descriptor_count"] == 1
    assert all(row["comparison"] == "MATCH" for row in report["blobs"])
    assert not report["offline_readiness_verified"]
    assert not report["weight_validity_verified"]
    assert not report["model_loaded"]
    assert not report["authority_granted"]
    assert "example" not in json.dumps(report)
    assert "sha256:" not in json.dumps(report)


def test_missing_and_corrupt_blobs(model):
    root, relative, data, _ = model
    path = root / "blobs" / data["layers"][0]["digest"].replace(":", "-")
    original = path.read_bytes()
    path.write_bytes(original[:-1] + b"x")
    assert li.verify(root, relative)["status"] == "HASH_MISMATCH"
    path.write_bytes(b"x")
    with pytest.raises(ValueError):
        li.verify(root, relative)
    path.unlink()
    with pytest.raises(OSError):
        li.verify(root, relative)


def test_budget_preflight(model, monkeypatch):
    root, relative, _, _ = model

    def forbidden(*args):
        pytest.fail("blob read before budget check")

    monkeypatch.setattr(li, "inspect_file", forbidden)
    with pytest.raises(ValueError):
        li.verify(root, relative, budget=25)


def test_duplicate_descriptors_count_bytes_once(model):
    root, relative, data, manifest = model
    data["layers"].append(dict(data["layers"][0]))
    manifest.write_text(json.dumps(data))
    report = li.verify(root, relative, budget=26)
    assert report["verified_selection_bytes"] == 26
    assert report["weight_descriptor_count"] == 2
    assert len(report["blobs"]) == 2
    data["layers"][-1]["size"] += 1
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        li.verify(root, relative)


def test_no_weights_not_ready(model):
    root, relative, data, manifest = model
    data["layers"][0]["mediaType"] = "application/vnd.ollama.image.template"
    manifest.write_text(json.dumps(data))
    assert li.verify(root, relative)["status"] == "NO_MODEL_WEIGHT_DESCRIPTOR"


def test_matching_non_gguf_is_unverified(model):
    root, relative, data, manifest = model
    payload = b"not a model"
    digest = hashlib.sha256(payload).hexdigest()
    (root / "blobs" / ("sha256-" + digest)).write_bytes(payload)
    data["layers"][0].update(digest="sha256:" + digest, size=len(payload))
    manifest.write_text(json.dumps(data))
    assert li.verify(root, relative)["status"] == "BLOB_BYTES_MATCH_WEIGHT_FORMAT_UNVERIFIED"


@pytest.mark.parametrize("relative", [
    "../secret", "manifests/../secret", "/manifests/file",
    "manifests/a\\b", "manifests//file", "manifests/a:b",
])
def test_path_rejection(model, relative):
    with pytest.raises(ValueError):
        li.verify(model[0], relative)


@pytest.mark.parametrize(("key", "value"), [
    ("digest", "sha256:../../secret"), ("size", True),
    ("size", 0), ("urls", ["https://example.invalid/file"]),
])
def test_invalid_descriptor(model, key, value):
    root, relative, data, manifest = model
    data["layers"][0][key] = value
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        li.verify(root, relative)


def test_duplicate_json_keys(model):
    root, relative, _, manifest = model
    manifest.write_text('{"schemaVersion":2,"schemaVersion":2}')
    with pytest.raises(ValueError):
        li.verify(root, relative)


def test_blob_symlink_rejected(model):
    root, relative, data, _ = model
    path = root / "blobs" / data["layers"][0]["digest"].replace(":", "-")
    target = root / "elsewhere"
    path.rename(target)
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink privileges unavailable")
    with pytest.raises(ValueError):
        li.verify(root, relative)


def test_cli_redacted_failure(model, monkeypatch, capsys):
    root, _, _, _ = model
    monkeypatch.setattr("sys.argv", ["verify", "--root", str(root),
                                   "--manifest", "manifests/private-missing"])
    assert li.main() == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "INVALID_OR_UNREADABLE_SELECTION"
    }
