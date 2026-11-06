/* Source-bound, non-authoritative public site status helpers. */
export function latestAppTestLine(names) {
  if (!Array.isArray(names)) throw new TypeError("test inventory must be a list");
  const versions = names.flatMap((name) => {
    const match = typeof name === "string"
      ? /^test_app_platform_v([0-9]{3})[a-z0-9_]*\.py$/.exec(name)
      : null;
    return match ? [Number(match[1])] : [];
  });
  if (!versions.length) return "unverified";
  return "v0." + String(Math.max(...versions)).padStart(2, "0") + " tests";
}

export function publicLinuxImageIdentity(record) {
  if (!record || typeof record !== "object" ||
      typeof record.os_version !== "string" ||
      typeof record.stage !== "string" ||
      record.architecture !== "x86_64" ||
      typeof record.secure_boot !== "boolean") {
    throw new TypeError("unrecognized Linux image release contract");
  }
  return {
    version: record.os_version,
    stage: record.stage,
    architecture: record.architecture,
    secureBoot: record.secure_boot,
  };
}
