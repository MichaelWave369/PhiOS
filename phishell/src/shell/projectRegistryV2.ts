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

/**
 * V2 has a separate, metadata-only review boundary from the V1 bridge.
 * PixelForge's merged sidecar is accepted as an identity label only.
 * It is deliberately NOT in the PhiOS executable/browser adapter catalog.
 */
export const PIXELFORGE_V2_IDENTITY_SOURCE =
  "pixelforge.phios-vr-world-identity.v0.1" as const;
export const PIXELFORGE_V2_PROVIDER = "pixelforge" as const;

export type ProviderQualifiedProjectReference = Readonly<
  Omit<SavedProjectReference, "source"> & {
    source: string;
    providerAppId: string;
  }
>;

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
  if (value.source === PIXELFORGE_V2_IDENTITY_SOURCE) {
    // The merged PixelForge producer accepts bounded titles and stable
    // operator-chosen IDs, but gives no attestation or execution authority.
    // This metadata path NEVER registers PixelForge as a browser target.
    if (value.providerAppId !== PIXELFORGE_V2_PROVIDER ||
        typeof value.projectRef !== "string" ||
        !/^project:[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(value.projectRef) ||
        value.projectRef.includes("..") || value.projectRef.endsWith(".") ||
        typeof value.title !== "string" || value.title.length < 1 ||
        value.title.length > 100 || value.title !== value.title.trim() ||
        /[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/.test(value.title)) {
      throw new Error("Invalid PixelForge V2-only identity metadata");
    }
    providerQualifiedProjectKey(PIXELFORGE_V2_PROVIDER, value.projectRef);
    return Object.freeze({
      providerAppId: PIXELFORGE_V2_PROVIDER,
      projectRef: value.projectRef,
      title: value.title,
      source: PIXELFORGE_V2_IDENTITY_SOURCE,
    });
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
