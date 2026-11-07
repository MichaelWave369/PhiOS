/**
 * PhiOS browser-local project reference registry v1.
 *
 * Explicitly operator-saved metadata only. Never store file contents,
 * manifests, grants, permissions, cloud tokens, or executable app state.
 * This module does not provide or imply access to any project artifacts.
 */
import type { SelectedProjectReference } from "./projectManifestSelection";

export const PROJECT_REGISTRY_KEY = "phios.project-registry.v1";
export const PROJECT_REGISTRY_FORMAT = "phios.project-registry";
export const PROJECT_REGISTRY_VERSION = 1;
export const PROJECT_REGISTRY_MAX_BYTES = 16 * 1024;
export const PROJECT_REGISTRY_MAX_RECORDS = 24;
export const PHIOFFICE_MANIFEST_SOURCE = "phioffice369.project_manifest.v0.1";

export type SavedProjectReference = Readonly<SelectedProjectReference & {
  source: typeof PHIOFFICE_MANIFEST_SOURCE;
}>;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactly(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length
    && Object.keys(value).every((key) => keys.includes(key));
}

export function validateRegistryEntry(value: unknown): SavedProjectReference {
  if (!record(value) || !exactly(value, ["projectRef", "title", "source"])) {
    throw new Error("Saved project has unsupported fields");
  }
  const { projectRef, title, source } = value;
  if (typeof projectRef !== "string"
    || !/^project:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(projectRef)
    || projectRef.includes("..") || projectRef.endsWith(".")) {
    throw new Error("Saved project reference is invalid");
  }
  if (typeof title !== "string" || title.length < 1 || title.length > 120
    || title !== title.trim() || /[\u0000-\u001f\u007f]/.test(title)) {
    throw new Error("Saved project display title is invalid");
  }
  if (source !== PHIOFFICE_MANIFEST_SOURCE) {
    throw new Error("Unreviewed project identity source");
  }
  return Object.freeze({ projectRef, title, source });
}

function checkedEntries(input: unknown): SavedProjectReference[] {
  if (!Array.isArray(input) || input.length > PROJECT_REGISTRY_MAX_RECORDS) {
    throw new Error("Saved project list exceeds 24 projects");
  }
  const entries = input.map(validateRegistryEntry);
  if (new Set(entries.map(({ projectRef }) => projectRef)).size !== entries.length) {
    throw new Error("Saved project list contains duplicate identities");
  }
  return entries;
}

export function decodeProjectRegistry(json: string): SavedProjectReference[] {
  if (typeof json !== "string"
    || new TextEncoder().encode(json).byteLength > PROJECT_REGISTRY_MAX_BYTES) {
    throw new Error("Saved project registry exceeds 16 KiB");
  }
  let value: unknown;
  try { value = JSON.parse(json); } catch { throw new Error("Saved project registry is not JSON"); }
  if (!record(value)
    || !exactly(value, ["format", "version", "entries"])
    || value.format !== PROJECT_REGISTRY_FORMAT
    || value.version !== PROJECT_REGISTRY_VERSION) {
    throw new Error("Unrecognized project registry version or shape");
  }
  return checkedEntries(value.entries);
}

export function encodeProjectRegistry(entries: readonly SavedProjectReference[]): string {
  const serialized = JSON.stringify({
    format: PROJECT_REGISTRY_FORMAT,
    version: PROJECT_REGISTRY_VERSION,
    entries: checkedEntries(entries),
  });
  decodeProjectRegistry(serialized);
  return serialized + "\n";
}

export function rememberProject(
  entries: readonly SavedProjectReference[],
  selected: SelectedProjectReference,
): SavedProjectReference[] {
  const candidate = validateRegistryEntry({
    projectRef: selected.projectRef,
    title: selected.title,
    source: PHIOFFICE_MANIFEST_SOURCE,
  });
  return checkedEntries([
    candidate,
    ...entries.filter(({ projectRef }) => projectRef !== candidate.projectRef),
  ]);
}

export function forgetProject(
  entries: readonly SavedProjectReference[], projectRef: string,
): SavedProjectReference[] {
  return checkedEntries(entries.filter((entry) => entry.projectRef !== projectRef));
}

export function loadProjectRegistry(
  storage: Pick<Storage, "getItem"> = globalThis.localStorage,
): SavedProjectReference[] {
  const json = storage.getItem(PROJECT_REGISTRY_KEY);
  return json === null ? [] : decodeProjectRegistry(json);
}

export function storeProjectRegistry(
  entries: readonly SavedProjectReference[],
  storage: Pick<Storage, "setItem"> = globalThis.localStorage,
): void {
  storage.setItem(PROJECT_REGISTRY_KEY, encodeProjectRegistry(entries));
}
