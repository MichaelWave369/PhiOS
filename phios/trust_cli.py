from __future__ import annotations

import argparse
import json
from pathlib import Path

from phios.phivessel_local_execution import execution_manifest_path
from phios.trust_operator import (
    PhiVesselTrustOperator,
    PhiVesselTrustOperatorError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phi-trust",
        description=(
            "Operate the sealed local PhiVessel execution manifest and "
            "AuthorityEpoch."
        ),
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path.home() / ".phios",
        help="PhiOS state root (default: ~/.phios)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=(
            "Override the PhiVessel execution manifest path. "
            "Defaults to PHIOS_PHIVESSEL_EXECUTION_MANIFEST or "
            "<state-root>/config/phivessel-execution.json."
        ),
    )
    parser.add_argument(
        "--actor-id",
        default="operator:local",
        help="Local human operator identity written to trust receipts.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "status",
        help="Show sealed execution, mappings, policies, and authority state.",
    )
    sub.add_parser(
        "validate",
        help="Validate manifest and materialized authority-event state.",
    )
    sub.add_parser(
        "recover",
        help="Complete one previously prepared trust mutation.",
    )

    bootstrap = sub.add_parser(
        "authority-bootstrap",
        help=(
            "Explicitly migrate the currently validated AuthorityEpoch "
            "into the v0.37 local authority-event store."
        ),
    )
    _add_expected_manifest(bootstrap)

    grant = sub.add_parser(
        "grant",
        help="Append one authoritative local permission grant and rotate the epoch.",
    )
    grant.add_argument("permission")
    grant.add_argument(
        "--expires-at",
        help="Optional timezone-aware ISO-8601 grant expiry.",
    )
    _add_expected_manifest(grant)

    revoke = sub.add_parser(
        "revoke",
        help="Append one authoritative local permission revocation and rotate the epoch.",
    )
    revoke.add_argument("permission")
    _add_expected_manifest(revoke)

    refresh = sub.add_parser(
        "refresh-epoch",
        help="Recompute the current AuthorityEpoch from stored events.",
    )
    _add_expected_manifest(refresh)

    enable = sub.add_parser(
        "enable",
        help=(
            "Enable trusted PhiVessel execution and the desktop executor. "
            "Static trust change: host restart required."
        ),
    )
    _add_expected_manifest(enable)

    disable = sub.add_parser(
        "disable",
        help=(
            "Disable trusted PhiVessel execution and the desktop executor. "
            "Static trust change: host restart required."
        ),
    )
    _add_expected_manifest(disable)

    sub.add_parser(
        "mappings",
        help="Show trusted semantic-intent to capability mappings.",
    )
    sub.add_parser(
        "policies",
        help="Show trusted ActionLease policies.",
    )
    sub.add_parser(
        "epoch",
        help="Show the currently materialized AuthorityEpoch.",
    )

    return parser


def _add_expected_manifest(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--expect-manifest-sha",
        required=True,
        dest="expected_manifest_sha256",
        help=(
            "Current manifest SHA-256 from 'phi-trust status'. "
            "Mutation fails if it changed."
        ),
    )


def _operator(args: argparse.Namespace) -> PhiVesselTrustOperator:
    state_root = Path(args.state_root).expanduser()
    manifest = (
        Path(args.manifest).expanduser()
        if args.manifest is not None
        else execution_manifest_path(
            state_root=state_root,
        )
    )
    return PhiVesselTrustOperator.for_manifest(
        manifest_path=manifest,
        state_root=state_root,
        actor_id=args.actor_id,
    )


def _print(value: object) -> None:
    print(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    operator = _operator(args)

    try:
        if args.command == "status":
            _print(operator.status())
            return 0

        if args.command == "validate":
            _print(operator.validate())
            return 0

        if args.command == "recover":
            _print(operator.recover().to_dict())
            return 0

        if args.command == "authority-bootstrap":
            _print(
                operator.bootstrap_authority(
                    expected_manifest_sha256=(
                        args.expected_manifest_sha256
                    )
                ).to_dict()
            )
            return 0

        if args.command == "grant":
            _print(
                operator.grant(
                    permission=args.permission,
                    expires_at=args.expires_at,
                    expected_manifest_sha256=(
                        args.expected_manifest_sha256
                    ),
                ).to_dict()
            )
            return 0

        if args.command == "revoke":
            _print(
                operator.revoke(
                    permission=args.permission,
                    expected_manifest_sha256=(
                        args.expected_manifest_sha256
                    ),
                ).to_dict()
            )
            return 0

        if args.command == "refresh-epoch":
            _print(
                operator.refresh_epoch(
                    expected_manifest_sha256=(
                        args.expected_manifest_sha256
                    )
                ).to_dict()
            )
            return 0

        if args.command == "enable":
            _print(
                operator.set_execution_enabled(
                    enabled=True,
                    expected_manifest_sha256=(
                        args.expected_manifest_sha256
                    ),
                ).to_dict()
            )
            return 0

        if args.command == "disable":
            _print(
                operator.set_execution_enabled(
                    enabled=False,
                    expected_manifest_sha256=(
                        args.expected_manifest_sha256
                    ),
                ).to_dict()
            )
            return 0

        status = operator.status()
        if not status.get("manifest_present"):
            raise PhiVesselTrustOperatorError(
                "execution manifest is not present"
            )

        if args.command == "mappings":
            _print(
                {
                    "manifest_sha256": status.get("manifest_sha256"),
                    "mappings": status.get("mappings", []),
                }
            )
            return 0

        if args.command == "policies":
            _print(
                {
                    "manifest_sha256": status.get("manifest_sha256"),
                    "lease_policies": status.get(
                        "lease_policies",
                        [],
                    ),
                }
            )
            return 0

        if args.command == "epoch":
            _print(
                {
                    "manifest_sha256": status.get("manifest_sha256"),
                    "authority_epoch": status.get("authority_epoch"),
                    "authority_state_present": status.get(
                        "authority_state_present"
                    ),
                    "authority_state_sha256": status.get(
                        "authority_state_sha256"
                    ),
                    "authority_state_error": status.get(
                        "authority_state_error"
                    ),
                }
            )
            return 0

    except (
        PhiVesselTrustOperatorError,
        OSError,
        ValueError,
    ) as exc:
        _print({"ok": False, "error": str(exc)})
        return 2

    parser.error("unknown trust command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
