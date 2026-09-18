from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .models import NativeEvidence


class NativeEvidenceStore:
    """Content-addressed store that preserves native perception input bytes."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()

    def put_text(self, text: str) -> NativeEvidence:
        data = text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{digest}.txt"

        if not path.exists():
            fd, temp_name = tempfile.mkstemp(prefix=".evidence-", dir=self.root)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)

        stored = path.read_bytes()
        stored_digest = hashlib.sha256(stored).hexdigest()
        if stored_digest != digest:
            raise RuntimeError("native evidence digest mismatch")

        return NativeEvidence(
            evidence_ref=f"evidence:sha256:{digest}",
            sha256=digest,
            path=str(path),
            media_type="text/plain; charset=utf-8",
            size_bytes=len(data),
        )
