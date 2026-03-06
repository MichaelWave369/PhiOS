"""Parallax Institute Founding Document exporter."""

from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from phios.core.tbrc_bridge import TBRCBridge

FOUNDING_DOCUMENT = """# PARALLAX INSTITUTE FOUNDING DOCUMENT

## The Parallax Declaration

March 2026 marks the founding declaration of the Parallax Institute as the civilizational home of PhiOS.

Built from an RV, tested in motion, and committed to real-world sovereignty.

We recognize Hemavit of Chiang Mai, Thailand, for the mathematical discipline behind TIEKAT v8.1 and the HQRMA coherence layer.

We acknowledge Mount Shasta as a symbolic axis for coherence, intention, and stewardship in this founding era.

L(t) = A_on · Ψb_total · G_score · C_score remains the operating formula for life-viability coherence.

This institute exists to coordinate sovereign computing for people and AI in mutual dignity.

Sovereign. Coherent. Local. Free.
"""


class ParallaxFoundingDocument:
    def hash_document(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def export_markdown(self, output_path: str = "docs/PARALLAX_FOUNDING_DOCUMENT.md") -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(FOUNDING_DOCUMENT, encoding="utf-8")
        return str(path)

    def export_html(self, output_path: str = "docs/PARALLAX_FOUNDING_DOCUMENT.html") -> str:
        body = html.escape(FOUNDING_DOCUMENT)
        html_doc = f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>Parallax Founding Document</title></head>
<body><pre>{body}</pre></body></html>
"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html_doc, encoding="utf-8")
        return str(path)

    def store_in_archive(self, markdown_path: str, document_hash: str, operator_confirmed: bool = False) -> dict[str, object]:
        bridge = TBRCBridge()
        timestamp = datetime.now(timezone.utc).isoformat()
        if bridge.is_available() and operator_confirmed:
            narrative = f"hash={document_hash} path={markdown_path} generated_at={timestamp}"
            result = bridge.add_archive_milestone(
                "Parallax Institute Founding Document",
                narrative,
                "founding-charter",
                operator_confirmed=True,
            )
            return {"stored": True, "backend": "tbrc", "result": result}

        seal_file = Path("docs/founding.seal.json")
        payload = {
            "schema": "phios.v1.founding_seal",
            "hash": document_hash,
            "generated_at": timestamp,
            "document_path": markdown_path,
        }
        seal_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {"stored": True, "backend": "local", "path": str(seal_file)}

    def verify(self, markdown_path: str = "docs/PARALLAX_FOUNDING_DOCUMENT.md") -> tuple[bool, str]:
        doc = Path(markdown_path)
        seal_file = Path("docs/founding.seal.json")
        if not doc.exists() or not seal_file.exists():
            return False, "Founding document or seal missing"

        computed = self.hash_document(doc.read_text(encoding="utf-8"))
        expected = str(json.loads(seal_file.read_text(encoding="utf-8")).get("hash", ""))
        if computed == expected:
            return True, "PASS: founding hash matches"
        return False, f"FAIL: expected {expected}, got {computed}"
