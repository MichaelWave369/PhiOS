from __future__ import annotations

import json
from pathlib import Path

from phios import __version__
from phios.shell.phi_router import route_command


def test_release_notes_generator_finds_current_version():
    from scripts.generate_release_notes import generate_release_notes

    notes = generate_release_notes()
    assert f"## v{__version__}" in notes or f"PhiOS v{__version__}" in notes


def test_release_notes_extracts_correct_section():
    from scripts.generate_release_notes import extract_section

    text = "## v0.7.0 — Title\nA\n## v0.6.0 — Prev\nB"
    out = extract_section("0.7.0", text)
    assert "Title" in out
    assert "Prev" not in out


def test_release_notes_fallback_when_not_found():
    from scripts.generate_release_notes import extract_section

    out = extract_section("9.9.9", "")
    assert "Sovereign Computing Shell" in out


def test_changelog_has_all_versions():
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    for v in ["v0.7.0", "v0.6.0", "v0.5.0", "v0.4.0", "v0.3.0", "v0.2.0", "v0.1.0"]:
        assert v in text


def test_changelog_has_hemavit_attribution():
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert "Hemavit" in text


def test_iso_build_script_exists():
    assert Path("build/build_iso.sh").exists()


def test_iso_build_requires_confirmation():
    out, code = route_command(["build", "iso"])
    assert code == 0
    assert "Refusing to build ISO" in out


def test_iso_profile_contains_phios_packages():
    text = Path("build/archiso-profile/packages.x86_64").read_text(encoding="utf-8")
    assert "phios" in text


def test_iso_profile_contains_wayfire():
    text = Path("build/archiso-profile/packages.x86_64").read_text(encoding="utf-8")
    assert "wayfire" in text


def test_iso_profile_contains_ollama():
    text = Path("build/archiso-profile/packages.x86_64").read_text(encoding="utf-8")
    assert "ollama" in text


def test_phi_build_status_schema_correct():
    out, code = route_command(["build", "status"])
    assert code == 0
    data = json.loads(out)
    for key in ["exists", "path", "size", "sha256"]:
        assert key in data


def test_phi_build_clean_removes_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build" / "work").mkdir(parents=True)
    (tmp_path / "build" / "out").mkdir(parents=True)
    (tmp_path / "dist").mkdir(parents=True)
    (tmp_path / "dist" / "phios-v0.7.0-x86_64.iso").write_text("x", encoding="utf-8")
    out, code = route_command(["build", "clean"])
    assert code == 0
    data = json.loads(out)
    assert data["removed"]


def test_release_workflow_exists():
    assert Path(".github/workflows/release.yml").exists()


def test_release_workflow_has_test_job():
    text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "test:" in text


def test_release_workflow_has_pypi_publish():
    text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "pypa/gh-action-pypi-publish@release/v1" in text
    assert "id-token: write" in text


def test_release_workflow_has_github_release():
    text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "github-release:" in text


def test_release_workflow_release_body_has_manifesto_url():
    text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "https://enterthefield.org/phios" in text


def test_release_workflow_release_body_has_hemavit():
    text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "Hemavit" in text


def test_release_workflow_no_hardcoded_tokens():
    text = Path(".github/workflows/release.yml").read_text(encoding="utf-8").lower()
    assert "ghp_" not in text
    assert "pypi_token" not in text
    assert "__token__" not in text


def test_changelog_exists():
    assert Path("CHANGELOG.md").exists()


def test_changelog_has_dreamteam_header():
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert "Dreamteam attribution" in text


def test_changelog_v07_entry_exists():
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v0.7.0" in text
