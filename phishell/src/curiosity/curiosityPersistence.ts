import type { SymbolLabNode } from "./symbolLab";

export interface CuriosityAuthorityHealth {
  schemaVersion: "phios.curiosity-authority-broker.v0.5";
  brokerId: "phios.curiosity-authority-broker.local.v0.5";
  localOnly: true;
  principalId: string;
  capabilityId: "curiosity.persist";
  permission: "curiosity.write";
  approvalMode: "local_cli_hmac_exact_payload";
  browserCanApprove: false;
  browserReceivesLease: false;
  status: "ready";
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: false;
}

export type CuriosityPersistStatus =
  | "pending"
  | "approved"
  | "succeeded"
  | "held"
  | "failed"
  | "expired";

export interface CuriosityPersistRequest {
  schemaVersion: "phios.curiosity-persist-request.v0.5";
  requestId: string;
  payload: {
    schema_version: "phios.curiosity_persist_payload.v0.4";
    artifact_kind: SymbolLabNode["kind"];
    title: string;
    content: string;
    created_at: string;
    created_by: string;
    tags: string[];
    evidence_ref_sha256s: string[];
    parent_artifact_sha256s: string[];
  };
  payloadSha256: string;
  requestedAt: string;
  expiresAt: string;
  status: CuriosityPersistStatus;
  reason: string;
  approvedAt: string | null;
  artifactSha256: string | null;
  executionReceipt: Record<string, unknown> | null;
  approvalCommand: string;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: boolean;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha256(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function validHealth(value: unknown): value is CuriosityAuthorityHealth {
  if (!record(value)) return false;
  return (
    value.schemaVersion === "phios.curiosity-authority-broker.v0.5" &&
    value.brokerId === "phios.curiosity-authority-broker.local.v0.5" &&
    value.localOnly === true &&
    typeof value.principalId === "string" &&
    value.capabilityId === "curiosity.persist" &&
    value.permission === "curiosity.write" &&
    value.approvalMode === "local_cli_hmac_exact_payload" &&
    value.browserCanApprove === false &&
    value.browserReceivesLease === false &&
    value.status === "ready" &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === false
  );
}

function validRequest(value: unknown): value is CuriosityPersistRequest {
  if (!record(value) || !record(value.payload)) return false;
  const statuses = new Set([
    "pending",
    "approved",
    "succeeded",
    "held",
    "failed",
    "expired",
  ]);
  return (
    value.schemaVersion === "phios.curiosity-persist-request.v0.5" &&
    typeof value.requestId === "string" &&
    /^curiosity-request-[0-9a-f]{32}$/.test(value.requestId) &&
    sha256(value.payloadSha256) &&
    timestamp(value.requestedAt) &&
    timestamp(value.expiresAt) &&
    statuses.has(String(value.status)) &&
    typeof value.reason === "string" &&
    (value.approvedAt === null || timestamp(value.approvedAt)) &&
    (value.artifactSha256 === null || sha256(value.artifactSha256)) &&
    (value.executionReceipt === null || record(value.executionReceipt)) &&
    typeof value.approvalCommand === "string" &&
    value.approvalCommand.startsWith(
      "python -m phios.curiosity_authority_broker approve curiosity-request-",
    ) &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    typeof value.effectPerformed === "boolean"
  );
}

export function canonicalParentHashes(node: SymbolLabNode): string[] | null {
  const hashes: string[] = [];
  for (const parentId of node.parentIds) {
    if (!parentId.startsWith("canonical:")) return null;
    const digest = parentId.slice("canonical:".length);
    if (!sha256(digest)) return null;
    hashes.push(digest);
  }
  return [...new Set(hashes)].sort();
}

export function nodeToPersistPayload(node: SymbolLabNode) {
  if (node.id.startsWith("canonical:")) return null;
  const parents = canonicalParentHashes(node);
  if (parents === null) return null;
  return {
    artifact_kind: node.kind,
    title: node.title,
    content: node.content,
    created_at: node.createdAt,
    tags: [...node.tags].sort(),
    evidence_ref_sha256s: [] as string[],
    parent_artifact_sha256s: parents,
  };
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function createCuriosityPersistenceClient({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2000,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  async function call(path: string, init: RequestInit): Promise<unknown> {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetcher(path, {
        ...init,
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      });
      if (!response.ok) return null;
      return await readJson(response);
    } catch {
      return null;
    } finally {
      globalThis.clearTimeout(timeout);
    }
  }

  return {
    async health(): Promise<CuriosityAuthorityHealth | null> {
      const value = await call("/api/v1/curiosity-authority", {
        method: "GET",
        headers: { accept: "application/json" },
      });
      return validHealth(value) ? value : null;
    },

    async request(node: SymbolLabNode): Promise<CuriosityPersistRequest | null> {
      const payload = nodeToPersistPayload(node);
      if (!payload) return null;
      const value = await call("/api/v1/curiosity/persist-requests", {
        method: "POST",
        headers: {
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      return validRequest(value) ? value : null;
    },

    async status(requestId: string): Promise<CuriosityPersistRequest | null> {
      if (!/^curiosity-request-[0-9a-f]{32}$/.test(requestId)) return null;
      const value = await call(
        `/api/v1/curiosity/persist-requests/${requestId}`,
        {
          method: "GET",
          headers: { accept: "application/json" },
        },
      );
      return validRequest(value) ? value : null;
    },
  };
}

export const curiosityPersistenceClient = createCuriosityPersistenceClient();
