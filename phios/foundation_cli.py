"""PhiOS R1.2 read-only foundation status command."""
from __future__ import annotations

import argparse
import json
import sys

from phios.foundation_status import observe_foundation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compose bounded PhiOS foundation observations; never installs or starts services."
    )
    command = parser.add_subparsers(dest="command", required=True)
    status = command.add_parser("status")
    status.add_argument("--mode", choices=("offline", "public", "local"), default="offline")
    status.add_argument("--phiark-data-root", default=None)
    status.add_argument("--verify-kiwix", action="store_true")
    status.add_argument("--probe-phiark-loopback", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = observe_foundation(
            mode=args.mode,
            phiark_data_root=args.phiark_data_root,
            verify_kiwix=args.verify_kiwix,
            probe_phiark_loopback=args.probe_phiark_loopback,
        )
    except (ValueError, OSError):
        # Do not echo any private local absolute path or raw transport exception.
        print(json.dumps({"status": "REFUSED", "error": "INVALID_OPERATOR_REQUEST"}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    # Report success only means a report was generated; offlineReady remains false.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
