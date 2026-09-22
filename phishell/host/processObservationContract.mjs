const TOP_LEVEL_KEYS = [
  "availability",
  "capturedAt",
  "currentUid",
  "currentUserProcessCount",
  "effectPerformed",
  "executionAuthority",
  "processLimit",
  "processes",
  "readOnly",
  "reason",
  "schemaVersion",
  "scope",
  "source",
  "stateCounts",
];

const PROCESS_KEYS = ["comm", "pid", "ppid", "rssBytes", "state", "threads"];
const STATE_KEYS = ["diskSleep", "idle", "other", "running", "sleeping", "stopped", "zombie"];

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value, expected) {
  return (
    isRecord(value) &&
    Object.keys(value).sort().join("\0") === [...expected].sort().join("\0")
  );
}

function boundedString(value, max) {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

export function validateProcessObservation(observation) {
  const errors = [];

  if (!exactKeys(observation, TOP_LEVEL_KEYS)) {
    return { ok: false, errors: ["top-level process fields do not match contract"] };
  }

  if (observation.schemaVersion !== "phios.process-observation.v1") {
    errors.push("unsupported process schemaVersion");
  }
  if (observation.source !== "procfs-current-user") {
    errors.push("unexpected process observation source");
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
    !["non-linux-host", "current-uid-unavailable", "procfs-unavailable"].includes(
      observation.reason,
    )
  ) {
    errors.push("invalid unavailable reason");
  }
  if (observation.availability === "available" && observation.reason !== null) {
    errors.push("available observation must not carry an unavailable reason");
  }
  if (observation.availability === "unavailable" && observation.reason === null) {
    errors.push("unavailable observation requires a reason");
  }
  if (observation.scope !== "current-user") errors.push("scope must be current-user");
  if (observation.processLimit !== 32) errors.push("processLimit must be 32");
  if (observation.readOnly !== true) errors.push("readOnly must be true");
  if (observation.executionAuthority !== false) {
    errors.push("executionAuthority must be false");
  }
  if (observation.effectPerformed !== false) errors.push("effectPerformed must be false");

  if (!(observation.currentUid === null || nonNegativeInteger(observation.currentUid))) {
    errors.push("currentUid invalid");
  }
  if (!nonNegativeInteger(observation.currentUserProcessCount)) {
    errors.push("currentUserProcessCount invalid");
  }

  if (!exactKeys(observation.stateCounts, STATE_KEYS)) {
    errors.push("stateCounts fields invalid");
  } else {
    for (const key of STATE_KEYS) {
      if (!nonNegativeInteger(observation.stateCounts[key])) {
        errors.push(`stateCounts.${key} invalid`);
      }
    }
  }

  if (!Array.isArray(observation.processes) || observation.processes.length > 32) {
    errors.push("process list invalid");
    return { ok: false, errors };
  }

  if (observation.processes.length > observation.currentUserProcessCount) {
    errors.push("process list cannot exceed current-user process count");
  }

  for (const item of observation.processes) {
    if (
      !exactKeys(item, PROCESS_KEYS) ||
      !Number.isInteger(item.pid) ||
      item.pid <= 0 ||
      !nonNegativeInteger(item.ppid) ||
      !boundedString(item.comm, 128) ||
      !/^[RSDTtZXIP?]$/.test(item.state) ||
      !Number.isFinite(item.rssBytes) ||
      item.rssBytes < 0 ||
      !Number.isInteger(item.threads) ||
      item.threads < 1
    ) {
      errors.push("process row invalid");
      break;
    }
  }

  return { ok: errors.length === 0, errors };
}

export function assertValidProcessObservation(observation) {
  const result = validateProcessObservation(observation);
  if (!result.ok) {
    throw new Error(`invalid process observation: ${result.errors.join("; ")}`);
  }
  return observation;
}
