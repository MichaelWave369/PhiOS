const CURIOSITY_HOST = "127.0.0.1";
const DEFAULT_CURIOSITY_PORT = 3971;
const MAX_CURIOSITY_ARTIFACTS = 64;

function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function timestamp(value) {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function zeroAuthority(value) {
  return (
    record(value) &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    value.effect_performed === false
  );
}

function validArtifact(value) {
  return (
    zeroAuthority(value) &&
    value.schema_version === "phios.curiosity_artifact.v0.1" &&
    value.lane === "curiosity" &&
    typeof value.artifact_kind === "string" &&
    typeof value.claim_class === "string" &&
    typeof value.title === "string" &&
    typeof value.content === "string" &&
    timestamp(value.created_at) &&
    typeof value.created_by === "string" &&
    Array.isArray(value.tags) &&
    value.tags.every((item) => typeof item === "string") &&
    Array.isArray(value.evidence_ref_sha256s) &&
    value.evidence_ref_sha256s.every(sha) &&
    Array.isArray(value.parent_artifact_sha256s) &&
    value.parent_artifact_sha256s.every(sha) &&
    sha(value.curiosity_artifact_sha256)
  );
}

function validReturnPointer(value) {
  return (
    zeroAuthority(value) &&
    value.schema_version === "phios.curiosity_return_pointer.v0.2" &&
    sha(value.artifact_sha256) &&
    timestamp(value.created_at) &&
    typeof value.created_by === "string" &&
    typeof value.return_prompt === "string" &&
    typeof value.context === "string" &&
    Array.isArray(value.tags) &&
    value.tags.every((item) => typeof item === "string") &&
    sha(value.return_pointer_sha256)
  );
}

export function validateCuriosityProjectionEnvelope(value) {
  if (!record(value) || !record(value.projection)) return false;
  if (
    value.transportSchemaVersion !== "phios.curiosity-transport.v0.4" ||
    value.transport !== "loopback-http" ||
    value.transportIdentity !== "phios-curiosity-store-reader" ||
    value.localOnly !== true ||
    value.readOnly !== true ||
    value.operationalAuthority !== false ||
    value.actionAuthority !== false ||
    value.executionAuthority !== false ||
    value.effectPerformed !== false ||
    !timestamp(value.servedAt)
  ) {
    return false;
  }

  const projection = value.projection;
  return (
    projection.schemaVersion === "phios.curiosity-projection.v0.4" &&
    projection.source === "canonical-curiosity-store" &&
    timestamp(projection.generatedAt) &&
    projection.persistent === true &&
    projection.writeAvailable === false &&
    projection.writeHoldReason === "action_lease_broker_unavailable" &&
    Number.isInteger(projection.limit) &&
    projection.limit >= 1 &&
    projection.limit <= MAX_CURIOSITY_ARTIFACTS &&
    Number.isInteger(projection.count) &&
    projection.count >= 0 &&
    projection.count <= projection.limit &&
    Number.isInteger(projection.omittedArtifactCount) &&
    projection.omittedArtifactCount >= 0 &&
    Array.isArray(projection.artifacts) &&
    projection.artifacts.length === projection.count &&
    projection.artifacts.every(validArtifact) &&
    Array.isArray(projection.returnPointers) &&
    projection.returnPointers.every(validReturnPointer) &&
    projection.operationalAuthority === false &&
    projection.actionAuthority === false &&
    projection.executionAuthority === false &&
    projection.effectPerformed === false
  );
}

export function curiositySidecarPort(env = process.env) {
  const raw = env.PHIOS_CURIOSITY_PORT;
  if (raw === undefined) return DEFAULT_CURIOSITY_PORT;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("PHIOS_CURIOSITY_PORT must be an integer from 1024 to 65535");
  }
  return port;
}

export async function fetchCuriosityProjection({
  fetcher = globalThis.fetch.bind(globalThis),
  port = curiositySidecarPort(),
  limit = 32,
  timeoutMs = 1500,
} = {}) {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("Curiosity sidecar port must be an integer from 1024 to 65535");
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_CURIOSITY_ARTIFACTS) {
    throw new Error("Curiosity projection limit must be an integer from 1 to 64");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(
      `http://${CURIOSITY_HOST}:${port}/api/v1/curiosity?limit=${limit}`,
      {
        method: "GET",
        cache: "no-store",
        headers: { accept: "application/json" },
        signal: controller.signal,
      },
    );
    if (!response.ok) return null;
    const payload = await response.json();
    return validateCuriosityProjectionEnvelope(payload) ? payload : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export {
  CURIOSITY_HOST,
  DEFAULT_CURIOSITY_PORT,
  MAX_CURIOSITY_ARTIFACTS,
};
