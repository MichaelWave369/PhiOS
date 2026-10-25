/** A bounded, credential-free, read-only probe of Porch's public health route.
 * Port is fixed; a candidate response DOES NOT authenticate Porch's identity.
 * No request uses the operator's token or any private Porch API.
 */
export const PORCH_HEALTH_URL = "http://127.0.0.1:7331/health";
export const PORCH_HEALTH_SCHEMA = "phios.porch_health_preflight.v0.1";
const RESPONSE_LIMIT = 1024;

function receipt(outcome, candidate = null) {
  return {
    schemaVersion: PORCH_HEALTH_SCHEMA,
    endpoint: "127.0.0.1:7331/health",
    outcome,
    protocolVersion: candidate?.protocol_version ?? null,
    candidateVersion: candidate?.candidate ?? null,
    origin: "UNAUTHENTICATED_LOCAL_HEALTH",
    identityVerified: false,
    authenticationPerformed: false,
    modelExecutionAuthorized: false,
    peerAuthority: false,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
  };
}

function validCandidate(data) {
  return data !== null && !Array.isArray(data) &&
    typeof data === "object" &&
    Object.keys(data).sort().join(",") === "candidate,protocol_version,status" &&
    data.status === "READY" &&
    data.protocol_version === 1 &&
    typeof data.candidate === "string" &&
    /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(data.candidate) &&
    data.candidate.length <= 48;
}

async function readSmallJson(response) {
  const type = response.headers.get("content-type") ?? "";
  if (!/^application\/json(?:\s*;|$)/i.test(type) || !response.body) {
    throw new Error("invalid content type");
  }
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > RESPONSE_LIMIT) throw new Error("health response too large");
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const joined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    joined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(joined));
}

export async function probeLocalPorchCandidateHealth({ fetchImpl = globalThis.fetch } = {}) {
  try {
    const response = await fetchImpl(PORCH_HEALTH_URL, {
      method: "GET",
      redirect: "error",
      signal: AbortSignal.timeout(1500),
      headers: { accept: "application/json" },
    });
    if (response.status !== 200 || response.redirected) return receipt("UNAVAILABLE");
    let body;
    try {
      body = await readSmallJson(response);
    } catch {
      return receipt("INVALID_RESPONSE");
    }
    return validCandidate(body) ? receipt("CANDIDATE_RESPONSE_OBSERVED", body) :
      receipt("INVALID_RESPONSE");
  } catch {
    return receipt("UNAVAILABLE");
  }
}
