import { describe, expect, it } from "vitest";
import {
  PORTABLE_PROJECT_BUNDLE_FORMAT,
  PORTABLE_PROJECT_BUNDLE_VERSION,
  decodePortableProjectBundle,
  encodePortableProjectBundle,
  previewProjectBundleMerge,
} from "./projectRegistryPortable";
import {
  PHIOFFICE_MANIFEST_SOURCE,
  PROJECT_REGISTRY_MAX_RECORDS,
  type SavedProjectReference,
} from "./projectRegistry";

const example: SavedProjectReference = {
  projectRef: "project:example-01",
  title: "Example",
  source: PHIOFFICE_MANIFEST_SOURCE,
};
const other: SavedProjectReference = {
  projectRef: "project:second",
  title: "Second",
  source: PHIOFFICE_MANIFEST_SOURCE,
};
const bundle = (entries: unknown, extras = {}) => JSON.stringify({
  format: PORTABLE_PROJECT_BUNDLE_FORMAT,
  version: PORTABLE_PROJECT_BUNDLE_VERSION,
  entries, ...extras,
});

describe("portable PhiOS project reference bundle v1", () => {
  it("round-trips only the exact three metadata fields, never rights or files", () => {
    const json = encodePortableProjectBundle([example, other]);
    expect(decodePortableProjectBundle(json)).toEqual([example, other]);
    const parsed = JSON.parse(json);
    expect(Object.keys(parsed)).toEqual(["format", "version", "entries"]);
    expect(Object.keys(parsed.entries[0])).toEqual(["projectRef", "title", "source"]);
    for (const privateField of ["authorization", "read_approved", "execution_authority",
      "manifest", "artifact", "token", "path", "password", "capability"]) {
      expect(json).not.toContain('"' + privateField + '"');
    }
  });

  it("rejects format confusion, extra properties, unknown providers and forged grants", () => {
    const original = JSON.parse(encodePortableProjectBundle([example]));
    for (const bad of [
      { ...original, grant: true },
      { ...original, version: 2 },
      { ...original, format: "phios.project-registry" },
      { ...original, entries: [{ ...example, permission: "all" }] },
      { ...original, entries: [{ ...example, token: "secret" }] },
      { ...original, entries: [{ ...example, source: "phicloud.unreviewed.v0" }] },
      { ...original, entries: [example, example] },
      { ...original, entries: null },
    ]) expect(() => decodePortableProjectBundle(JSON.stringify(bad))).toThrow();
    expect(() => decodePortableProjectBundle("{")).toThrow("not JSON");
    expect(() => decodePortableProjectBundle(" ".repeat(16385))).toThrow("16 KiB");
  });

  it("non-destructively merges imported new references and keeps local titles", () => {
    const local: SavedProjectReference = { ...example, title: "My local title" };
    const incoming: SavedProjectReference = { ...example, title: "Overwritten?" };
    const preview = previewProjectBundleMerge([local], [incoming, other]);
    expect(preview.added).toBe(1);
    expect(preview.skipped).toBe(1);
    expect(preview.entries).toEqual([local, other]);
    expect(local.title).toBe("My local title");
    expect(previewProjectBundleMerge([], [])).toEqual({ entries: [], added: 0, skipped: 0 });
  });

  it("rejects oversized merge atomically without truncating local records", () => {
    const full = Array.from({ length: PROJECT_REGISTRY_MAX_RECORDS }, (_, i): SavedProjectReference => ({
      projectRef: "project:local-" + i,
      title: "Local " + i,
      source: PHIOFFICE_MANIFEST_SOURCE,
    }));
    expect(() => previewProjectBundleMerge(full, [other])).toThrow("no changes applied");
    expect(full).toHaveLength(PROJECT_REGISTRY_MAX_RECORDS);
    expect(full[0].projectRef).toBe("project:local-0");
  });
});
