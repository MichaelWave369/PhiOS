# PhiShell v0.8 — Bounded Hardware Inventory

Status: **candidate implementation**  
Target substrate: **Linux / sysfs / Wayland path**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.8 adds read-only physical-device awareness without adding device-control authority.

## Native source

The device observer reads bounded metadata from Linux sysfs only.

Observed classes are:

```text
CPU topology
block devices
network interfaces
PCI devices
USB devices
DRM devices
power supplies
```

The observer creates no subprocess and writes no sysfs file.

## Fixed class limits

Each category has a hard detail cap:

```text
block    16
network  16
pci      16
usb      16
drm       8
power     8
```

The CPU topology result is an aggregate rather than an unbounded per-CPU payload.

## CPU topology

PhiShell derives only:

```text
logicalCpuCount
physicalPackageCount
physicalCoreCount
```

from the fixed CPU topology paths.

No frequency-control, governor, hotplug, or scheduler controls are exposed.

## Block devices

Each bounded block row contains:

```text
name
sizeBytes
removable
rotational
vendor
model
```

No filesystem contents, mount targets, UUIDs, partition labels, or write operations are exposed.

## Network devices

Each bounded network row contains:

```text
name
type
operState
vendorId
deviceId
```

The observer does **not** read or transport MAC addresses.

It also does not expose link configuration, routes, DNS configuration, interface enable/disable controls, or address assignment.

## PCI devices

Each bounded PCI row contains:

```text
slot
vendorId
deviceId
classId
```

Driver names, driver paths, BAR mappings, configuration space, bind/unbind controls, reset controls, and remove/rescan controls are not exposed.

## USB devices

Each bounded USB row contains:

```text
pathId
vendorId
productId
deviceClass
manufacturer
product
```

USB serial numbers are explicitly omitted.

No USB authorization, reset, bind/unbind, or device-control surface is exposed.

## DRM devices

Each bounded DRM row contains:

```text
name
vendorId
deviceId
```

The observer does not expose modesetting, connector mutation, GPU clocks, power profiles, or driver controls.

## Power supplies

Each bounded power row contains:

```text
name
type
manufacturer
model
```

Serial numbers and writable power controls are omitted.

## Observation contract

A live hardware observation carries:

```text
schemaVersion       = phios.device-observation.v1
source              = linux-sysfs-bounded
readOnly            = true
executionAuthority  = false
effectPerformed     = false
```

Availability is explicit:

```text
available
unavailable
```

Bounded unavailable reasons are:

```text
non-linux-host
sysfs-unavailable
```

Raw filesystem errors are not transported.

## Transport

The loopback host adds:

```text
GET /api/v1/device-observation
```

with:

```text
transportSchemaVersion = phios.device-transport.v1
transport              = loopback-http
transportIdentity      = phishell-local-observer
localOnly              = true
readOnly               = true
executionAuthority     = false
effectPerformed        = false
```

The host remains bound to:

```text
127.0.0.1
```

All non-GET methods remain rejected.

## Browser trust boundary

PhiShell accepts device observations only when:

- transport identity matches;
- freshness is within the existing five-second limit;
- source is `linux-sysfs-bounded`;
- authority and effect fields remain false;
- every category remains inside its frozen cap;
- every row matches the exact expected field set;
- numeric fields are bounded and sane.

Network rows that contain MAC or address fields are rejected.

USB or power rows that contain serial fields are rejected.

Unknown extra fields fail the exact-shape validation.

## Capability plane

v0.8 exposes:

```text
device.inspect = available
```

while explicitly preserving:

```text
device.control = unavailable
```

Therefore:

```text
can observe hardware
    !=
can bind a driver
    !=
can mount a disk
    !=
can configure a network device
    !=
can change device power state
```

## Forbidden mutation surface

The native observer contains no:

```text
writeFile
appendFile
chmod
chown
child_process
exec
spawn
driver bind
driver unbind
remove
rescan
power/control
```

The observation endpoint accepts no device path, PCI slot, USB path, block device, interface name, or arbitrary sysfs path from the browser.

There is no generic sysfs reader endpoint.

## System Inspector

The Hardware Inventory panel shows:

- CPU topology counts;
- bounded block inventory;
- bounded PCI inventory;
- bounded DRM/GPU identity;
- bounded USB inventory;
- bounded network hardware identity/state;
- bounded power-supply identity.

The only interactive control is:

```text
Refresh
```

## CI proof

The PhiShell lane performs:

```text
npm install
    ↓
browser and native contract tests
    ↓
live host probe
    ↓
live systemd service probe
    ↓
live process probe
    ↓
live package probe
    ↓
live sysfs hardware probe
    ↓
TypeScript/Vite build
    ↓
launch loopback host
    ↓
GET host/service/process/package/device observations
    ↓
verify authority=false
    ↓
verify effect=false
    ↓
POST observation endpoints
    ↓
405 Method Not Allowed
```

The Ubuntu runner must expose readable sysfs for the live device step to pass.

## Next increment

A safe v0.9 candidate is a **unified observation snapshot and health model** that composes host, service, process, package, and hardware observations into one versioned, read-only system-state receipt.

That would give PhiShell a coherent machine model without broadening authority.

The v0.8 device observer should remain permanently read-only.
