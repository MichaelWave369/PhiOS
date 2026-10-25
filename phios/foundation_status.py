"""Operator-run PhiOS foundation observation R1.2.

Composes pre-existing, independently governed observations without starting a
daemon, executing a model, installing software, or manufacturing offline proof.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from phios.apps.phiark_bridge import observe_phiark
from phios.git_mirror_observer import observe_git_mirror
from phios.network.homenode import select_mode

SCHEMA = "phios.foundation_observation.v0.1"
MODES = {"offline", "public", "local"}
FAILURES = {
    "LOCAL_CONFIGURATION_REQUIRED",
    "LOCAL_UNTRUSTED",
    "LOCAL_REJECTED",
    "LOCAL_TIMEOUT",
    "LOCAL_BAD_RESPONSE",
    "LOCAL_UNAVAILABLE",
}


def observe_foundation(
    *,
    mode: str = "offline",
    phiark_data_root: str | Path | None = None,
    git_mirror: str | Path | None = None,
    verify_kiwix: bool = False,
    probe_phiark_loopback: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Collect only explicitly requested bounded observations.

    OFFLINE/PUBLIC never probe a network and never inspect HomeNode credentials.
    LOCAL opts into the separately implemented pinned-TLS GitPorch client.
    A PhiARK data path must be explicit; no blind filesystem discovery.
    """
    if mode not in MODES:
        raise ValueError("Invalid mode: select offline, public or local")
    if phiark_data_root is None and (verify_kiwix or probe_phiark_loopback):
        raise ValueError("PhiARK archive/server probes require --phiark-data-root")
    if probe_phiark_loopback and mode != "local":
        raise ValueError("PhiARK loopback probe requires explicit local mode")
    if git_mirror is not None:
        mirror = Path(git_mirror)
        if not mirror.is_absolute():
            raise ValueError("Git mirror path must be absolute")
    if phiark_data_root is not None:
        root = Path(phiark_data_root)
        if not root.is_absolute():
            raise ValueError("PhiARK data root must be absolute")

    # PUBLIC/OFFLINE are dry mode selections in this native client, NOT probes.
    homenode = select_mode(mode, env=env)
    trusted_gateway = homenode["gatewayVerified"] is True
    home_status = {
        "requestedMode": homenode["requestedMode"],
        "effectiveMode": homenode["effectiveMode"],
        "status": homenode["status"],
        "gatewayVerified": trusted_gateway,
        "offlineServicesVerified": False,
        "capabilities": homenode.get("capabilities") if trusted_gateway else None,
        "failure": homenode.get("failure") if homenode.get("failure") in FAILURES else None,
        "actionAuthority": False,
    }

    if phiark_data_root is None:
        ark: dict[str, object] = {
            "status": "NOT_REQUESTED",
            "catalogStatus": "NOT_OBSERVED",
            "documentsHashVerified": 0,
            "documentsFailed": 0,
            "kiwixStatus": "NOT_OBSERVED",
            "archivesChecksumMatched": 0,
            "archivesFailed": 0,
            "loopbackStatus": "NOT_PROBED",
            "processIdentityVerified": False,
            "installAuthority": False,
            "launchAuthority": False,
            "contentApproved": False,
            "licenseApproved": False,
        }
    else:
        observed = observe_phiark(
            phiark_data_root,
            verify_kiwix=verify_kiwix,
            probe_loopback=probe_phiark_loopback,
        )
        catalog = observed["catalog"]
        kiwix = observed["kiwix"]
        ark = {
            # Sanitize: never export data_root, file names, archive bytes or contents.
            "status": observed["status"],
            "catalogStatus": catalog["status"],
            "documentsHashVerified": catalog["hash_verified"],
            "documentsFailed": catalog["failed"],
            "kiwixStatus": kiwix["status"],
            "archivesChecksumMatched": kiwix["checksum_matched"],
            "archivesFailed": kiwix["failed"],
            "loopbackStatus": observed["loopback"]["status"],
            "processIdentityVerified": False,
            "installAuthority": False,
            "launchAuthority": False,
            "contentApproved": False,
            "licenseApproved": False,
        }

    if git_mirror is None:
        git: dict[str, object] = {
            "status": "NOT_REQUESTED",
            "headCommit": None,
            "objectIntegrityPassed": False,
            "remoteFetchPerformed": False,
            "backupRestored": False,
            "lfsObjectsVerified": False,
            "offlineNetworkStateVerified": False,
            "effectAuthority": False,
        }
    else:
        git = observe_git_mirror(git_mirror)

    blocked = (git_mirror is not None and git["status"] != "OBJECTS_VERIFIED") or (
               home_status["status"] == "LOCAL_FAILED_OFFLINE_MODE_SELECTED" or
               ark["status"] == "BLOCKED" or
               ark["documentsFailed"] != 0 or ark["archivesFailed"] != 0)
    partial = (trusted_gateway or ark["status"] == "LOCAL_BYTES_OBSERVED" or
               git["status"] == "OBJECTS_VERIFIED")
    verdict = "BLOCKED" if blocked else "PARTIAL_EVIDENCE" if partial else "UNVERIFIED"
    return {
        "schema": SCHEMA,
        "status": verdict,
        "mode": mode.upper(),
        "homenode": home_status,
        "phiark": ark,
        "gitMirror": git,
        "porch": {
            "status": "SEPARATE_MANUAL_PHIOS_HOME_PREFLIGHT",
            "identityVerified": False,
            "modelAvailabilityVerified": False,
            "modelExecutionAuthorized": False,
        },
        "acceptance": {
            "gitMirrorRestoredOffline": False,
            "offlineBuildExecuted": False,
            "knowledgeDocumentOpenedOffline": False,
            "genuineKiwixReaderTested": False,
            "localModelInferenceTested": False,
            "twoPhysicalMachinesVerified": False,
            "wanDisconnectedTested": False,
            "offlineReady": False,
        },
        "authority": {
            "install": False,
            "launch": False,
            "networkConfigure": False,
            "gitPush": False,
            "modelExecute": False,
            "peerConnect": False,
        },
        "note": (
            "Git object verification, if requested, is read-only and excludes LFS or restore. "
            "This is an observation summary, not a verified offline installation, "
            "hardware test, authenticated Porch session or release grant."
        ),
    }
