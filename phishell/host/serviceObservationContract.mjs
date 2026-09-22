import { SERVICE_ALLOWLIST } from "./serviceObserver.mjs";

const TOP_LEVEL_KEYS = [
  "allowlistOnly",
  "availability",
  "capturedAt",
  "effectPerformed",
  "executionAuthority",
  "readOnly",
  "reason",
  "schemaVersion",
  "services",
  "source",
];

const SERVICE_KEYS = [
  "activeState",
  "description",
  "found",
  "id",
  "label",
  "loadState",
  "subState",
  "unit",
];

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value, expected) {
  return (
    isRecord(value) &&
    Object.keys(value).sort().join("\0") === [...expected].sort().join("\0")
  );
}

function boundedString(value, max = 256) {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function nullableBoundedString(value, max = 256) {
  return value === null || boundedString(value, max);
}

export function validateServiceObservation(observation) {
  const errors = [];

  if (!exactKeys(observation, TOP_LEVEL_KEYS)) {
    return { ok: false, errors: ["top-level service fields do not match contract"] };
  }

  if (observation.schemaVersion !== "phios.service-observation.v1") {
    errors.push("unsupported service schemaVersion");
  }
  if (observation.source !== "systemd-dbus-list-units") {
    errors.push("unexpected service observation source");
  }
  if (
    !boundedString(observation.capturedAt, 64) ||
    Number.isNaN(Date.parse(observation.capturedAt))
  ) {
    errors.push("capturedAt must be a valid timestamp");
  }
  if (!["available", "unavailable"].includes(observation.availability)) {
    errors.push("invalid availability");
  }
  if (
    observation.reason !== null &&
    !["non-linux-host", "systemd-runtime-not-present", "system-bus-unavailable"].includes(
      observation.reason,
    )
  ) {
    errors.push("invalid unavailable reason");
  }
  if (observation.availability === "available" && observation.reason !== null) {
    errors.push("available observation must not carry an unavailable reason");
  }
  if (observation.availability === "unavailable" && observation.reason === null) {
    errors.push("unavailable observation requires a bounded reason");
  }
  if (observation.allowlistOnly !== true) errors.push("allowlistOnly must be true");
  if (observation.readOnly !== true) errors.push("readOnly must be true");
  if (observation.executionAuthority !== false) {
    errors.push("executionAuthority must be false");
  }
  if (observation.effectPerformed !== false) errors.push("effectPerformed must be false");

  if (
    !Array.isArray(observation.services) ||
    observation.services.length !== SERVICE_ALLOWLIST.length
  ) {
    errors.push("service result must match the fixed allowlist length");
    return { ok: false, errors };
  }

  observation.services.forEach((service, index) => {
    const definition = SERVICE_ALLOWLIST[index];

    if (!exactKeys(service, SERVICE_KEYS)) {
      errors.push(`service fields invalid at index ${index}`);
      return;
    }
    if (service.id !== definition.id || service.label !== definition.label) {
      errors.push(`service identity mismatch at index ${index}`);
    }
    if (!definition.units.includes(service.unit)) {
      errors.push(`unit escaped allowlist at index ${index}`);
    }
    if (typeof service.found !== "boolean") {
      errors.push(`found must be boolean at index ${index}`);
    }

    if (service.found) {
      if (
        !nullableBoundedString(service.description, 256) ||
        !boundedString(service.loadState, 64) ||
        !boundedString(service.activeState, 64) ||
        !boundedString(service.subState, 64)
      ) {
        errors.push(`loaded service state invalid at index ${index}`);
      }
    } else if (
      service.description !== null ||
      service.loadState !== null ||
      service.activeState !== null ||
      service.subState !== null
    ) {
      errors.push(`not-loaded service must not carry synthetic state at index ${index}`);
    }
  });

  return { ok: errors.length === 0, errors };
}

export function assertValidServiceObservation(observation) {
  const result = validateServiceObservation(observation);
  if (!result.ok) {
    throw new Error(`invalid service observation: ${result.errors.join("; ")}`);
  }
  return observation;
}
