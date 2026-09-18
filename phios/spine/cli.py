from __future__ import annotations

import argparse
import json
from pathlib import Path

from phios.mandala import MANDALA_CONTRACT_VERSION, Gate, MandalaStatus
from phios.reality import (
    JSON_SCALAR_PREDICATES,
    JSON_STRUCTURAL_PREDICATES,
    JSON_TYPE_NAMES,
    JsonContractClause,
    JsonMixedContractClause,
    RealityClaim,
    RealityClaimKind,
    StdlibLoopbackHttpStateProvider,
)
from phios.soma import OcrSpec, ScreenCrop, ScreenEnhancementSpec, ScreenRegion

from . import __version__ as SPINE_VERSION
from .runtime import PhiOSSpine


def _runtime(args: argparse.Namespace) -> PhiOSSpine:
    root = Path(args.state_root).expanduser() if args.state_root else None
    return PhiOSSpine(state_root=root, allowed_permissions=args.allow or ())


def _json_contract_clauses(
    parser: argparse.ArgumentParser,
    raw_clauses: list[str],
) -> tuple[JsonContractClause, ...]:
    clauses: list[JsonContractClause] = []
    for index, raw in enumerate(raw_clauses):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            parser.error(f"--json-clause {index} is not valid JSON: {exc.msg}")
        if not isinstance(value, dict):
            parser.error(f"--json-clause {index} must decode to a JSON object")
        try:
            clause = JsonContractClause.from_mapping(value)
        except ValueError as exc:
            parser.error(f"--json-clause {index}: {exc}")
        clauses.append(clause)
    return tuple(clauses)


