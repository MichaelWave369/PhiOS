/**
 * R8 read-only preparation for provider-qualified browser project identities.
 *
 * No writes, implicit migration, app installation, network calls, or grants.
 * Only current reviewed adapters can yield an admitted v2 registry entry.
 */
import {
  PROJECT_REGISTRY_FORMAT,
  PROJECT_REGISTRY_MAX_BYTES,
  PROJECT_REGISTRY_MAX_RECORDS,
  decodeProjectRegistry,
  validateRegistryEntry,
  type SavedProjectReference,
} from "./projectRegistry";
import { findReviewedProjectAdapter } from "./projectAdapters";

export const PROJECT_REGISTRY_V2_KEY = "phios.project-registry.v2";
export const PROJECT_REGISTRY_V2_FORMAT = PROJECT_REGISTRY_FORMAT;
export const PROJECT_REGISTRY_V2_VERSION = 2;

export type ProviderQualifiedProjectReference = Readonly<SavedProjectReference & {
  providerAppId: string;
}>;

/** A collision-free lookup token; never a credential or a wire project ref. */
export function providerQualifiedProjectKey(providerAppId: string, projectRef: string): string {
  if (typeof providerAppId !== "string" ||
      !/^[a-z][a-z0-9-]{0,63}$/.test(providerAppId) ||
      typeof projectRef !== "string" ||
      !/^project:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(projectRef) ||
      projectRef.includes("..") || projectRef.endsWith(".")) {
    throw new Error("Invalid provider-qualified project identity");
  }
  // The length-delimited JSON tuple cannot collide when either field varies.
  return JSON.stringify([providerAppId, projectRef]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exact(value: Record<string, unknown>, names: readonly string[]): boolean {
  return Object.keys(value).length === names.length &&
    Object.keys(value).every((key) => names.includes(key));
}

export function validateQualifiedProjectEntry(value: unknown): ProviderQualifiedProjectReference {
  if (!isRecord(value) || !exact(value, ["providerAppId", "projectRef", "title", "source"])) {
    throw new Error("Unsupported provider-qualified project fields");
  }
  const legacy = validateRegistryEntry({
    projectRef: value.projectRef,
    title: value.title,
    source: value.source,
  });
  const adapter = findReviewedProjectAdapter(legacy.source);
  if (!adapter || value.providerAppId !== adapter.providerAppId) {
    throw new Error("Provider/source mismatch or unreviewed project adapter");
  }
  providerQualifiedProjectKey(adapter.providerAppId, legacy.projectRef);
  return Object.freeze({
    providerAppId: adapter.providerAppId,
    projectRef: legacy.projectRef,
    title: legacy.title,
    source: legacy.source,
  });
}

function checkedEntries(entries: unknown): ProviderQualifiedProjectReference[] {
  if (!Array.isArray(entries) || entries.length > PROJECT_REGISTRY_MAX_RECORDS) {
    throw new Error("Provider-qualified registry exceeds 24 projects");
  }
  const verified = entries.map(validateQualifiedProjectEntry);
  const ids = verified.map((entry) =>
    providerQualifiedProjectKey(entry.providerAppId, entry.projectRef));
  if (new Set(ids).size !== ids.length) {
    throw new Error("Duplicate provider-qualified project identities");
  }
  return verified;
}

export function decodeProjectRegistryV2(json: string): ProviderQualifiedProjectReference[] {
  if (typeof json !== "string" ||
      new TextEncoder().encode(json).byteLength > PROJECT_REGISTRY_MAX_BYTES) {
    throw new Error("Provider-qualified registry exceeds 16 KiB");
  }
  let data: unknown;
  try { data = JSON.parse(json); }
  catch { throw new Error("Provider-qualified registry is not JSON"); }
  if (!isRecord(data) || !exact(data, ["format", "version", "entries"]) ||
      data.format !== PROJECT_REGISTRY_V2_FORMAT ||
      data.version !== PROJECT_REGISTRY_V2_VERSION) {
    throw new Error("Unrecognized provider-qualified registry version or shape");
  }
  return checkedEntries(data.entries);
}

export function encodeProjectRegistryV2(entries: readonly ProviderQualifiedProjectReference[]): string {
  const json = JSON.stringify({
    format: PROJECT_REGISTRY_V2_FORMAT,
    version: PROJECT_REGISTRY_V2_VERSION,
    entries: checkedEntries(entries),
  }) + "\n";
  decodeProjectRegistryV2(json);
  return json;
}

export type V2MigrationPreview = Readonly<{
  targetKey: typeof PROJECT_REGISTRY_V2_KEY;
  entries: readonly ProviderQualifiedProjectReference[];
  recordCount: number;
  destinationAlreadyOccupied: false;
  writesPerformed: 0;
  approvalCarriedOver: false;
}>;

/**
 * Read-only v1 -> v2 preview.
 * Refuses to overwrite any existing v2 bytes, even valid ones.
 * It never reads localStorage, modifies v1, or persists anything.
 */
export function previewV1ToV2Migration(
  legacyRaw: string | null, existingV2Raw: string | null,
): V2MigrationPreview {
  if (existingV2Raw !== null) {
    // Distinguish an already valid target from unexpected or corrupt bytes.
    // Neither is ever replaced implicitly.
    decodeProjectRegistryV2(existingV2Raw);
    throw new Error("Provider-qualified v2 already exists; refusing overwrite");
  }
  const legacy = legacyRaw === null ? [] : decodeProjectRegistry(legacyRaw);
  const qualified = legacy.map((entry) => {
    const adapter = findReviewedProjectAdapter(entry.source);
    if (!adapter) throw new Error("Unreviewed legacy source cannot migrate");
    return validateQualifiedProjectEntry({
      ...entry, providerAppId: adapter.providerAppId,
    });
  });
  const checked = decodeProjectRegistryV2(encodeProjectRegistryV2(qualified));
  return Object.freeze({
    targetKey: PROJECT_REGISTRY_V2_KEY,
    entries: Object.freeze(checked),
    recordCount: checked.length,
    destinationAlreadyOccupied: false,
    writesPerformed: 0,
    approvalCarriedOver: false,
  });
}
