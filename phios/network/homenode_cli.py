"""Operator-initiated PhiOS HomeNode mode selection.

No listener, automatic discovery, persistence, Git mutations or background polling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
from pathlib import Path

from phios.network.homenode import (
    HomeNodeTrustError,
    config_from_env,
    load_trust,
    select_mode,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS HomeNode trusted client, preview")
    sub = parser.add_subparsers(dest="action", required=True)
    status = sub.add_parser("status", help="Select PUBLIC, LOCAL, or OFFLINE")
    status.add_argument("--mode", required=True, choices=("public", "local", "offline"))
    sub.add_parser("preflight", help="Validate local trust files without networking")
    fp = sub.add_parser("fingerprint", help="Display untrusted certificate SHA-256 candidate")
    fp.add_argument("certificate", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            result = select_mode(args.mode)
        elif args.action == "preflight":
            config = config_from_env()
            load_trust(config)
            result = {
                "status": "LOCAL_TRUST_FILES_CHECKED_NO_NETWORK",
                "note": "No remote identity, service readiness, or firewall policy validated.",
            }
        else:
            path: Path = args.certificate
            if not path.is_absolute() or path.is_symlink() or not path.is_file():
                raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
            if not 0 < path.stat().st_size <= 1024 * 1024:
                raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
            cert = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))
            result = {
                "certificateSha256": hashlib.sha256(cert).hexdigest(),
                "notice": "Independently verify this certificate fingerprint before trusting it.",
            }
    except (OSError, ValueError, ssl.SSLError, UnicodeError) as exc:
        # Never disclose local paths or secret material in terminal errors.
        print(
            json.dumps({"status": "FAILED", "failure":
                str(exc) if isinstance(exc, HomeNodeTrustError) else "LOCAL_CONFIGURATION_REQUIRED"}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
