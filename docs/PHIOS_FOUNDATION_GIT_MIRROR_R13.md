# PhiOS R1.3: local GitPorch mirror integrity rung

**Status: opt-in local Git object verification only. This does not install GitPorch, restore a backup, disconnect the WAN, run local AI, or qualify PhiOS for release.**

## Why this exists

R1.2 observes the pinned TLS GitPorch gateway and optionally verifies local PhiARK bytes. A gateway being reachable does **not** mean your source has actually been mirrored to local storage. R1.3 independently checks one **already-existing local bare Git mirror** using a bounded Git integrity test, so the operator can compare actual source-store evidence and offline-library bytes in one status report.

GitPorch's normal single-user bare repository layout is `GITPORCH_DATA_DIR/repos/<name>.git`. The client supplies a precise absolute path; no directories are recursively discovered or modified. Nothing is copied or downloaded.

## Operator commands

```shell
# No network, source scan, or credential access:
phi-foundation status

# Read one local bare Git repository and check Git objects and its HEAD:
phi-foundation status --mode offline --git-mirror /absolute/GitPorch/data/repos/PhiOS.git

# Check a GitPorch bare mirror and independently hash already-imported PhiARK files:
phi-foundation status --mode offline \
  --git-mirror /absolute/GitPorch/data/repos/PhiOS.git \
  --phiark-data-root /absolute/PhiARKVault
```

On Windows pass your actual **absolute Windows path** in quotes, not the illustrative Unix-style path. Git and the real bare mirror must be available on that machine.

## Precisely checked

- Path is absolute, exists as a real directory with no symlinked ancestors; HEAD/config are real files, objects/refs are real directories.
- Refuses a shallow repository and explicit alternate object store or promisor pack marker; does not fetch missing objects.
- Runs only fixed, local `git --git-dir=<path> rev-parse` and `git --git-dir=<path> fsck --full --strict --no-reflogs` commands. No shell, repo hooks, scripts, network, push, commit, checkout, restore, npm, Docker or model invocation.
- Runs with inherited Git configuration and alternate-object environment variables stripped. Prompts, lazy fetching, optional locks and LFS smudge are disabled. Output of Git is suppressed except the validated exact commit ID.
- Fails closed on absent Git, missing mirror, invalid layout, empty/unborn branch, timeouts or Git object failures. Negative receipt has **no** "verified" bit.
- Report includes only a bounded status and validated HEAD ID. It never exports the selected mirror path, Git stderr, private remotes, file contents, local credentials or complete refs.

The check can take time on large mirrors and times out after 60 seconds **per command**. It examines one repository only, not all 2,048 possible GitPorch repositories. The exact Git installed on the machine is an external dependency. Do not point it at adversarial data without a host-level sandbox.

## Evidence not obtained

Passing Git fsck means the **local reachable Git objects are structurally consistent** for the checked bare mirror. It does **not** prove the mirror matches current GitHub, all branches/tags were copied, the mirror was restored from external backup, LFS objects and submodule contents exist, that a project builds, what a certificate represents, or that the WAN was actually disconnected.

The R1.3 composite verdict is `PARTIAL_EVIDENCE` after success, or `BLOCKED` when an explicitly requested mirror fails. `acceptance.gitMirrorRestoredOffline`, `acceptance.wanDisconnectedTested` and `acceptance.offlineReady` remain **false** until independent end-to-end field runs with retained machine/network proofs.

## Test on GitHub

```sh
python -m pytest tests/test_git_mirror_field_r13.py tests/test_foundation_status_r12.py -q
ruff check phios/git_mirror_observer.py phios/foundation_status.py phios/foundation_cli.py tests/test_git_mirror_field_r13.py
mypy phios/git_mirror_observer.py phios/foundation_status.py phios/foundation_cli.py --ignore-missing-imports
```

The tests initialize a real temporary Git repository, commit actual bytes, clone a local bare mirror and run genuine Git checks. They also exercise altered bytes, symlinked paths, malformed arguments, source-output redaction and the distinction between verified objects and true WAN-off readiness. Nothing on the operator's PCs is installed by merging this PR.

**Ledger Above Ego.**
