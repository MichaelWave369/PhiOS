# Build and qualify the Linux development preview

Use the `Linux development image` pull-request workflow. It builds in a pinned
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
display capture on failed qualification when QEMU is still running. This fixture
is omitted from normal locally built previews.

A fixture pass is evidence for the checks it performs. Review the screenshot
and session behavior. It does not prove installation, persisted receipts,
crash recovery, whole-OS updates, hardware compatibility or a Linux effect
executor. Those remain explicit gates in RELEASE_CONTRACT.md. CI never tags,
signs, publishes or automatically promotes this candidate.
