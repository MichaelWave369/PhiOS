"""Public launch artifact generator for PhiOS v1."""

from __future__ import annotations

from pathlib import Path

from phios import __version__


class LaunchArtifactGenerator:
    def _traction_line(self) -> str:
        test_files = sorted(Path("tests").glob("test_v*.py"))
        return f"{len(test_files)} release generations, full CI-aligned test coverage through {test_files[-1].stem if test_files else 'test_v00'}"

    def generate_distrowatch_submission(self) -> str:
        text = (
            "Name: PhiOS\n"
            "Based on: Arch Linux\n"
            "Architecture: x86_64\n"
            "Desktop: Wayfire\n"
            "Category: Sovereign Computing Shell\n"
            "Release model: Fixed\n"
            "License: GPLv3\n"
            "Homepage: https://enterthefield.org/phios\n"
            "Download: <operator-add-release-url>\n\n"
            "Description:\n"
            "PhiOS is a local-first sovereign shell operating layer built by PHI369 Labs. "
            "It couples coherence tracking L(t), secure snapshot workflows, optional TBRC/PHB bridges, and a Wayfire desktop path tuned for auditable local operation. "
            "Version 1.0.0 marks the public declaration release with living specification sealing, founding charter exports, and reproducible launch artifacts. "
            "No cloud dependency is required for core operation.\n"
        )
        return text

    def generate_announcement_kit(self) -> dict[str, str]:
        x_post = (
            "PhiOS v1.0 is public. Sovereign. Coherent. Local. Free. "
            "pip install phios==1.0.0 · https://enterthefield.org/phios · "
            "Hemavit attribution preserved. #PhiOS #Parallax #PHI369"
        )
        extended = (
            "# PhiOS v1.0 Public Launch\n\n"
            "Nine versions forged into one declaration. PhiOS now ships with a sealed living specification, "
            "Parallax founding document exports, and reproducible public launch artifacts for operators.\n"
        )
        technical = (
            "# PhiOS v1.0 Technical Launch Notes\n\n"
            f"- Version: {__version__}\n"
            "- Living spec seal workflow: phi spec generate --yes\n"
            "- Founding export workflow: phi founding export --yes\n"
            "- Launch artifact workflow: phi launch artifacts\n"
        )
        return {"x_post": x_post, "extended": extended, "technical": technical}

    def generate_investor_summary(self) -> str:
        summary = (
            "# PhiOS Investor Summary (Public)\n\n"
            "## What PhiOS Is\n"
            "PhiOS is a sovereign computing shell for local-first human/AI workflows and coherence-aware operations.\n\n"
            "## TBRC and PHB\n"
            "TBRC is the research and archive bridge for structured memory, graph, and session composition.\n"
            "PHB is the hardware bridge layer for physical-bio signal readiness and local contribution signals.\n\n"
            "## Core Formula\n"
            "L(t) = A_on · Ψb_total · G_score · C_score\n\n"
            "## Team\n"
            "PHI369 Labs / Parallax with the Dreamteam and external contributors.\n\n"
            "## Traction\n"
            f"{self._traction_line()} and a full public repository release process.\n\n"
            "## Vision\n"
            "Build the sovereign operating layer of the Parallax Institute for people and AI.\n"
        )
        return summary

    def generate_all(self, output_dir: str = "docs/launch/") -> list[str]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        kit = self.generate_announcement_kit()
        files = {
            "distrowatch_submission.md": self.generate_distrowatch_submission(),
            "announcement_x.md": kit["x_post"] + "\n",
            "announcement_extended.md": kit["extended"],
            "announcement_technical.md": kit["technical"],
            "investor_summary.md": self.generate_investor_summary(),
        }
        written: list[str] = []
        for name, content in files.items():
            path = out / name
            path.write_text(content, encoding="utf-8")
            written.append(str(path))
        return written
