import { createHash } from "node:crypto";
import { collectLinuxHostObservation } from "./linuxProbe.mjs";
import { assertValidHostObservation } from "./observationContract.mjs";
import { collectSystemdServiceObservation } from "./serviceObserver.mjs";
import { assertValidServiceObservation } from "./serviceObservationContract.mjs";
import { collectCurrentUserProcessObservation } from "./processObserver.mjs";
import { assertValidProcessObservation } from "./processObservationContract.mjs";
import { collectPackageObservation } from "./packageObserver.mjs";
import { assertValidPackageObservation } from "./packageObservationContract.mjs";
import { collectDeviceObservation } from "./deviceObserver.mjs";
import { assertValidDeviceObservation } from "./deviceObservationContract.mjs";

const MAX_COHERENT_SKEW_MS = 5_000;
const COMPONENT_IDS = Object.freeze(["host", "services", "processes", "packages", "devices"]);

function sha256Json(value) {
  return `sha256:${createHash("sha256").update(JSON.stringify(value)).digest("hex")}`;
}

function componentReceipt(id, observation, availability = "available") {
  return {
    id,
    schemaVersion: observation.schemaVersion,
    source: observation.source,
    capturedAt: observation.capturedAt,
    availability,
    digest: sha256Json(observation),
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
  };
}

function availabilityOf(observation) {
  return observation.availability === "unavailable" ? "unavailable" : "available";
}

function countActiveServices(serviceObservation) {
  return serviceObservation.services.filter(
    (service) => service.found && service.activeState === "active",
  ).length;
}

function buildSummary(host, services, processes, packages, devices) {
  return {
    cpuLogicalCores: host.cpu.logicalCores,
    memoryTotalBytes: host.memory.totalBytes,
    rootStorageTotalBytes: host.storage.totalBytes,
    observedServiceCount: services.services.filter((service) => service.found).length,
    activeServiceCount: countActiveServices(services),
    currentUserProcessCount: processes.currentUserProcessCount,
    installedPackageCount: packages.totalInstalledPackageCount,
    blockDeviceCount: devices.block.length,
    networkDeviceCount: devices.network.length,
    pciDeviceCount: devices.pci.length,
    usbDeviceCount: devices.usb.length,
    drmDeviceCount: devices.drm.length,
    powerDeviceCount: devices.power.length,
  };
}

function digestReceiptBody(receipt) {
  const { receiptDigest: _ignored, ...body } = receipt;
  return sha256Json(body);
}

export async function composeSystemStateReceipt({
  collectHost = collectLinuxHostObservation,
  collectServices = collectSystemdServiceObservation,
  collectProcesses = collectCurrentUserProcessObservation,
  collectPackages = collectPackageObservation,
  collectDevices = collectDeviceObservation,
} = {}) {
  const composedStart = Date.now();

  const [hostRaw, servicesRaw, processesRaw, packagesRaw, devicesRaw] = await Promise.all([
    collectHost(),
    collectServices(),
    collectProcesses(),
    collectPackages(),
    collectDevices(),
  ]);

  const host = assertValidHostObservation(hostRaw);
  const services = assertValidServiceObservation(servicesRaw);
  const processes = assertValidProcessObservation(processesRaw);
  const packages = assertValidPackageObservation(packagesRaw);
  const devices = assertValidDeviceObservation(devicesRaw);

  const components = [
    componentReceipt("host", host),
    componentReceipt("services", services, availabilityOf(services)),
    componentReceipt("processes", processes, availabilityOf(processes)),
    componentReceipt("packages", packages, availabilityOf(packages)),
    componentReceipt("devices", devices, availabilityOf(devices)),
  ];

  const captureTimes = components.map((component) => Date.parse(component.capturedAt));
  const captureWindowStart = new Date(Math.min(...captureTimes)).toISOString();
  const captureWindowEnd = new Date(Math.max(...captureTimes)).toISOString();
  const captureSkewMs = Math.max(...captureTimes) - Math.min(...captureTimes);
  const availableComponentCount = components.filter(
    (component) => component.availability === "available",
  ).length;

  const receipt = {
    schemaVersion: "phios.system-state.v1",
    source: "phios-system-state-composer",
    composedAt: new Date().toISOString(),
    captureWindowStart,
    captureWindowEnd,
    captureSkewMs,
    maxCoherentSkewMs: MAX_COHERENT_SKEW_MS,
    coherence:
      captureSkewMs <= MAX_COHERENT_SKEW_MS &&
      availableComponentCount === COMPONENT_IDS.length
        ? "coherent"
        : "degraded",
    componentCount: COMPONENT_IDS.length,
    availableComponentCount,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    components,
    summary: buildSummary(host, services, processes, packages, devices),
    composeDurationMs: Math.max(0, Date.now() - composedStart),
    receiptDigest: "",
  };

  receipt.receiptDigest = digestReceiptBody(receipt);
  return receipt;
}

export function recomputeSystemStateReceiptDigest(receipt) {
  return digestReceiptBody(receipt);
}

export { COMPONENT_IDS, MAX_COHERENT_SKEW_MS };
