import { describe, expect, it } from "vitest";
import { PHIOFFICE_MANIFEST_SOURCE, encodeProjectRegistry } from "./projectRegistry";
import {
  PROJECT_REGISTRY_V2_FORMAT,
  PROJECT_REGISTRY_V2_KEY,
  PROJECT_REGISTRY_V2_VERSION,
  decodeProjectRegistryV2,
  encodeProjectRegistryV2,
  previewV1ToV2Migration,
  providerQualifiedProjectKey,
  validateQualifiedProjectEntry,
} from "./projectRegistryV2";

const source = PHIOFFICE_MANIFEST_SOURCE;
const v1 = { projectRef: "project:alpha", title: "Local Alpha", source } as const;
const alpha = { providerAppId: "phioffice", ...v1 } as const;
const beta = { providerAppId: "phioffice", projectRef: "project:beta", title: "Beta", source } as const;
const wire = (entries: unknown) => JSON.stringify({
  format: PROJECT_REGISTRY_V2_FORMAT,
  version: PROJECT_REGISTRY_V2_VERSION,
  entries,
});

describe("PhiOS provider-qualified project reference R8", () => {
  it("previews existing v1 entries without touching or upgrading saved data", () => {
    const old = encodeProjectRegistry([v1]);
    const before = old;
    const preview = previewV1ToV2Migration(old, null);
    expect(preview).toEqual({
      targetKey: PROJECT_REGISTRY_V2_KEY,
      entries: [alpha],
      recordCount: 1,
      destinationAlreadyOccupied: false,
      writesPerformed: 0,
      approvalCarriedOver: false,
    });
    expect(old).toBe(before);
    expect(preview.entries[0]).toEqual(alpha);
    expect(Object.isFrozen(preview)).toBe(true);
    expect(Object.isFrozen(preview.entries)).toBe(true);
    expect(Object.isFrozen(preview.entries[0])).toBe(true);
    expect(previewV1ToV2Migration(null, null).entries).toEqual([]);
    expect(JSON.parse(old).version).toBe(1);
  });

  it("validates exact four-field metadata only; v2 never inherits grant or credential data", () => {
    const json = encodeProjectRegistryV2([alpha, beta]);
    expect(decodeProjectRegistryV2(json)).toEqual([alpha, beta]);
    expect(Object.keys(JSON.parse(json).entries[0])).toEqual([
      "providerAppId", "projectRef", "title", "source",
    ]);
    expect(JSON.parse(json).version).toBe(2);
    for (const forbidden of ["grant", "credential", "token", "path", "owner",
      "manifest", "execution_authority", "read_approved", "artifacts"]) {
      expect(json).not.toContain('"' + forbidden + '"');
      expect(() => validateQualifiedProjectEntry({ ...alpha, [forbidden]: "private" })).toThrow();
    }
  });

  it("separates identically spelled project references by provider without admitting new providers", () => {
    expect(providerQualifiedProjectKey("phioffice", "project:alpha"))
      .not.toBe(providerQualifiedProjectKey("phimail", "project:alpha"));
    expect(providerQualifiedProjectKey("phioffice", "project:alpha"))
      .not.toBe(providerQualifiedProjectKey("phioffice", "project:beta"));
    expect(() => validateQualifiedProjectEntry({
      ...alpha, providerAppId: "phimail",
    })).toThrow("Provider/source mismatch");
    expect(() => validateQualifiedProjectEntry({
      ...alpha, source: "phicloud.project_manifest.v0.1",
    })).toThrow("Unreviewed project identity source");
    expect(() => decodeProjectRegistryV2(wire([alpha, alpha]))).toThrow("Duplicate");
  });

  it("fails closed on malformed registry or forged authority", () => {
    for (const invalid of [
      { ...alpha, title: "private\nstate" },
      { ...alpha, projectRef: "/home/user/secrets" },
      { ...alpha, providerAppId: "PhiOffice" },
      { ...alpha, arbitrary: true },
    ]) expect(() => decodeProjectRegistryV2(wire([invalid]))).toThrow();
    expect(() => decodeProjectRegistryV2("{")).toThrow("not JSON");
    expect(() => decodeProjectRegistryV2(wire(null))).toThrow();
    expect(() => decodeProjectRegistryV2(JSON.stringify({
      format: PROJECT_REGISTRY_V2_FORMAT, version: 2, entries: [],
      authorizations: ["all"],
    }))).toThrow("shape");
    expect(() => decodeProjectRegistryV2(JSON.stringify({
      format: PROJECT_REGISTRY_V2_FORMAT, version: 1, entries: [],
    }))).toThrow("version");
    expect(() => decodeProjectRegistryV2(" ".repeat(16385))).toThrow("16 KiB");
    expect(() => encodeProjectRegistryV2(Array.from({ length: 25 }, (_, i) => ({
      ...alpha, projectRef: "project:too-many-" + i,
    })))).toThrow("24 projects");
  });

  it("never replaces a preexisting v2 target, including malformed or incompatible data", () => {
    const legacy = encodeProjectRegistry([v1]);
    const existing = encodeProjectRegistryV2([beta]);
    expect(() => previewV1ToV2Migration(legacy, existing)).toThrow("refusing overwrite");
    expect(() => previewV1ToV2Migration(legacy, "{")).toThrow("not JSON");
    expect(() => previewV1ToV2Migration(legacy, encodeProjectRegistry([]))).toThrow("version");
    expect(() => previewV1ToV2Migration("{", null)).toThrow("not JSON");
  });

  it("migration has no dependency on browser storage, transport or app authorization", () => {
    const preview = previewV1ToV2Migration(encodeProjectRegistry([v1]), null);
    expect(preview.approvalCarriedOver).toBe(false);
    expect(preview.writesPerformed).toBe(0);
    expect(encodeProjectRegistryV2(preview.entries)).not.toContain("read_approved");
    for (const bad of ["", "https://example.com", "project:../oops", "project:a..b"]) {
      expect(() => providerQualifiedProjectKey("phioffice", bad)).toThrow();
    }
  });
});
