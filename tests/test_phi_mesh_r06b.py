from unittest.mock import Mock, patch
import sqlite3

import pytest

from scripts import phi_mesh_r06b as mesh


@pytest.fixture
def job(tmp_path):
    spec = mesh.task("a"*64, "node02", "test:local", "logic")
    journal = mesh.Journal(tmp_path / "job.sqlite", spec)
    journal.initialize()
    return spec, journal


def test_restart_and_duplicate(job):
    spec, journal = job
    run = Mock(return_value={"status": "CORRECT"})
    assert journal.status()["state"] == "NOT_ADMITTED"
    result = journal.submit(run)
    restored = mesh.Journal(journal.path, spec)
    assert restored.status() == result == restored.submit(run)
    assert result["outcome"] == "CORRECT"
    assert result["execution_authority"] is False
    run.assert_called_once_with("test:local", mesh.CASES["logic"], 120)


def test_interrupted_admission_never_retries(job):
    spec, journal = job
    run = Mock(side_effect=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        journal.submit(run)
    restored = mesh.Journal(journal.path, spec)
    assert restored.status()["state"] == "OUTCOME_UNKNOWN"
    assert restored.submit(run)["outcome"] is None
    run.assert_called_once()


@pytest.mark.parametrize("outcome", ["INCORRECT", "ERROR"])
def test_distinct_terminal_results(job, outcome):
    _, journal = job
    assert journal.submit(lambda *a: {"status": outcome})["outcome"] == outcome


def test_missing_database_not_recreated(tmp_path):
    spec = mesh.task("a"*64, "node02", "test:local", "logic")
    journal = mesh.Journal(tmp_path / "missing.sqlite", spec)
    with pytest.raises(sqlite3.Error):
        journal.status()
    assert not journal.path.exists()


def test_no_overwrite_or_different_job(job):
    spec, journal = job
    with pytest.raises(FileExistsError):
        journal.initialize()
    other = mesh.Journal(journal.path, dict(spec, job="b"*64))
    with pytest.raises(ValueError):
        other.status()


@pytest.mark.parametrize("field,value", [("case","arbitrary"), ("model","test:cloud"), ("job","bad")])
def test_scope(field, value):
    spec = dict(job="a"*64, node="node02", model="test:local", case="logic")
    spec[field] = value
    with pytest.raises(ValueError):
        mesh.task(**spec)


def test_receipt_rejects_authority_or_wrong_job(job):
    spec, journal = job
    result = journal.status()
    assert mesh.validate_receipt(spec, result) == result
    for modified in (dict(result, execution_authority=True), dict(result, job="b"*64)):
        with pytest.raises(ValueError):
            mesh.validate_receipt(spec, modified)


def test_plan_and_wrong_approval_never_network(capsys):
    args = ["--job", "a"*64, "--node", "node02", "--model", "test:local", "--case", "logic"]
    with patch.object(mesh, "call") as call:
        assert mesh.main(["plan", *args]) == 0
        assert mesh.main(["submit", *args, "--confirm-offline-lan", "--approve-digest", "bad"]) == 1
        call.assert_not_called()
    assert "task_sha256" in capsys.readouterr().out
