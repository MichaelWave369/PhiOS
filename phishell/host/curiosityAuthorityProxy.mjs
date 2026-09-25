const BROKER_HOST = "127.0.0.1";
const DEFAULT_BROKER_PORT = 3972;

function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function sha(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}
function timestamp(value) {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}
function zeroAuthority(value) {
  return record(value) &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false;
}

export function validateBrokerHealth(value) {
  return zeroAuthority(value) &&
    value.schemaVersion === "phios.curiosity-authority-broker.v0.5" &&
    value.brokerId === "phios.curiosity-authority-broker.local.v0.5" &&
    value.localOnly === true &&
    value.capabilityId === "curiosity.persist" &&
    value.permission === "curiosity.write" &&
    value.approvalMode === "local_cli_hmac_exact_payload" &&
    value.browserCanApprove === false &&
    value.browserReceivesLease === false &&
    value.status === "ready" &&
    value.effectPerformed === false &&
    typeof value.principalId === "string";
}

export function validatePersistRequest(value) {
  if (!zeroAuthority(value) || !record(value.payload)) return false;
  const validStatus = ["pending", "approved", "succeeded", "held", "failed", "expired"];
  return value.schemaVersion === "phios.curiosity-persist-request.v0.5" &&
    typeof value.requestId === "string" &&
    sha(value.payloadSha256) &&
    timestamp(value.requestedAt) &&
    timestamp(value.expiresAt) &&
    validStatus.includes(value.status) &&
    typeof value.reason === "string" &&
    typeof value.approvalCommand === "string" &&
    value.approvalCommand.startsWith("python -m phios.curiosity_authority_broker approve ") &&
    typeof value.payload.artifact_kind === "string" &&
    typeof value.payload.title === "string" &&
    typeof value.payload.content === "string" &&
    typeof value.payload.created_by === "string" &&
    Array.isArray(value.payload.tags) &&
    (value.effectPerformed === true) === (value.status === "succeeded");
}

export function brokerPort(env = process.env) {
  const raw = env.PHIOS_CURIOSITY_BROKER_PORT;
  if (raw === undefined) return DEFAULT_BROKER_PORT;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("PHIOS_CURIOSITY_BROKER_PORT must be an integer from 1024 to 65535");
  }
  return port;
}

async function fetchJson(url, init, fetcher, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(url, { ...init, signal: controller.signal });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function fetchBrokerHealth({
  fetcher = globalThis.fetch.bind(globalThis),
  port = brokerPort(),
  timeoutMs = 1500,
} = {}) {
  const payload = await fetchJson(
    `http://${BROKER_HOST}:${port}/api/v1/health`,
    { method: "GET", cache: "no-store", headers: { accept: "application/json" } },
    fetcher,
    timeoutMs,
  );
  return validateBrokerHealth(payload) ? payload : null;
}

export async function createPersistRequest(payload, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = brokerPort(),
  timeoutMs = 1800,
} = {}) {
  const response = await fetchJson(
    `http://${BROKER_HOST}:${port}/api/v1/curiosity/persist-requests`,
    {
      method: "POST",
      cache: "no-store",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
    fetcher,
    timeoutMs,
  );
  return validatePersistRequest(response) ? response : null;
}

export async function fetchPersistRequest(requestId, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = brokerPort(),
  timeoutMs = 1500,
} = {}) {
  if (typeof requestId !== "string" || !/^curiosity-request-[0-9a-f]{32}$/.test(requestId)) {
    return null;
  }
  const payload = await fetchJson(
    `http://${BROKER_HOST}:${port}/api/v1/curiosity/persist-requests/${requestId}`,
    { method: "GET", cache: "no-store", headers: { accept: "application/json" } },
    fetcher,
    timeoutMs,
  );
  return validatePersistRequest(payload) ? payload : null;
}

export { BROKER_HOST, DEFAULT_BROKER_PORT };
