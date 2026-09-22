import {
  COMPONENT_IDS,
  MAX_COHERENT_SKEW_MS,
  recomputeSystemStateReceiptDigest,
} from "./systemStateComposer.mjs";

const TOP_KEYS = [
  "schemaVersion",
  "source",
  "composedAt",
  "captureWindowStart",
  "captureWindowEnd",
  "captureSkewMs",
  "maxCoherentSkewMs",
  "coherence",
  "componentCount",
  "availableComponentCount",
  "readOnly",
  "executionAuthority",
  "effectPerformed",
  "components",
  "summary",
  "composeDurationMs",
  "receiptDigest",
];

const COMPONENT_KEYS = [
  "id",
  "schemaVersion",
  "source",
  "capturedAt",
  "availability",
  "digest",
  "readOnly",
  "executionAuthority",
  "effectPerformed",
];

const SUMMARY_KEYS = [
  "cpuLogicalCores",
  "memoryTotalBytes",
  "rootStorageTotalBytes",
  "observedServiceCount",
  "activeServiceCount",
  "currentUserProcessCount",
  "installedPackageCount",
  "blockDeviceCount",
  "networkDeviceCount",
  "pciDeviceCount",
  "usbDeviceCount",
  "drmDeviceCount",
  "powerDeviceCount",
];

const COMPONENT_CONTRACTS = Object.freeze({
  host: {
    schemaVersion: "phios.host-observation.v1",
    source: "linux-readonly-node-probe",
  },
  services: {
    schemaVersion: "phios.service-observation.v1",
    source: "systemd-dbus-list-units",
  },
  processes: {
    schemaVersion: "phios.process-observation.v1",
    source: "procfs-current-user",
  },
  packages: {
    schemaVersion: "phios.package-observation.v1",
    source: "dpkg-status-file",
  },
  devices: {
    schemaVersion: "phios.device-observation.v1",
    source: "linux-sysfs-bounded",
  },
});

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value, expected) {
  return (
    isRecord(value) &&
    Object.keys(value).sort().join("\0") === [...expected].sort().join("\0")
  );
}

function validTimestamp(value) {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function nonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

function sha256(value) {
  return typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
}

export function validateSystemStateReceipt(receipt) {
  const errors = [];

  if (!exactKeys(receipt, TOP_KEYS)) {
    return { ok: false, errors: ["top-level system-state fields do not match contract"] };
  }

  if (receipt.schemaVersion !== "phios.system-state.v1") errors.push("schemaVersion");
  if (receipt.source !== "phios-system-state-composer") errors.push("source");
  if (!validTimestamp(receipt.composedAt)) errors.push("composedAt");
  if (!validTimestamp(receipt.captureWindowStart)) errors.push("captureWindowStart");
  if (!validTimestamp(receipt.captureWindowEnd)) errors.push("captureWindowEnd");
  if (!nonNegativeNumber(receipt.captureSkewMs)) errors.push("captureSkewMs");
  if (receipt.maxCoherentSkewMs !== MAX_COHERENT_SKEW_MS) errors.push("maxCoherentSkewMs");
  if (!["coherent", "degraded"].includes(receipt.coherence)) errors.push("coherence");
  if (receipt.componentCount !== COMPONENT_IDS.length) errors.push("componentCount");
  if (
    !nonNegativeInteger(receipt.availableComponentCount) ||
    receipt.availableComponentCount > COMPONENT_IDS.length
  ) {
    errors.push("availableComponentCount");
  }
  if (receipt.readOnly !== true) errors.push("readOnly");
  if (receipt.executionAuthority !== false) errors.push("executionAuthority");
  if (receipt.effectPerformed !== false) errors.push("effectPerformed");
  if (!nonNegativeNumber(receipt.composeDurationMs)) errors.push("composeDurationMs");
  if (!sha256(receipt.receiptDigest)) errors.push("receiptDigest");

  if (!Array.isArray(receipt.components) || receipt.components.length !== COMPONENT_IDS.length) {
    errors.push("components");
  } else {
    receipt.components.forEach((component, index) => {
      const expectedId = COMPONENT_IDS[index];
      const expected = COMPONENT_CONTRACTS[expectedId];

      if (!exactKeys(component, COMPONENT_KEYS)) {
        errors.push(`component fields ${expectedId}`);
        return;
      }
      if (component.id !== expectedId) errors.push(`component id ${expectedId}`);
      if (component.schemaVersion !== expected.schemaVersion) {
        errors.push(`component schema ${expectedId}`);
      }
      if (component.source !== expected.source) errors.push(`component source ${expectedId}`);
      if (!validTimestamp(component.capturedAt)) errors.push(`component time ${expectedId}`);
      if (!["available", "unavailable"].includes(component.availability)) {
        errors.push(`component availability ${expectedId}`);
      }
      if (expectedId === "host" && component.availability !== "available") {
        errors.push("host availability");
      }
      if (!sha256(component.digest)) errors.push(`component digest ${expectedId}`);
      if (
        component.readOnly !== true ||
        component.executionAuthority !== false ||
        component.effectPerformed !== false
      ) {
        errors.push(`component authority ${expectedId}`);
      }
    });
  }

  if (!exactKeys(receipt.summary, SUMMARY_KEYS)) {
    errors.push("summary fields");
  } else {
    for (const key of SUMMARY_KEYS) {
      if (!nonNegativeNumber(receipt.summary[key])) errors.push(`summary ${key}`);
    }
    if (receipt.summary.activeServiceCount > receipt.summary.observedServiceCount) {
      errors.push("active service count");
    }
  }

  const times = Array.isArray(receipt.components)
    ? receipt.components.map((component) => Date.parse(component.capturedAt))
    : [];

  if (times.length === COMPONENT_IDS.length && times.every(Number.isFinite)) {
    const expectedStart = new Date(Math.min(...times)).toISOString();
    const expectedEnd = new Date(Math.max(...times)).toISOString();
    const expectedSkew = Math.max(...times) - Math.min(...times);
    if (receipt.captureWindowStart !== expectedStart) errors.push("capture window start");
    if (receipt.captureWindowEnd !== expectedEnd) errors.push("capture window end");
    if (receipt.captureSkewMs !== expectedSkew) errors.push("capture skew");
  }

  if (Array.isArray(receipt.components)) {
    const available = receipt.components.filter(
      (component) => component.availability === "available",
    ).length;
    if (receipt.availableComponentCount !== available) errors.push("available component count");

    const expectedCoherence =
      receipt.captureSkewMs <= MAX_COHERENT_SKEW_MS &&
      available === COMPONENT_IDS.length
        ? "coherent"
        : "degraded";
    if (receipt.coherence !== expectedCoherence) errors.push("coherence derivation");
  }

  if (sha256(receipt.receiptDigest)) {
    const recomputed = recomputeSystemStateReceiptDigest(receipt);
    if (receipt.receiptDigest !== recomputed) errors.push("receipt digest mismatch");
  }

  return { ok: errors.length === 0, errors };
}

export function assertValidSystemStateReceipt(receipt) {
  const result = validateSystemStateReceipt(receipt);
  if (!result.ok) {
    throw new Error(`invalid system-state receipt: ${result.errors.join("; ")}`);
  }
  return receipt;
}
