# PhiShell v0.7 — Read-Only Package Inventory

Status: **candidate implementation**  
Target substrate: **Linux / Debian-family package database / Wayland path**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.7 adds installed-package awareness without adding package-management authority.

## Native source

The first package adapter reads only:

```text
/etc/os-release
/var/lib/dpkg/status
```

It supports Debian-family distributions when the distro metadata identifies a compatible package database.

It does not invoke:

```text
apt
apt-get
dpkg
rpm
dnf
pacman
zypper
sudo
child_process
exec
spawn
```

## Bounded package projection

Only packages whose dpkg status is exactly:

```text
install ok installed
```

are counted.

Detailed rows are capped at:

```text
packageLimit = 64
```

Each exposed package row contains only:

```text
name
version
architecture
essential
```

The adapter does not transport package descriptions, maintainer addresses, homepages, repository metadata, dependency graphs, file lists, changelogs, or package scripts.

## Observation contract

A live package observation carries:

```text
schemaVersion               = phios.package-observation.v1
source                      = dpkg-status-file
adapter                     = debian-dpkg-status
packageLimit                = 64
readOnly                    = true
executionAuthority          = false
effectPerformed             = false
totalInstalledPackageCount  = <count>
```

Availability is explicit. Unsupported distributions return an unavailable observation rather than guessing.

## Transport

The existing loopback host adds:

```text
GET /api/v1/package-observation
```

with:

```text
transportSchemaVersion = phios.package-transport.v1
transport              = loopback-http
transportIdentity      = phishell-local-observer
localOnly              = true
readOnly               = true
executionAuthority     = false
effectPerformed        = false
```

The host remains bound to `127.0.0.1`. POST and other mutation methods remain rejected.

## Browser trust boundary

PhiShell accepts package inventory only when:

- the transport identity is correct;
- the response is fresh;
- the package schema matches;
- the adapter is the declared Debian status-file adapter;
- authority and effect fields remain false;
- the detail limit is exactly 64;
- row count stays within the limit;
- each row contains only the bounded four fields.

The browser explicitly rejects package rows that try to add fields such as descriptions, maintainers, or homepages.

## Capability plane

v0.7 exposes:

```text
package.inspect = available
```

while preserving:

```text
package.manage = unavailable
```

Therefore:

```text
can inventory packages
    !=
can install packages
    !=
can remove packages
    !=
can upgrade packages
    !=
can change repositories
```

## System Inspector

The Package Inventory panel displays:

- detected distro;
- total installed package count;
- up to 64 package rows;
- package name;
- version;
- architecture;
- essential flag.

The only control is Refresh.

## CI proof

The PhiShell lane now verifies:

```text
contract tests
→ native package parser tests
→ live Linux host probe
→ live systemd service probe
→ live process probe
→ live Debian package-database probe
→ production build
→ same-origin host/service/process/package observations
→ POST rejected with 405
```

The Ubuntu runner must expose a readable Debian package database for the live package step to pass.

## Replaceability

The contract belongs to PhiOS, not dpkg.

The Debian adapter is intentionally isolated behind:

```text
collectPackageObservation()
```

Future RPM, pacman, or other inventory adapters can implement the same governed observation contract without redesigning PhiShell.

## Next increment

A safe v0.8 candidate is bounded **device inventory** using read-only sysfs metadata.

It should expose identity/capability metadata only and continue to avoid device-control, driver-binding, mount, network-configuration, or power operations.
