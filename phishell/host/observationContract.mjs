const TOP_LEVEL_KEYS = [
  "availability",
  "capturedAt",
  "cpu",
  "effectPerformed",
  "executionAuthority",
  "host",
  "init",
  "memory",
  "network",
  "power",
  "readOnly",
  "reason",
  "schemaVersion",
  "session",
  "source",
  "storage",
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

function finiteNumber(value, min = -Infinity, max = Infinity) {
  return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
}

function boundedString(value, max = 512) {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function nullableBoundedString(value, max = 512) {
  return value === null || boundedString(value, max);
}

function validPercent(value) {
  return finiteNumber(value, 0, 100);
}

export function validateHostObservation(snapshot) {
  const errors = [];

  if (!exactKeys(snapshot, TOP_LEVEL_KEYS)) {
    errors.push("top-level fields do not match phios.host-observation.v1");
    return { ok: false, errors };
  }

  if (snapshot.schemaVersion !== "phios.host-observation.v1") {
    errors.push("unsupported schemaVersion");
  }
  if (snapshot.source !== "linux-readonly-node-probe") {
    errors.push("local transport only accepts linux-readonly-node-probe source");
  }
  if (snapshot.readOnly !== true) errors.push("readOnly must be true");
  if (snapshot.executionAuthority !== false) errors.push("executionAuthority must be false");
  if (snapshot.effectPerformed !== false) errors.push("effectPerformed must be false");
  if (!["available", "unavailable"].includes(snapshot.availability)) {
    errors.push("availability must be available or unavailable");
  }
  if (
    !(
      (snapshot.availability === "available" && snapshot.reason === null) ||
      (snapshot.availability === "unavailable" && boundedString(snapshot.reason, 256))
    )
  ) {
    errors.push("reason must match host availability");
  }

  if (
    !boundedString(snapshot.capturedAt, 64) ||
    Number.isNaN(Date.parse(snapshot.capturedAt))
  ) {
    errors.push("capturedAt must be a valid timestamp");
  }

  if (
    !exactKeys(snapshot.host, ["arch", "hostname", "platform", "release"]) ||
    !boundedString(snapshot.host?.hostname, 255) ||
    !boundedString(snapshot.host?.platform, 64) ||
    !boundedString(snapshot.host?.release, 255) ||
    !boundedString(snapshot.host?.arch, 64)
  ) {
    errors.push("host observation is invalid");
  }

  if (
    !exactKeys(snapshot.session, ["sessionType", "shell", "uid", "username"]) ||
    !boundedString(snapshot.session?.username, 255) ||
    !(snapshot.session?.uid === null || Number.isInteger(snapshot.session?.uid)) ||
    !nullableBoundedString(snapshot.session?.shell, 512) ||
    !nullableBoundedString(snapshot.session?.sessionType, 128)
  ) {
    errors.push("session observation is invalid");
  }

  if (
    !exactKeys(snapshot.cpu, ["loadAverage", "logicalCores", "model"]) ||
    !Number.isInteger(snapshot.cpu?.logicalCores) ||
    snapshot.cpu.logicalCores < 1 ||
    snapshot.cpu.logicalCores > 4096 ||
    !boundedString(snapshot.cpu?.model, 512) ||
    !Array.isArray(snapshot.cpu?.loadAverage) ||
    snapshot.cpu.loadAverage.length !== 3 ||
    !snapshot.cpu.loadAverage.every((value) => finiteNumber(value, 0, 1_000_000))
  ) {
    errors.push("cpu observation is invalid");
  }

  if (
    !exactKeys(snapshot.memory, ["freeBytes", "totalBytes", "usedPercent"]) ||
    !finiteNumber(snapshot.memory?.totalBytes, 0, Number.MAX_SAFE_INTEGER) ||
    !finiteNumber(snapshot.memory?.freeBytes, 0, Number.MAX_SAFE_INTEGER) ||
    snapshot.memory.freeBytes > snapshot.memory.totalBytes ||
    !validPercent(snapshot.memory?.usedPercent)
  ) {
    errors.push("memory observation is invalid");
  }

  if (
    !exactKeys(snapshot.storage, ["freeBytes", "mount", "totalBytes", "usedPercent"]) ||
    snapshot.storage?.mount !== "/" ||
    !finiteNumber(snapshot.storage?.totalBytes, 0, Number.MAX_SAFE_INTEGER) ||
    !finiteNumber(snapshot.storage?.freeBytes, 0, Number.MAX_SAFE_INTEGER) ||
    snapshot.storage.freeBytes > snapshot.storage.totalBytes ||
    !validPercent(snapshot.storage?.usedPercent)
  ) {
    errors.push("storage observation is invalid");
  }

  if (!Array.isArray(snapshot.network) || snapshot.network.length > 64) {
    errors.push("network observation is invalid");
  } else {
    for (const item of snapshot.network) {
      if (
        !exactKeys(item, ["families", "internal", "name"]) ||
        !boundedString(item?.name, 128) ||
        !Array.isArray(item?.families) ||
        item.families.length > 8 ||
        !item.families.every((family) => boundedString(family, 32)) ||
        typeof item?.internal !== "boolean"
      ) {
        errors.push("network observation contains an invalid interface");
        break;
      }
    }
  }

  if (!Array.isArray(snapshot.power) || snapshot.power.length > 32) {
    errors.push("power observation is invalid");
  } else {
    for (const item of snapshot.power) {
      if (
        !exactKeys(item, ["capacityPercent", "name", "status", "type"]) ||
        !boundedString(item?.name, 128) ||
        !nullableBoundedString(item?.type, 128) ||
        !nullableBoundedString(item?.status, 128) ||
        !(item?.capacityPercent === null || validPercent(item.capacityPercent))
      ) {
        errors.push("power observation contains an invalid supply");
        break;
      }
    }
  }

  if (
    !exactKeys(snapshot.init, ["reason", "serviceStatusBound", "systemdPresent"]) ||
    typeof snapshot.init?.systemdPresent !== "boolean" ||
    snapshot.init?.serviceStatusBound !== false ||
    !boundedString(snapshot.init?.reason, 1024)
  ) {
    errors.push("init observation is invalid");
  }

  return { ok: errors.length === 0, errors };
}

export function assertValidHostObservation(snapshot) {
  const result = validateHostObservation(snapshot);
  if (!result.ok) {
    throw new Error(`invalid host observation: ${result.errors.join("; ")}`);
  }
  return snapshot;
}
