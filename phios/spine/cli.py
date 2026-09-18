from __future__ import annotations

import argparse
import json
from pathlib import Path

from phios.mandala import MANDALA_CONTRACT_VERSION, Gate, MandalaStatus
from phios.reality import RealityClaim, RealityClaimKind
from phios.soma import OcrSpec, ScreenCrop, ScreenEnhancementSpec, ScreenRegion

from . import __version__ as SPINE_VERSION
from .runtime import PhiOSSpine


def _runtime(args: argparse.Namespace) -> PhiOSSpine:
    root = Path(args.state_root).expanduser() if args.state_root else None
    return PhiOSSpine(state_root=root, allowed_permissions=args.allow or ())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phi-spine", description="PhiOS Spine v0.10")
    parser.add_argument("--state-root", help="Override the PhiOS Spine local state root")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="PERMISSION",
        help="Explicitly grant one permission for this invocation (repeatable)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show the v0.10 spine and Mandala contract state")
    sub.add_parser("list", help="List registered capabilities")

    perceive = sub.add_parser(
        "perceive",
        help="Admit text through the SOMA North Gate with native provenance",
    )
    perceive.add_argument("--source-id", required=True)
    perceive.add_argument("--text", required=True)
    perceive.add_argument(
        "--transform",
        action="append",
        default=[],
        choices=["strip_utf8_bom", "normalize_newlines"],
        help="Apply one deterministic recovery transform (repeatable)",
    )

    perceive_file = sub.add_parser(
        "perceive-file",
        help="Acquire one bounded text-like file through the SOMA North Gate",
    )
    perceive_file.add_argument("--root", required=True, help="Explicit source root")
    perceive_file.add_argument("--path", required=True, help="Path relative to --root")
    perceive_file.add_argument("--max-bytes", type=int, default=1_048_576)
    perceive_file.add_argument(
        "--transform",
        action="append",
        default=[],
        choices=["strip_utf8_bom", "normalize_newlines"],
        help="Apply one deterministic recovery transform (repeatable)",
    )

    perceive_screen = sub.add_parser(
        "perceive-screen",
        help="Capture one explicitly selected desktop region through the SOMA North Gate",
    )
    perceive_screen.add_argument("--x", type=int, required=True)
    perceive_screen.add_argument("--y", type=int, required=True)
    perceive_screen.add_argument("--width", type=int, required=True)
    perceive_screen.add_argument("--height", type=int, required=True)
    perceive_screen.add_argument("--max-pixels", type=int, default=8_294_400)
    perceive_screen.add_argument("--reacquire-attempts", type=int, default=1)

    perceive_burst = sub.add_parser(
        "perceive-screen-burst",
        help="Capture a bounded burst and select the sharpest valid native frame",
    )
    perceive_burst.add_argument("--x", type=int, required=True)
    perceive_burst.add_argument("--y", type=int, required=True)
    perceive_burst.add_argument("--width", type=int, required=True)
    perceive_burst.add_argument("--height", type=int, required=True)
    perceive_burst.add_argument("--frames", type=int, default=3)
    perceive_burst.add_argument("--max-pixels", type=int, default=8_294_400)
    perceive_burst.add_argument("--max-total-pixels", type=int, default=33_177_600)

    ocr_screen = sub.add_parser(
        "ocr-screen",
        help="Interpret preserved PNG evidence as text through an explicit OCR receipt",
    )
    ocr_screen.add_argument("--evidence-ref", required=True)
    ocr_screen.add_argument("--language", default="eng")
    ocr_screen.add_argument("--psm", type=int, default=6)
    ocr_screen.add_argument("--max-pixels", type=int, default=16_777_216)

    enhance_screen = sub.add_parser(
        "enhance-screen",
        help="Create a bounded deterministic sharpened derivative from preserved evidence",
    )
    enhance_screen.add_argument("--evidence-ref", required=True)
    enhance_screen.add_argument("--radius", type=float, default=1.5)
    enhance_screen.add_argument("--percent", type=int, default=150)
    enhance_screen.add_argument("--threshold", type=int, default=3)
    enhance_screen.add_argument("--max-pixels", type=int, default=16_777_216)

    recover_screen = sub.add_parser(
        "recover-screen",
        help="Derive a tight crop and/or native enlargement from preserved screen evidence",
    )
    recover_screen.add_argument("--evidence-ref", required=True)
    recover_screen.add_argument("--crop-x", type=int)
    recover_screen.add_argument("--crop-y", type=int)
    recover_screen.add_argument("--crop-width", type=int)
    recover_screen.add_argument("--crop-height", type=int)
    recover_screen.add_argument("--scale", type=int, default=1)
    recover_screen.add_argument("--max-output-pixels", type=int, default=16_777_216)

    verify_claim = sub.add_parser(
        "verify-claim",
        help="Evaluate a bounded claim through the Reality Gate bridge",
    )
    verify_claim.add_argument(
        "--kind",
        required=True,
        choices=[item.value for item in RealityClaimKind],
    )
    verify_claim.add_argument("--statement", required=True)
    verify_claim.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Cited evidence reference (repeatable)",
    )
    verify_claim.add_argument(
        "--expected-text",
        help="Required for source_contains_text claims",
    )
    verify_claim.add_argument("--case-sensitive", action="store_true")
    verify_claim.add_argument("--max-evidence-bytes", type=int, default=1_048_576)

    run = sub.add_parser("run", help="Plan, authorize, execute, and receipt a capability")
    run.add_argument("capability_id")
    run.add_argument("--input", default="{}", help="JSON object payload")

    ledger = sub.add_parser("ledger", help="Show recent legacy execution receipts")
    ledger.add_argument("--limit", type=int, default=10)

    mandala = sub.add_parser("mandala-ledger", help="Show recent typed Mandala receipts")
    mandala.add_argument("--limit", type=int, default=10)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    runtime = _runtime(args)

    if args.command == "status":
        print(
            json.dumps(
                {
                    "version": SPINE_VERSION,
                    "state_root": str(runtime.state_root),
                    "capability_count": len(runtime.registry.list()),
                    "legacy_ledger": str(runtime.ledger.path),
                    "mandala_ledger": str(runtime.mandala_ledger.path),
                    "native_evidence_root": str(runtime.soma.evidence.root),
                    "mandala_contract": MANDALA_CONTRACT_VERSION,
                    "task_id": runtime.core.task_id,
                    "core_lifecycle": runtime.core.lifecycle.value,
                    "gates": [gate.value for gate in Gate],
                    "statuses": [status.value for status in MandalaStatus],
                    "north_gate": "soma.text.v0.1+soma.file.v0.1+soma.screen.v0.1+soma.recovery.v0.1+soma.multishot.v0.1+soma.enhancement.v0.1+soma.ocr.v0.1",
                    "reality_gate": "reality.bounded-text-evidence.v0.1",
                },
                indent=2,
            )
        )
        return 0

    if args.command == "list":
        print(json.dumps([item.to_dict() for item in runtime.registry.list()], indent=2))
        return 0

    if args.command == "perceive":
        result = runtime.perceive_text(
            source_id=args.source_id,
            text=args.text,
            transforms=tuple(args.transform),
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.receipt.status in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED} else 2

    if args.command == "perceive-file":
        file_result = runtime.perceive_file(
            source_root=Path(args.root).expanduser(),
            relative_path=args.path,
            transforms=tuple(args.transform),
            max_bytes=args.max_bytes,
        )
        print(json.dumps(file_result.to_dict(), indent=2))
        return (
            0
            if file_result.receipt.status in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED}
            else 2
        )

    if args.command == "perceive-screen":
        screen_result = runtime.perceive_screen(
            region=ScreenRegion(
                x=args.x,
                y=args.y,
                width=args.width,
                height=args.height,
            ),
            max_pixels=args.max_pixels,
            reacquire_attempts=args.reacquire_attempts,
        )
        print(json.dumps(screen_result.to_dict(), indent=2))
        return (
            0
            if screen_result.receipt.status
            in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED}
            else 2
        )

    if args.command == "perceive-screen-burst":
        burst_result = runtime.perceive_screen_burst(
            region=ScreenRegion(
                x=args.x,
                y=args.y,
                width=args.width,
                height=args.height,
            ),
            frame_count=args.frames,
            max_pixels=args.max_pixels,
            max_total_pixels=args.max_total_pixels,
        )
        print(json.dumps(burst_result.to_dict(), indent=2))
        return (
            0
            if burst_result.receipt.status
            in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED}
            else 2
        )

    if args.command == "ocr-screen":
        ocr_result = runtime.ocr_screen_evidence(
            evidence_ref=args.evidence_ref,
            spec=OcrSpec(
                language=args.language,
                page_segmentation_mode=args.psm,
                max_pixels=args.max_pixels,
            ),
        )
        print(json.dumps(ocr_result.to_dict(include_text=True), indent=2))
        return (
            0
            if ocr_result.receipt.status
            in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED}
            else 2
        )

    if args.command == "enhance-screen":
        enhancement_result = runtime.enhance_screen_evidence(
            evidence_ref=args.evidence_ref,
            spec=ScreenEnhancementSpec(
                radius=args.radius,
                percent=args.percent,
                threshold=args.threshold,
                max_pixels=args.max_pixels,
            ),
        )
        print(json.dumps(enhancement_result.to_dict(), indent=2))
        return (
            0
            if enhancement_result.receipt.status
            in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED}
            else 2
        )

    if args.command == "recover-screen":
        crop_values = (
            args.crop_x,
            args.crop_y,
            args.crop_width,
            args.crop_height,
        )
        if any(value is not None for value in crop_values) and not all(
            value is not None for value in crop_values
        ):
            parser.error(
                "--crop-x, --crop-y, --crop-width, and --crop-height must be supplied together"
            )
        crop = (
            ScreenCrop(
                x=args.crop_x,
                y=args.crop_y,
                width=args.crop_width,
                height=args.crop_height,
            )
            if all(value is not None for value in crop_values)
            else None
        )
        recovery_result = runtime.recover_screen_evidence(
            evidence_ref=args.evidence_ref,
            crop=crop,
            scale=args.scale,
            max_output_pixels=args.max_output_pixels,
        )
        print(json.dumps(recovery_result.to_dict(), indent=2))
        return (
            0
            if recovery_result.receipt.status
            in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED}
            else 2
        )

    if args.command == "verify-claim":
        claim = RealityClaim.create(
            kind=RealityClaimKind(args.kind),
            statement=args.statement,
            evidence_refs=tuple(args.evidence_ref),
            expected_text=args.expected_text,
            case_sensitive=args.case_sensitive,
        )
        verification_result = runtime.verify_reality(
            claims=(claim,),
            max_evidence_bytes=args.max_evidence_bytes,
        )
        print(json.dumps(verification_result.to_dict(), indent=2))
        return (
            0
            if verification_result.receipt.status
            in {
                MandalaStatus.ACCEPTED,
                MandalaStatus.UNKNOWN,
                MandalaStatus.DISPUTED,
            }
            else 2
        )

    if args.command == "run":
        payload = json.loads(args.input)
        if not isinstance(payload, dict):
            parser.error("--input must decode to a JSON object")
        receipt = runtime.run(args.capability_id, payload)
        print(json.dumps(receipt.to_dict(), indent=2))
        return 0 if receipt.execution_status == "succeeded" else 2

    if args.command == "ledger":
        print(json.dumps(runtime.ledger.recent(args.limit), indent=2))
        return 0

    if args.command == "mandala-ledger":
        print(json.dumps(runtime.mandala_ledger.recent(args.limit), indent=2))
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
