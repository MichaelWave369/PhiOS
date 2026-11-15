"""Regression guard for the controlled Ubuntu 24.04 VM runner trial."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_both_vm_qualifiers_pin_supported_lts_and_preserve_failure_gates():
    for filename in ("linux-image.yml", "os-release-candidate.yml"):
        script = (ROOT / ".github" / "workflows" / filename).read_text(
            encoding="utf-8"
        )
        assert "    runs-on: ubuntu-24.04\n" in script
        assert "runs-on: ubuntu-latest" not in script
        assert "qemu-system-x86_64 --version" in script
        assert "sha256sum /usr/share/OVMF/OVMF_CODE_4M.fd" in script
        assert "sudo apt-get install -y qemu-system-x86 ovmf" in script
        assert "          sha256sum /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_VARS_4M.fd\n" in script
        assert "sha256sum /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_VARS_4M.fd python3-venv" not in script
        if filename == "os-release-candidate.yml":
            assert "sudo apt-get install -y qemu-system-x86 ovmf python3-pil python3-venv" in script
        assert "    timeout-minutes: 60\n" in script
        assert "--iso dist/" in script
        assert "--recovery" in script
        assert "      - name: " in script
        assert "if: always()" in script


def test_top_level_release_gate_remains_unconditional():
    script = (
        ROOT / ".github" / "workflows" / "release-qualification.yml"
    ).read_text(encoding="utf-8")
    assert "release-gate:" in script
    assert "if: ${{ always() }}" in script
    assert "python3 scripts/os_ci_gate.py check" in script
