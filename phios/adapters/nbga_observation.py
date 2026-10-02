"""Offline NBG-A observations from explicitly selected, pinned public documents.

Document integrity is checked against a packet digest supplied by trusted code or
the caller. It does not verify the underlying field event or initialize PhiKernel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from phios.adapters.nbga import MEMORY_RECEIPT_SCHEMA, GearHop, MemoryReceipt, NBGContractError

PACKET_SCHEMA = "phios.nbga.observation-packet.v1"
RESULT_SCHEMA = "phios.nbga.observation-result.v1"
PACKET_FILENAME = "nbga-virtualbox-observations.json"
PINNED_PACKET_SHA256 = "d61f0bd49de27f770e62d36871dbd335f82684c526a8631b19da6dc2b5651608"
DEFAULT_EVIDENCE_ROOT = Path("/usr/share/phios/nbga")
MAX_DOCUMENT_BYTES = 128 * 1024
MAX_RECORDS = 64
MAX_HOPS = 32
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9:._-]{0,255}\Z")
_FILENAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\.json\Z")


class ObservationUnavailableError(NBGContractError):
    """The entire observation is refused when its public evidence cannot be checked."""


def _keys(value: object, required: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != required:
        raise ObservationUnavailableError("invalid or unknown packet fields")
    return value


def _text(value: object, *, identifier: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservationUnavailableError("invalid observation text")
    try:
        oversized = len(value.encode("utf-8")) > 4096
    except UnicodeError as exc:
        raise ObservationUnavailableError("invalid observation text encoding") from exc
    if oversized or (identifier and not _IDENTIFIER.fullmatch(value)):
        raise ObservationUnavailableError("observation text exceeds its allowed format")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ObservationUnavailableError("a full lowercase SHA-256 pin is required")
    return value


def _integer(value: object, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ObservationUnavailableError("invalid bounded integer")
    return value


def _array(value: object, *, maximum: int = MAX_RECORDS, allow_empty: bool = False) -> list[object]:
    if not isinstance(value, list) or len(value) > maximum or (not value and not allow_empty):
        raise ObservationUnavailableError("invalid bounded observation array")
    return value


def _json(raw: bytes) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ObservationUnavailableError("duplicate JSON field")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise ObservationUnavailableError("non-finite JSON number")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ObservationUnavailableError):
            raise
        raise ObservationUnavailableError("invalid public observation JSON") from exc


def _read(root: Path, filename: str) -> bytes:
    # Only a basename is accepted. No paths, discovery, URLs or subprocesses.
    if not _FILENAME.fullmatch(filename):
        raise ObservationUnavailableError("invalid evidence filename")
    path = root / filename
    try:
        if path.is_symlink():
            raise ObservationUnavailableError("symbolic-link evidence is refused")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_DOCUMENT_BYTES:
                raise ObservationUnavailableError("evidence must be a bounded regular file")
            raw = stream.read(MAX_DOCUMENT_BYTES + 1)
            after = os.fstat(stream.fileno())
        if (len(raw) != before.st_size or len(raw) > MAX_DOCUMENT_BYTES
                or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
            raise ObservationUnavailableError("evidence changed during its read")
        return raw
    except OSError as exc:
        # Do not echo host paths or arbitrary file contents in refusal output.
        raise ObservationUnavailableError("public evidence file unavailable") from exc


@dataclass(frozen=True, slots=True)
class EvidencePin:
    id: str
    filename: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ObservationReport:
    packet_id: str
    packet_sha256: str
    evidence: tuple[EvidencePin, ...]
    receipts: tuple[MemoryReceipt, ...]

    def to_payload(self) -> dict[str, object]:
        receipts = []
        for receipt in self.receipts:
            payload = {"schema_version": MEMORY_RECEIPT_SCHEMA, **asdict(receipt)}
            payload["evidence"] = list(receipt.evidence)
            payload["gear_path"] = [asdict(hop) for hop in receipt.gear_path]
            receipts.append(payload)
        return {
            "schema_version": RESULT_SCHEMA,
            "packet_id": self.packet_id,
            "packet_sha256": self.packet_sha256,
            "provider_mode": "read-only",
            "evidence_integrity": "verified-against-pins",
            "checked_documents": [asdict(pin) for pin in self.evidence],
            "observations": receipts,
            "bubble_zero": {"availability": "unavailable", "reason": "no continuity backend"},
            "release_ready": False,
            "publication_authority": False,
        }


def observe(
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    *,
    expected_packet_sha256: str = PINNED_PACKET_SHA256,
    bubble_id: str | None = None,
) -> ObservationReport:
    """Read the whole pinned packet before returning any selected observation.

    A custom pin is a caller-owned trust input, never a value accepted from the
    packet itself. Success checks documentary bytes, not truth or release readiness.
    """
    expected = _digest(expected_packet_sha256)
    try:
        root = evidence_root.resolve(strict=True)
        if not root.is_dir():
            raise ObservationUnavailableError("an explicit evidence directory is required")
    except (OSError, ValueError, RuntimeError) as exc:
        raise ObservationUnavailableError("public evidence directory unavailable") from exc
    raw = _read(root, PACKET_FILENAME)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ObservationUnavailableError("observation packet integrity mismatch")
    packet = _keys(_json(raw), {"schema_version", "packet_id", "evidence", "observations"})
    if packet["schema_version"] != PACKET_SCHEMA:
        raise ObservationUnavailableError("unsupported observation packet schema")
    packet_id = _text(packet["packet_id"], identifier=True)
    pins: dict[str, EvidencePin] = {}
    filenames: set[str] = set()
    for item in _array(packet["evidence"]):
        row = _keys(item, {"id", "filename", "sha256", "size_bytes"})
        pin = EvidencePin(_text(row["id"], identifier=True), _text(row["filename"]),
                          _digest(row["sha256"]), _integer(row["size_bytes"], MAX_DOCUMENT_BYTES))
        if pin.id in pins or pin.filename in filenames:
            raise ObservationUnavailableError("duplicate evidence identity or filename")
        data = _read(root, pin.filename)
        if len(data) != pin.size_bytes or hashlib.sha256(data).hexdigest() != pin.sha256:
            raise ObservationUnavailableError("evidence document integrity mismatch")
        pins[pin.id] = pin
        filenames.add(pin.filename)

    rows = [_keys(row, {"bubble_id", "bubble_version", "observable", "trust_state", "evidence",
                       "gear_path", "event_head"}) for row in _array(packet["observations"])]
    identities = [_text(row["bubble_id"], identifier=True) for row in rows]
    if len(set(identities)) != len(identities):
        raise ObservationUnavailableError("duplicate observation bubble")
    lineage = {identity: {_text(ref, identifier=True) for ref in _array(row["evidence"])}
               for identity, row in zip(identities, rows, strict=True)}
    used: set[str] = set()
    definitions: dict[str, GearHop] = {}
    receipts = []
    for row, identity in zip(rows, identities, strict=True):
        references = tuple(_text(ref, identifier=True) for ref in _array(row["evidence"]))
        if len(set(references)) != len(references) or any(ref not in pins for ref in references):
            raise ObservationUnavailableError("missing or repeated evidence reference")
        used.update(references)
        event_head = _text(row["event_head"], identifier=True)
        if event_head != references[-1]:
            raise ObservationUnavailableError("documentary head must resolve to the final evidence")
        trust_state = row["trust_state"]
        if trust_state not in ("owner-reported", "reviewed-ci-record"):
            raise ObservationUnavailableError("unsupported observation trust state")
        hops = tuple(GearHop.from_payload(hop) for hop in
                     _array(row["gear_path"], maximum=MAX_HOPS, allow_empty=True))
        visited: set[str] = set()
        for index, hop in enumerate(hops):
            for value in (hop.gear_id, hop.source, hop.destination):
                _text(value, identifier=True)
            if hop.transform != "documented-follow-up":
                raise ObservationUnavailableError("unsupported documentary transformation")
            if hop.source not in identities or hop.destination not in identities:
                raise ObservationUnavailableError("gear path references an unknown bubble")
            if not (lineage[hop.source] | lineage[hop.destination]).issubset(references):
                raise ObservationUnavailableError("gear lineage evidence is missing")
            if index and hop.source != hops[index - 1].destination:
                raise ObservationUnavailableError("disconnected directional gear path")
            visited.add(hop.source)
            if hop.destination in visited:
                raise ObservationUnavailableError("cyclic directional gear path")
            prior = definitions.setdefault(hop.gear_id, hop)
            if prior != hop:
                raise ObservationUnavailableError("conflicting gear definition")
        if hops and hops[-1].destination != identity:
            raise ObservationUnavailableError("gear path does not end at its observation")
        provenance = json.dumps({"schema_version": "phios.nbga.document-provenance.v1",
            "packet_sha256": expected, "evidence": [asdict(pins[ref]) for ref in references]},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        receipts.append(MemoryReceipt.from_payload({
            "schema_version": MEMORY_RECEIPT_SCHEMA, "bubble_id": identity,
            "bubble_version": _integer(row["bubble_version"], 2**53 - 1),
            "observable": _text(row["observable"]), "trust_state": trust_state,
            "confidence": None, "evidence": list(references),
            "gear_path": [asdict(hop) for hop in hops], "event_head": event_head,
            "provenance_root": "sha256:" + hashlib.sha256(provenance).hexdigest(),
        }))
    if used != set(pins):
        raise ObservationUnavailableError("unreferenced evidence document")
    if bubble_id is not None:
        selected = _text(bubble_id, identifier=True)
        receipts = [receipt for receipt in receipts if receipt.bubble_id == selected]
        if not receipts:
            raise ObservationUnavailableError("unknown observation bubble")
    return ObservationReport(packet_id, expected, tuple(pins.values()), tuple(receipts))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read pinned public NBG-A qualification observations")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--bubble-id", help="Select a bubble after checking the entire evidence packet")
    args = parser.parse_args(argv)
    try:
        result = observe(args.evidence_root, bubble_id=args.bubble_id).to_payload()
    except NBGContractError as exc:
        print(json.dumps({"schema_version": RESULT_SCHEMA, "availability": "unavailable",
                          "reason": str(exc), "release_ready": False,
                          "publication_authority": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
