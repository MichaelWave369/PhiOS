import type { ClaimClass, SymbolKind, SymbolLabNode } from "./symbolLab";

export interface CanonicalCuriosityArtifact {
  schema_version: "phios.curiosity_artifact.v0.1";
  lane: "curiosity";
  artifact_kind: SymbolKind;
  claim_class: ClaimClass;
  title: string;
  content: string;
  created_at: string;
  created_by: string;
  tags: string[];
  evidence_ref_sha256s: string[];
  parent_artifact_sha256s: string[];
  effect_performed: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  curiosity_artifact_sha256: string;
}

export interface CuriosityProjection {
  schemaVersion: "phios.curiosity-projection.v0.4";
  source: "canonical-curiosity-store";
  generatedAt: string;
  persistent: true;
  writeAvailable: false;
  writeHoldReason: "action_lease_broker_unavailable";
  limit: number;
  count: number;
  omittedArtifactCount: number;
  artifacts: CanonicalCuriosityArtifact[];
  returnPointers: unknown[];
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: false;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function validArtifact(value: unknown): value is CanonicalCuriosityArtifact {
  if (!record(value)) return false;
  const kinds = [
    "symbol",
    "metaphor",
    "question",
    "hypothesis",
    "association",
    "pattern",
    "dream_fragment",
    "creative_seed",
  ];
  const claims = ["non_claim", "open_question", "hypothesis", "unverified_association"];
  return (
    value.schema_version === "phios.curiosity_artifact.v0.1" &&
    value.lane === "curiosity" &&
    kinds.includes(String(value.artifact_kind)) &&
    claims.includes(String(value.claim_class)) &&
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
    value.effect_performed === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.curiosity_artifact_sha256)
  );
}

function validEnvelope(value: unknown): value is { projection: CuriosityProjection } {
  if (!record(value) || !record(value.projection)) return false;
  const projection = value.projection;
  return (
    value.transportSchemaVersion === "phios.curiosity-transport.v0.4" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-curiosity-store-reader" &&
    value.localOnly === true &&
    value.readOnly === true &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === false &&
    timestamp(value.servedAt) &&
    projection.schemaVersion === "phios.curiosity-projection.v0.4" &&
    projection.source === "canonical-curiosity-store" &&
    timestamp(projection.generatedAt) &&
    projection.persistent === true &&
    projection.writeAvailable === false &&
    projection.writeHoldReason === "action_lease_broker_unavailable" &&
    typeof projection.count === "number" &&
    Number.isInteger(projection.count) &&
    projection.count >= 0 &&
    typeof projection.limit === "number" &&
    Number.isInteger(projection.limit) &&
    projection.limit >= 1 &&
    projection.limit <= 64 &&
    Array.isArray(projection.artifacts) &&
    projection.artifacts.length === projection.count &&
    projection.artifacts.every(validArtifact) &&
    Array.isArray(projection.returnPointers) &&
    projection.operationalAuthority === false &&
    projection.actionAuthority === false &&
    projection.executionAuthority === false &&
    projection.effectPerformed === false
  );
}

export function canonicalArtifactToSessionNode(
  artifact: CanonicalCuriosityArtifact,
): SymbolLabNode {
  return {
    id: `canonical:${artifact.curiosity_artifact_sha256}`,
    kind: artifact.artifact_kind,
    claimClass: artifact.claim_class,
    title: artifact.title,
    content: artifact.content,
    tags: [...artifact.tags],
    parentIds: artifact.parent_artifact_sha256s.map((sha256) => `canonical:${sha256}`),
    createdAt: artifact.created_at,
    returnPointers: [],
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
  };
}

export function createCuriosityProjectionProvider({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 1800,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    readOnly: true as const,
    writeAvailable: false as const,
    executionAuthority: false as const,
    async read(): Promise<CuriosityProjection | null> {
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher("/api/v1/curiosity", {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) return null;
        const payload: unknown = await response.json();
        return validEnvelope(payload) ? payload.projection : null;
      } catch {
        return null;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const curiosityProjectionProvider = createCuriosityProjectionProvider();
