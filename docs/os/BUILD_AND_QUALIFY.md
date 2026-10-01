# Build and qualify the Linux development preview

Use the always-triggered `PhiOS qualification` workflow. Its reusable
`Linux development image` job builds the separate QA artifact in a pinned
x86_64 Arch container, downgrades/synchronizes to the fixed Arch repository
snapshot in `packaging/linux/release.json`, checks the Archiso package version,
and builds the Python and UI packages from a hashed archive of the exact source
commit. Arch repository packages require signatures; the two local development
packages are unsigned and must not be presented as a signed public OS release.
`npm ci` uses the committed lockfile. No floating git checkout is used as source.

The image profile is staged from the installed complete Archiso releng template
and keeps its UEFI and initramfs inputs. The staging step removes root autologin,
SSH, cloud-init and unrelated services. It selects a graphical session for the
non-root `phios` user, with no wheel membership. In this **volatile live preview**
the public login is `phios` / `phios`, and root is locked. Never reuse that login
for an installed system or place private data in this live image. The reserved
`phios-agent` account cannot read the operator home and runs no agent by default.

The browser keeps Chromium's sandbox. The compositor's autostart imports its
Wayland environment before starting `phios-session.target`. Transport, curiosity
projection, optional history, browser and Waybar have separate user services.
Session exit stops the target. Default state is `%h/.local/state/phios` with
umask 0077. History is not auto-enabled: an operator must create and review
`~/.config/phios/memory.json` before that reader starts. Windows GhostWalk and
the curiosity authority broker are not started in this Linux preview.

For a local build, from a committed source checkout on an x86_64 Docker host:

```sh
bash build/build_iso.sh
# Or, after reviewing the privileged container build:
phi build iso --yes
```

The source mount is read-only; the privileged build runs inside the container,
with only `dist/linux` writable. It changes that container's pacman mirror,
never the host's mirror. The build must fail with a nonzero exit status if an
input, package install, UI build, profile assembly or mkarchiso step fails.
Do not run `packaging/linux/build-linux.sh` on a personal Arch installation:
it is the internal root-container entrypoint and rewrites its builder environment.

## Evidence

The Actions artifact includes the ISO, local packages, source archive/hash,
source commit, fixed release inputs, builder image identity, builder and image
package inventories, complete builder/Archiso logs, license history and SHA256SUMS. The CI-only
qualification fixture waits for the non-root compositor and browser, checks the
built page, native package observation and unified system state, verifies private state permissions,
and confirms all three approval HTTP routes return 403. QEMU runs with no
network and no target disk, using x64 UEFI firmware. The harness uses KVM when
the runner exposes it and records the selected accelerator; software TCG has
a longer explicit deadline. Wayfire permits software GLES rendering for this
virtual display, and its startup log remains in the private state directory.
The exact source marker,
ISO hash, VM command, serial log and screen capture are preserved, including a
display capture on failed qualification when QEMU is still running. The fixture
also kills the observer to verify supervised restart, ends the compositor to
verify service cleanup, and restarts greetd to prove a fresh graphical login.
The harness then resets the VM and requires the complete fixture on a second,
distinct kernel boot ID. Both desktop captures are preserved. This fixture
is omitted from normal locally built previews.

A fixture pass is evidence for the checks it performs. Review the screenshot
and session behavior. It does not prove installation, persisted receipts,
crash recovery, whole-OS updates, hardware compatibility or a Linux effect
executor. Those remain explicit gates in RELEASE_CONTRACT.md. CI never tags,
signs, publishes or automatically promotes this candidate. The later installed
and normal-image gates have their own scopes and receipts in IMPLEMENTATION_STATUS.md.

## Always-reported qualification gate

`release-qualification.yml` runs for every pull request, every main push,
OS `phios-linux-v*` tag and manual invocation. It calls the existing Python,
PhiShell, normal image and QA image workflows from the same source revision;
it does not poll or borrow another commit's successful runs. The called
workflows retain independent manual entrypoints and their existing tests and
artifact retention. Automatic calls are centralized to avoid duplicate builds.

Python tests, installed wheel, native vector and ledger-report checks always
run. Only a complete observed documentation-only PR may omit the expensive
image jobs. PhiShell contract docs still request UI checks. Unknown files,
deleted runtime files, build/test/workflow inputs, unreadable diff, main pushes,
OS tags and manual runs require both images and UI. The classifier uses the
complete local Git trees, including deletions, without an API pagination or
300-file workflow-path cutoff.

The final job is named **`release-gate`**, with `if: always()`. It fails when
scope determination fails, any required result is missing/failed/cancelled/
skipped, or scope outputs disagree. A skipped image is acceptable only when
explicitly unrequested for that documentation-only PR; this is not a new image
qualification. The job reports `release_ready: false` and no publication authority.
All jobs have read-only contents permissions and inherit no release secrets.

After reviewing this change and observing a successful run, the maintainer
should configure **`release-gate`** from GitHub Actions as the required status
on protected main and the applicable release rules. Require current-branch
checks and review, restrict bypass/force push/deletion and protect the OS tag
namespace as appropriate to the chosen release ownership. Those repository
settings are not changed by a workflow commit. A green aggregate does not
replace hardware evidence, authentic signing, final transition qualification,
source/license delivery or explicit release authorization.

Configure the requirement against the complete integration candidate containing
this controller after its same-source run passes. Earlier component heads
predate the controller and cannot emit `release-gate`; they are review references
for the integration. The complete candidate repeated all nine jobs in run
36823086807, including exact normal live/install/recovery, restricted virtual
DHCP/audio and actual PAM locking, plus the separate signed-update QA cases.
See RELEASE_HANDOFF.md and `evidence/qualification-gate-a7bcd986.json` for exact
identities, verified compact hashes, preserved failures and remaining gates.

## Retained retries and compact review metadata

Normal and QA artifact names include both the run ID and attempt number. A
same-source failed-job retry preserves earlier failure artifacts rather than
colliding with or overwriting them. Display conversion imports Pillow only when
actual PPM captures exist, so an early builder/download failure retains its
original error without an unrelated missing-Pillow cleanup exception.

An always-run bounded metadata step emits the actual receipt JSON (without VM
command arrays), source identity, inventory counts and small-file hashes to CI
logs. It cross-checks report source identities against this run's checked-out
source and preserves failed receipts as failures. These are producer metadata,
not an independent archive download verification or publication authority.
Use the emitted metadata when a review host cannot extract the compact archive;
record that limitation explicitly. Exact VM and aggregate assertions still
must pass, and every attempt retains its own source/artifact identity.