def _json_mixed_contract_clauses(
    parser: argparse.ArgumentParser,
    raw_clauses: list[str],
) -> tuple[JsonMixedContractClause, ...]:
    clauses: list[JsonMixedContractClause] = []
    for index, raw in enumerate(raw_clauses):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            parser.error(
                f"--json-mixed-clause {index} is not valid JSON: {exc.msg}"
            )
        if not isinstance(value, dict):
            parser.error(
                f"--json-mixed-clause {index} must decode to a JSON object"
            )
        try:
            clause = JsonMixedContractClause.from_mapping(value)
        except ValueError as exc:
            parser.error(f"--json-mixed-clause {index}: {exc}")
        clauses.append(clause)
    return tuple(clauses)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phi-spine", description="PhiOS Spine v0.20")
    parser.add_argument("--state-root", help="Override the PhiOS Spine local state root")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="PERMISSION",
        help="Explicitly grant one permission for this invocation (repeatable)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show the v0.20 spine and Mandala contract state")
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
    verify_claim.add_argument(
        "--interface-name",
        help="Required for local_interface_state claims",
    )
    verify_claim.add_argument(
        "--expected-state",
        choices=["up", "down"],
        help="Required for local_interface_state claims",
    )
    verify_claim.add_argument(
        "--local-port",
        type=int,
        help="Required for local_tcp_listener_state claims",
    )
    verify_claim.add_argument(
        "--local-address",
        help="Optional exact local address filter for local_tcp_listener_state",
    )
    verify_claim.add_argument(
        "--expected-listening",
        choices=["yes", "no"],
        help="Required for local_tcp_listener_state claims",
    )
    verify_claim.add_argument(
        "--http-url",
        help="Required loopback HTTP URL for local HTTP claim kinds",
    )
    verify_claim.add_argument(
        "--expected-http-status",
        type=int,
        help="Required exact HTTP status for local HTTP claim kinds",
    )
    verify_claim.add_argument("--http-timeout", type=float, default=2.0)
    verify_claim.add_argument("--http-max-body-bytes", type=int, default=65_536)
    verify_claim.add_argument(
        "--json-pointer",
        help="Required RFC-6901-style pointer for semantic local HTTP JSON claims",
    )
    verify_claim.add_argument(
        "--expected-json-type",
        choices=sorted(JSON_TYPE_NAMES),
        help="Required JSON type at --json-pointer for local_http_json_contract claims",
    )
    verify_claim.add_argument(
        "--json-predicate",
        choices=sorted(JSON_STRUCTURAL_PREDICATES),
        help="Required structural predicate for local_http_json_predicate claims",
    )
    verify_claim.add_argument(
        "--json-predicate-bound",
        type=int,
        help="Integer bound required by length/key-count JSON predicates",
    )
    verify_claim.add_argument(
        "--json-clause",
        action="append",
        default=[],
        metavar="JSON",
        help=(
            "Repeatable clause for local_http_json_multi_contract. "
            'Examples: {"pointer":"/models","type":"array"} or '
            '{"pointer":"/models","predicate":"array_length_gte","bound":1}'
        ),
    )
    verify_claim.add_argument(
        "--json-scalar-predicate",
        choices=sorted(JSON_SCALAR_PREDICATES),
        help="Required bounded scalar predicate for local_http_json_scalar_predicate claims",
    )
    verify_claim.add_argument(
        "--json-scalar-operand",
        help="Numeric operand required by integer/number scalar predicates",
    )
    verify_claim.add_argument(
        "--json-mixed-clause",
        action="append",
        default=[],
        metavar="JSON",
        help=(
            "Repeatable clause for local_http_json_mixed_contract. "
            'Examples: {"pointer":"/models","type":"array"}, '
            '{"pointer":"/models","predicate":"array_length_gte","bound":1}, '
            'or {"pointer":"/ready","scalar_predicate":"boolean_is_true"}'
        ),
    )
    verify_claim.add_argument(
        "--observation-count",
        type=int,
        help=(
            "Required 2-5 provider observations for "
            "local_http_json_repeated_mixed_contract"
        ),
    )
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
                    "reality_gate": "reality.bounded-evidence.v0.10",
                    "world_verifiers": [
                        "local-interface-state.v0.1",
                        "local-tcp-listener-state.v0.1",
                        "local-http-response-contract.v0.1",
                        "local-http-response-stdlib-loopback.v0.1",
                        "local-http-json-contract.v0.1",
                        "local-http-json-structural-predicate.v0.1",
                        "local-http-json-multi-contract.v0.1",
                        "local-http-json-scalar-predicate.v0.1",
                        "local-http-json-mixed-contract.v0.1",
                        "local-http-json-repeated-mixed-contract.v0.1",
                    ],
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
        json_contract_clauses = _json_contract_clauses(
            parser,
            args.json_clause,
        )
        json_mixed_contract_clauses = _json_mixed_contract_clauses(
            parser,
            args.json_mixed_clause,
        )
        claim = RealityClaim.create(
            kind=RealityClaimKind(args.kind),
            statement=args.statement,
            evidence_refs=tuple(args.evidence_ref),
            expected_text=args.expected_text,
            case_sensitive=args.case_sensitive,
            interface_name=args.interface_name,
            expected_is_up=(
                True
                if args.expected_state == "up"
                else False
                if args.expected_state == "down"
                else None
            ),
            local_port=args.local_port,
            local_address=args.local_address,
            expected_listening=(
                True
                if args.expected_listening == "yes"
                else False
                if args.expected_listening == "no"
                else None
            ),
            http_url=args.http_url,
            expected_http_status=args.expected_http_status,
            http_timeout_seconds=args.http_timeout,
            http_max_body_bytes=args.http_max_body_bytes,
            json_pointer=args.json_pointer,
            expected_json_type=args.expected_json_type,
            json_predicate_kind=args.json_predicate,
            json_predicate_bound=args.json_predicate_bound,
            json_contract_clauses=json_contract_clauses,
            json_scalar_predicate_kind=args.json_scalar_predicate,
            json_scalar_operand=args.json_scalar_operand,
            json_mixed_contract_clauses=json_mixed_contract_clauses,
            repeat_observation_count=args.observation_count,
        )
        verification_result = runtime.verify_reality(
            claims=(claim,),
            max_evidence_bytes=args.max_evidence_bytes,
            local_http_provider=(
                StdlibLoopbackHttpStateProvider()
                if args.kind
                in {
                    RealityClaimKind.LOCAL_HTTP_RESPONSE_STATE.value,
                    RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT.value,
                    RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE.value,
                    RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT.value,
                    RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE.value,
                    RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT.value,
                    RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT.value,
                }
                else None
            ),
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
