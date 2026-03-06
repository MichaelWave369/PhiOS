from __future__ import annotations

import re

from phios import __version__
from phios.core.founding_document import FOUNDING_DOCUMENT, ParallaxFoundingDocument
from phios.core.launch_artifacts import LaunchArtifactGenerator
from phios.core.living_spec import PhiOSLivingSpec
from phios.shell.phi_commands import cmd_spec


def test_living_spec_generates_without_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec = PhiOSLivingSpec()
    path = spec.generate(force=True, operator_confirmed=True)
    assert (tmp_path / path).exists()


def test_living_spec_contains_hemavit_attribution(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec = PhiOSLivingSpec()
    path = spec.generate(force=True, operator_confirmed=True)
    assert "Hemavit" in (tmp_path / path).read_text(encoding="utf-8")


def test_living_spec_contains_lt_formula(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = PhiOSLivingSpec().generate(force=True, operator_confirmed=True)
    assert "L(t) = A_on · Ψb_total · G_score · C_score" in (tmp_path / path).read_text(encoding="utf-8")


def test_living_spec_contains_six_refusals(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    text = (tmp_path / PhiOSLivingSpec().generate(force=True, operator_confirmed=True)).read_text(encoding="utf-8")
    assert text.count("We refuse") >= 6


def test_living_spec_contains_dreamteam(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    text = (tmp_path / PhiOSLivingSpec().generate(force=True, operator_confirmed=True)).read_text(encoding="utf-8")
    assert "Dreamteam" in text


def test_living_spec_contains_cgcardona(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    text = (tmp_path / PhiOSLivingSpec().generate(force=True, operator_confirmed=True)).read_text(encoding="utf-8")
    assert "cgcardona" in text


def test_living_spec_seal_is_sha256(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec = PhiOSLivingSpec()
    path = spec.generate(force=True, operator_confirmed=True)
    seal = spec.generate_seal((tmp_path / path).read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-f0-9]{64}", seal)


def test_living_spec_verify_detects_tamper(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec = PhiOSLivingSpec()
    path = spec.generate(force=True, operator_confirmed=True)
    seal = spec.generate_seal((tmp_path / path).read_text(encoding="utf-8"))
    spec.store_in_archive(path, seal, operator_confirmed=False)
    p = tmp_path / path
    p.write_text(p.read_text(encoding="utf-8") + "\nTAMPER\n", encoding="utf-8")
    ok, _ = spec.verify(path)
    assert ok is False


def test_phi_spec_generate_creates_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = cmd_spec(["generate", "--yes"])
    assert "Spec generated" in out
    assert (tmp_path / "docs/PHIOS_LIVING_SPEC.md").exists()


def test_founding_document_contains_declaration() -> None:
    assert "Parallax Declaration" in FOUNDING_DOCUMENT


def test_founding_document_contains_hemavit() -> None:
    assert "Hemavit" in FOUNDING_DOCUMENT


def test_founding_document_contains_mt_shasta() -> None:
    assert "Mount Shasta" in FOUNDING_DOCUMENT


def test_founding_document_contains_rv() -> None:
    assert "RV" in FOUNDING_DOCUMENT


def test_founding_document_contains_lt_formula() -> None:
    assert "L(t) = A_on · Ψb_total · G_score · C_score" in FOUNDING_DOCUMENT


def test_founding_document_march_2026() -> None:
    assert "March 2026" in FOUNDING_DOCUMENT


def test_founding_document_export_creates_files(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    f = ParallaxFoundingDocument()
    md = f.export_markdown()
    html = f.export_html()
    assert (tmp_path / md).exists()
    assert (tmp_path / html).exists()


def test_founding_document_verify_hash(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    f = ParallaxFoundingDocument()
    md = f.export_markdown()
    digest = f.hash_document((tmp_path / md).read_text(encoding="utf-8"))
    f.store_in_archive(md, digest)
    ok, _ = f.verify(md)
    assert ok is True


def test_distrowatch_submission_under_250_words() -> None:
    text = LaunchArtifactGenerator().generate_distrowatch_submission()
    assert len(text.split()) < 250


def test_distrowatch_has_gpl3() -> None:
    assert "GPLv3" in LaunchArtifactGenerator().generate_distrowatch_submission()


def test_distrowatch_has_manifesto_url() -> None:
    assert "https://enterthefield.org/phios" in LaunchArtifactGenerator().generate_distrowatch_submission()


def test_distrowatch_based_on_arch() -> None:
    assert "Arch" in LaunchArtifactGenerator().generate_distrowatch_submission()


def test_announcement_kit_has_all_platforms() -> None:
    kit = LaunchArtifactGenerator().generate_announcement_kit()
    assert {"x_post", "extended", "technical"}.issubset(kit.keys())


def test_announcement_x_post_under_280_chars() -> None:
    assert len(LaunchArtifactGenerator().generate_announcement_kit()["x_post"]) <= 280


def test_announcement_contains_pip_install() -> None:
    assert "pip install phios" in LaunchArtifactGenerator().generate_announcement_kit()["x_post"]


def test_announcement_contains_hemavit() -> None:
    assert "Hemavit" in LaunchArtifactGenerator().generate_announcement_kit()["x_post"]


def test_investor_summary_one_page() -> None:
    summary = LaunchArtifactGenerator().generate_investor_summary()
    assert len(summary.splitlines()) <= 80


def test_investor_summary_contains_traction() -> None:
    assert "Traction" in LaunchArtifactGenerator().generate_investor_summary()


def test_launch_generate_all_creates_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    paths = LaunchArtifactGenerator().generate_all()
    assert len(paths) == 5


def test_version_is_1_0_0() -> None:
    assert str(__version__) == "1.0.0"


def test_changelog_has_v1_0_0_entry() -> None:
    text = open("CHANGELOG.md", encoding="utf-8").read()
    assert "## v1.0.0" in text


def test_changelog_v1_0_0_contains_declaration() -> None:
    text = open("CHANGELOG.md", encoding="utf-8").read()
    assert "The Parallax Declaration" in text
