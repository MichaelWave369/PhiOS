/**
 * Local-only, explicit project selection for the PhiOffice bridge pilot.
 *
 * This is intentionally a narrow manifest-header reader, not a complete
 * PhiOffice manifest validator, project loader, sync adapter or auth token.
 * Never pass the source manifest, owner, artifacts, paths or tags to an app.
 */
export const MAX_PROJECT_MANIFEST_BYTES = 256 * 1024;
export const PROJECT_MANIFEST_SCHEMA = "phioffice369.project_manifest.v0.1";

export type SelectedProjectReference = Readonly<{
  projectRef: string;
  title: string;
}>;

function isRecord(input: unknown): input is Record<string, unknown> {
  return input !== null && typeof input === "object" && !Array.isArray(input);
}

export function extractProjectReference(text: string): SelectedProjectReference {
  if (typeof text !== "string"
    || new TextEncoder().encode(text).byteLength > MAX_PROJECT_MANIFEST_BYTES) {
    throw new Error("Project manifest must be a local JSON file under 256 KiB");
  }
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error("Project manifest is not valid JSON");
  }
  if (!isRecord(payload)
      || payload.schema !== PROJECT_MANIFEST_SCHEMA
      || typeof payload.projectId !== "string"
      || typeof payload.title !== "string"
      || typeof payload.description !== "string"
      || typeof payload.owner !== "string"
      || typeof payload.createdAt !== "string"
      || typeof payload.updatedAt !== "string"
      || !Array.isArray(payload.tags)
      || !payload.tags.every((tag) => typeof tag === "string")
      || !Array.isArray(payload.artifacts)) {
    throw new Error("Not a PhiOffice369 v0.1 project manifest header");
  }

  const title = payload.title.trim();
  const id = payload.projectId;
  // Keep the exact user-chosen project identity, never invent a replacement.
  // The bridge's wire prefix is a type marker, not an access capability.
  const rawId = id.startsWith("project:") ? id.slice("project:".length) : id;
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(rawId)
      || rawId.includes("..") || rawId.endsWith(".")
      || title.length < 1 || title.length > 120
      || payload.owner.trim().length === 0
      || payload.createdAt.length === 0 || payload.updatedAt.length === 0) {
    throw new Error("Project ID or display title cannot be represented safely");
  }
  return Object.freeze({ projectRef: `project:${rawId}`, title });
}
