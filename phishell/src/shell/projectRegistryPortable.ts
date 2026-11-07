/**
 * Explicit, metadata-only, offline project reference portability.
 * Not a backup of project files, a grant, an app-install manifest or a
 * provider-authenticated registry. No network requests or credential fields.
 */
import {
  PROJECT_REGISTRY_FORMAT,
  PROJECT_REGISTRY_MAX_BYTES,
  PROJECT_REGISTRY_MAX_RECORDS,
  PROJECT_REGISTRY_VERSION,
  decodeProjectRegistry,
  encodeProjectRegistry,
  type SavedProjectReference,
} from "./projectRegistry";

export const PORTABLE_PROJECT_BUNDLE_FORMAT = "phios.project-references";
export const PORTABLE_PROJECT_BUNDLE_VERSION = 1;
export const PORTABLE_PROJECT_BUNDLE_MAX_BYTES = PROJECT_REGISTRY_MAX_BYTES;

type BundleHeader = {
  entries: unknown;
  format: unknown;
  version: unknown;
};

export function decodePortableProjectBundle(json: string): SavedProjectReference[] {
  if (typeof json !== "string"
      || new TextEncoder().encode(json).byteLength > PORTABLE_PROJECT_BUNDLE_MAX_BYTES) {
    throw new Error("Portable project reference file exceeds 16 KiB");
  }
  let value: unknown;
  try { value = JSON.parse(json); } catch { throw new Error("Portable project references are not JSON"); }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Unsupported project reference bundle");
  }
  const header = value as BundleHeader;
  if (Object.keys(value).length !== 3
      || !Object.keys(value).every((key) => ["format", "version", "entries"].includes(key))
      || header.format !== PORTABLE_PROJECT_BUNDLE_FORMAT
      || header.version !== PORTABLE_PROJECT_BUNDLE_VERSION) {
    throw new Error("Unsupported project reference bundle format or version");
  }
  // Reuse the strict versioned registry codec, including entry field
  // allowlist, duplicate checks, limits and reviewed provider allowlist.
  return decodeProjectRegistry(JSON.stringify({
    format: PROJECT_REGISTRY_FORMAT,
    version: PROJECT_REGISTRY_VERSION,
    entries: header.entries,
  }));
}

export function encodePortableProjectBundle(entries: readonly SavedProjectReference[]): string {
  const verified = decodeProjectRegistry(encodeProjectRegistry(entries));
  const json = JSON.stringify({
    format: PORTABLE_PROJECT_BUNDLE_FORMAT,
    version: PORTABLE_PROJECT_BUNDLE_VERSION,
    entries: verified,
  }) + "\n";
  // Portable bundle must itself satisfy the external-input size constraint.
  decodePortableProjectBundle(json);
  return json;
}

export type ProjectBundleMergePreview = Readonly<{
  entries: SavedProjectReference[];
  added: number;
  skipped: number;
}>;

/**
 * Non-destructive import: existing browser entries win on identical IDs,
 * imported new IDs are appended. If capacity is exceeded, reject entirely.
 * No implicit persistence, selection or approval.
 */
export function previewProjectBundleMerge(
  existing: readonly SavedProjectReference[],
  incoming: readonly SavedProjectReference[],
): ProjectBundleMergePreview {
  const current = decodeProjectRegistry(encodeProjectRegistry(existing));
  const proposed = decodeProjectRegistry(encodeProjectRegistry(incoming));
  const seen = new Set(current.map((entry) => entry.projectRef));
  const additions = proposed.filter((entry) => !seen.has(entry.projectRef));
  const skipped = proposed.length - additions.length;
  if (current.length + additions.length > PROJECT_REGISTRY_MAX_RECORDS) {
    throw new Error("Import exceeds the 24-project registry limit; no changes applied");
  }
  const entries = decodeProjectRegistry(encodeProjectRegistry([...current, ...additions]));
  return Object.freeze({ entries, added: additions.length, skipped });
}
