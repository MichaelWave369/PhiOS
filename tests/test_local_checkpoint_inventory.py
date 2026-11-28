import hashlib
import json
import os
import struct

import pytest

from phios import local_checkpoint_inventory as li


def gguf_bytes():
    return b"GGUF" + struct.pack("<IQQ", 3, 0, 0)


def test_explicit_bytes_and_digest(tmp_path):
    path = tmp_path / "private-model.gguf"
    body = gguf_bytes()
    path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    report = li.inventory([path], [digest], budget=len(body))
    assert report["status"] == "REVIEW_ONLY"
    assert report["checkpoints"] == [{
        "selection": 1, "observed_bytes": len(body), "sha256": digest,
        "format_hint": "GGUF_HEADER_HINT", "comparison": "MATCH",
    }]
    assert "private-model" not in json.dumps(report)
    assert not report["weight_validity_verified"]
    assert not report["model_loaded"]
    assert not report["inference_executed"]
    assert not report["authority_granted"]
    assert li.inventory([path], ["0" * 64])["status"] == "HASH_MISMATCH"


def test_safetensors_header_hint(tmp_path):
    header = json.dumps({
        "w": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}
    }).encode()
    path = tmp_path / "fixture.safetensors"
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"1234")
    assert li.inventory([path])["checkpoints"][0]["format_hint"] == "SAFETENSORS_HEADER_HINT"
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"1")
    assert li.inventory([path])["checkpoints"][0]["format_hint"] == "UNRECOGNIZED"


def test_extension_is_not_evidence(tmp_path):
    path = tmp_path / "fake.gguf"
    path.write_bytes(b"not a checkpoint")
    assert li.inventory([path])["checkpoints"][0]["format_hint"] == "UNRECOGNIZED"


def test_budget_and_duplicate_rejected_before_read(tmp_path, monkeypatch):
    path = tmp_path / "fixture"
    path.write_bytes(b"test")

    def forbidden(*args):
        pytest.fail("read before preflight")

    monkeypatch.setattr(li, "inspect_file", forbidden)
    for paths, budget in [([path], 3), ([path, path], 8), ([], 1)]:
        with pytest.raises(ValueError):
            li.inventory(paths, budget=budget)


def test_reject_directory_and_empty(tmp_path):
    empty = tmp_path / "empty"
    empty.touch()
    for path in (tmp_path, empty):
        with pytest.raises(ValueError):
            li.inventory([path])


def test_reject_symlink(tmp_path):
    target = tmp_path / "target"
    target.write_bytes(b"bytes")
    link = tmp_path / "alias"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink privileges unavailable")
    with pytest.raises(ValueError):
        li.inventory([link])


def test_duplicate_hardlink(tmp_path):
    target = tmp_path / "target"
    target.write_bytes(b"bytes")
    alias = tmp_path / "alias"
    try:
        os.link(target, alias)
    except (OSError, NotImplementedError):
        pytest.skip("hardlinks unavailable")
    with pytest.raises(ValueError):
        li.inventory([target, alias])


def test_changed_metadata_rejected(tmp_path):
    path = tmp_path / "fixture"
    path.write_bytes(b"test")
    before = path.stat()
    path.write_bytes(b"changed")
    with pytest.raises(ValueError):
        li.inspect_file(path, before, None)


@pytest.mark.parametrize("digest", ["", "abc", "X" * 64])
def test_bad_expected_digest(tmp_path, digest):
    path = tmp_path / "fixture"
    path.write_bytes(b"x")
    with pytest.raises(ValueError):
        li.inventory([path], [digest])


def test_cli_private_error_and_mismatch(tmp_path, capsys, monkeypatch):
    path = tmp_path / "secret-name"
    monkeypatch.setattr("sys.argv", ["inventory", "--checkpoint", str(path)])
    assert li.main() == 2
    assert "secret-name" not in capsys.readouterr().out
    path.write_bytes(b"x")
    monkeypatch.setattr("sys.argv", [
        "inventory", "--checkpoint", str(path), "--expected-sha256", "0" * 64
    ])
    assert li.main() == 3
    assert json.loads(capsys.readouterr().out)["status"] == "HASH_MISMATCH"
