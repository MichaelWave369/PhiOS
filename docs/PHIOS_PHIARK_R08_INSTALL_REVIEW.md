# PhiOS R0.8: PhiARK network-denied install-review candidate

**Status:** HELD_FOR_OPERATOR_REVIEW. This is not a source acquisition, installation, runtime launch, permission grant, physical sandbox qualification or a release.

## Change from R0.6/R0.7

PhiARK now implements a Linux Unix-domain socket and PhiOS has a separately human-started host-loopback diagnostic gateway. The earlier candidate requested `runtime.network.inherit` because only a broad host network could expose an ordinary TCP server. That is no longer an acceptable installation proposal.

The candidate under `integrations/phiark/manifest-candidate.json` therefore requests only `runtime.data.persist`, making the **intended** PhiOS runtime network mode `deny`. This does **not** make current PhiOS v0.34 able to launch PhiARK as a working service.

`integrations/phiark/r08-install-review-candidate.json` records the currently observed PhiARK `main` commit as an exact 40-character candidate pin. It has not been operator-approved, acquired or attested by PhiOS. If upstream moves, the pin does not silently move. A reviewer must deliberately inspect and replace the pin.

## Current real blockers

1. PhiOS v0.26 can observe a bounded public GitHub repository; v0.27 can separately acquire a reviewed exact commit. Neither has been executed under installation authority for this candidate.
2. The installed runtime currently mounts writable persistent app data at `/phios/app-data`, but exposes only `PHIOS_APP_DATA`. It does **not** inject `PHIARK_DATA_DIR=/phios/app-data` or `PHIARK_SOCKET_PATH=/phios/app-data/.phiark.sock` into PhiARK.
3. The direct installed-runtime adapter is a bounded, synchronous process with a wall-clock deadline. It is not a supervised long-running PhiARK service; repeatedly launching it is not an acceptable substitute.
4. Existing PhiARK R0.7 gateway is an operator-approved diagnostic bridge for an **already-running** socket. It does not bind to a verified installed-runtime process or prove which code owns the socket.
5. The Linux target's Bubblewrap `--unshare-net` must be qualified on an actual device. Passing Python unit tests or VM package jobs is not sufficient.

## Next smallest truthful acceptance test

Using temporary synthetic installed-tree receipts and explicit fake resources, prove the **advisory** candidate: 

- Source repository, app identity, requested data permission and Node entrypoint match the reviewed candidate.
- The proposal has **no host-network-inheritance permission**, identifies exactly one Unix socket inside the private app data root, and never supplies false install/launch authority.
- Missing source-commit, toolchain, environment mapping, service supervision or physical isolation evidence remains **blocked**, not `PASS`.

After that, implement a separately reviewed, exact-receipt-bound long-running runtime adapter, with a private data root, explicit stop and restart, and physical network-denial evidence. Only then qualify offline cold boot with actual stored guides.

Related: [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321), [PhiOS R0.7](PHIOS_PHIARK_R07_LOCAL_GATEWAY.md), [PhiARK socket](https://github.com/MichaelWave369/PhiARK/blob/main/docs/PHIOS_UNIX_SOCKET_R06.md).
