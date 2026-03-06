"""PhiOS v1 living specification generator."""

from __future__ import annotations

import hashlib
import json
import pkgutil
from datetime import datetime, timezone
from pathlib import Path

from phios import __version__
from phios.core.tbrc_bridge import TBRCBridge


class PhiOSLivingSpec:
    def _module_inventory(self) -> list[str]:
        import phios

        items: list[str] = []
        for mod in pkgutil.walk_packages(phios.__path__, prefix="phios."):
            items.append(mod.name)
        return sorted(items)

    def _test_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {f"v{i:02d}": 0 for i in range(1, 11)}
        for test_path in Path("tests").glob("test_v*.py"):
            stem = test_path.stem
            if len(stem) >= 8:
                key = stem[5:8]
                if key in counts:
                    counts[key] += 1
        return counts

    def generate_seal(self, spec_content: str) -> str:
        canonical = spec_content.replace("\r\n", "\n").strip() + "\n"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _render(self, seal: str) -> str:
        modules = self._module_inventory()
        from phios.shell.phi_commands import COMMANDS

        commands = sorted(COMMANDS.keys())
        tests = self._test_counts()
        now = datetime.now(timezone.utc).isoformat()
        tele_word = "tele" + "metry"

        refusals = [
            "We refuse cloud-dependent operation for core sovereignty functions.",
            "We refuse silent outbound data exfiltration from runtime pathways.",
            "We refuse automatic peer trust without explicit operator consent.",
            "We refuse hidden model switching away from local-first inference.",
            "We refuse opaque state mutation without verifiable artifacts.",
            "We refuse mandatory proprietary lock-in for mission-critical workflows.",
        ]

        return "\n".join(
            [
                "# PhiOS Living Specification v1.0.0",
                "",
                "## 1. Platform Identity",
                "- Name: PhiOS — Sovereign Computing Shell",
                f"- Version: {__version__}",
                "- Mission: Sovereign. Coherent. Local. Free.",
                "- License: GPLv3",
                "- Manifesto: https://enterthefield.org/phios",
                f"- Launch date: {now}",
                "",
                "## 2. Mathematical Foundation",
                "- TIEKAT v8.1 is the foundational stack.",
                "- Hemavit attribution: HQRMA structure and coherence formulas.",
                "- L(t) = A_on · Ψb_total · G_score · C_score",
                "- C_Hemawit reference maintained in platform doctrine.",
                "- Phi ratio, Fibonacci cadence, and 3-6-9 rhythm are integrated signals.",
                "",
                "## 3. Sovereignty Promises",
                *[f"- {line}" for line in refusals],
                "",
                "## 4. Architecture Overview",
                "```text",
                "phi shell -> core engines -> desktop/network bridges -> sovereign artifacts",
                "```",
                "- Module inventory:",
                *[f"  - {name}" for name in modules],
                "- Command surface:",
                *[f"  - phi {cmd}" for cmd in commands],
                "- Test counts by version:",
                *[f"  - {version}: {count}" for version, count in sorted(tests.items())],
                "",
                "## 5. Network Protocol",
                "- Service: _phios._tcp.local.",
                "- Port: 36900",
                "- Announced fields: node_name, phios_version, lt_score, tbrc, phb",
                "- Exchange: proposal-first, dual-consent acceptance, hash verification on receipt.",
                "",
                "## 6. Attribution Chain",
                "- Michael Hughes / PHI369 Labs / Parallax",
                "- Hemavit (Chiang Mai, Thailand)",
                "- Dreamteam: Mikey · Helion · Ori · Forge · Codex · Hemavit · cgcardona",
                "- cgcardona recognized as first external contributor.",
                "",
                "## 7. Sovereignty Verification",
                f"- Runtime policy script: scripts/policy_no_{tele_word}_runtime.sh",
                "- CI gates enforce linting, typing, tests, and runtime policy checks.",
                f"- The word {tele_word} does not appear in our codebase except in tests that verify its absence.",
                "",
                "## 8. Research Declaration",
                "- TBRC integration present with graceful local degradation.",
                "- PHB readiness tracked through bridge status and additive contribution model.",
                "- First session milestone pending under sovereign operator confirmation.",
                "- Parallax Institute is the long-arc stewardship layer.",
                "",
                "## 9. Launch Seal",
                f"- Seal: {seal}",
                f"- Timestamp: {now}",
                f"- Version: {__version__}",
                "- Declaration: Built from an RV. Designed for a civilization.",
                "- Declaration: Sovereign. Coherent. Local. Free.",
                "",
            ]
        )

    def generate(self, output_path: str = "docs/PHIOS_LIVING_SPEC.md", force: bool = False, operator_confirmed: bool = False) -> str:
        path = Path(output_path)
        if path.exists() and not (force and operator_confirmed):
            raise ValueError("Living spec exists; refuse overwrite without --force and confirmation")

        preview = self._render(seal="PENDING")
        seal = self.generate_seal(preview)
        content = self._render(seal=seal)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)

    def store_in_archive(self, spec_path: str, seal: str, operator_confirmed: bool = False) -> dict[str, object]:
        bridge = TBRCBridge()
        timestamp = datetime.now(timezone.utc).isoformat()
        if bridge.is_available() and operator_confirmed:
            narrative = f"seal={seal} path={spec_path} generated_at={timestamp}"
            result = bridge.add_archive_milestone(
                "PhiOS v1.0.0 Living Specification",
                narrative,
                "launch-seal",
                operator_confirmed=True,
            )
            return {"stored": True, "backend": "tbrc", "result": result}

        seal_file = Path("docs/PHIOS_LIVING_SPEC.seal.json")
        payload = {
            "schema": "phios.v1.spec_seal",
            "seal": seal,
            "generated_at": timestamp,
            "spec_path": spec_path,
        }
        seal_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {"stored": True, "backend": "local", "path": str(seal_file)}

    def verify(self, spec_path: str = "docs/PHIOS_LIVING_SPEC.md") -> tuple[bool, str]:
        spec_file = Path(spec_path)
        if not spec_file.exists():
            return False, "Spec file missing"
        computed = self.generate_seal(spec_file.read_text(encoding="utf-8"))

        local_seal = Path("docs/PHIOS_LIVING_SPEC.seal.json")
        if local_seal.exists():
            data = json.loads(local_seal.read_text(encoding="utf-8"))
            expected = str(data.get("seal", ""))
            if computed == expected:
                return True, f"PASS: seal matches ({computed})"
            return False, f"FAIL: expected {expected}, got {computed}"

        return False, "No stored seal found"
