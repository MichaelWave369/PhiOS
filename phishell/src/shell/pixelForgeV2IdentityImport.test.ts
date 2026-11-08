import { describe, expect, it } from "vitest";
import { PHIOFFICE_MANIFEST_SOURCE, PROJECT_REGISTRY_KEY, encodeProjectRegistry } from "./projectRegistry";
import {
  PROJECT_REGISTRY_V2_KEY,
  PIXELFORGE_V2_IDENTITY_SOURCE,
  decodeProjectRegistryV2,
  encodeProjectRegistryV2,
  providerQualifiedProjectKey,
  validateQualifiedProjectEntry,
} from "./projectRegistryV2";
import {
  previewPixelForgeV2Import,
  confirmPixelForgeV2Import,
  previewPixelForgeV2Removal,
  confirmPixelForgeV2Removal,
  inspectPixelForgeV2Identities,
} from "./pixelForgeV2IdentityImport";
import type { ProjectRegistryStorage } from "./projectRegistryV2Copy";
import { findProjectAdapterForTarget, findReviewedProjectAdapter } from "./projectAdapters";

const office = {
  providerAppId: "phioffice", projectRef: "project:same-project",
  title: "PhiOffice Title", source: PHIOFFICE_MANIFEST_SOURCE,
} as const;
const pixelManifest = (id = "same-project", title = "PixelForge World") =>
  JSON.stringify({
    schema: PIXELFORGE_V2_IDENTITY_SOURCE,
    projectId: id, title, worldFormat: "pixelforge.vr-world.v1",
  });

function fixture() {
  const rawV1 = encodeProjectRegistry([{
    projectRef: office.projectRef, title: office.title, source: office.source,
  }]);
  const rawV2 = encodeProjectRegistryV2([office]);
  const data = new Map([[PROJECT_REGISTRY_KEY, rawV1], [PROJECT_REGISTRY_V2_KEY, rawV2]]);
  const calls: Array<[string, string, string?]> = [];
  const storage: ProjectRegistryStorage = {
    getItem(key) { return data.get(key) ?? null; },
    setItem(key, raw) { calls.push(["set", key, raw]); data.set(key, raw); },
    removeItem(key) { calls.push(["remove", key]); data.delete(key); },
  };
  return { rawV1, rawV2, data, calls, storage };
}

describe("R11 PixelForge identity-only addition to reviewed PhiOS V2 metadata", () => {
  it("separates identical text IDs with no authority or V1 mutation", () => {
    const x = fixture();
    const plan = previewPixelForgeV2Import(x.storage, pixelManifest());
    expect(plan.collisionWithPhiOfficeRef).toBe(true);
    expect(plan.identity).toEqual({
      providerAppId: "pixelforge", projectRef: "project:same-project",
      title: "PixelForge World", source: PIXELFORGE_V2_IDENTITY_SOURCE,
    });
    expect(plan.resultCount).toBe(2);
    expect(x.calls).toEqual([]);
    expect(() => confirmPixelForgeV2Import(x.storage, plan, false)).toThrow("approval");
    expect(x.calls).toEqual([]);
    expect(confirmPixelForgeV2Import(x.storage, plan, true)).toBe(2);
    const saved = decodeProjectRegistryV2(x.data.get(PROJECT_REGISTRY_V2_KEY)!);
    expect(saved).toHaveLength(2);
    expect(saved.map((e) => providerQualifiedProjectKey(e.providerAppId, e.projectRef)))
      .toEqual([
        '["phioffice","project:same-project"]',
        '["pixelforge","project:same-project"]',
      ]);
    expect(x.data.get(PROJECT_REGISTRY_KEY)).toBe(x.rawV1);
    expect(x.calls.map((c) => c.slice(0, 2))).toEqual([["set", PROJECT_REGISTRY_V2_KEY]]);
    for (const forbidden of ["token", "grant", "execution_authority", "read_approved",
      "object", "asset", "filePath", "localWorld", "nativeApp"]) {
      expect(x.data.get(PROJECT_REGISTRY_V2_KEY)).not.toContain('"' + forbidden + '"');
    }
    expect(findReviewedProjectAdapter(PIXELFORGE_V2_IDENTITY_SOURCE)).toBeNull();
    expect(findProjectAdapterForTarget(PIXELFORGE_V2_IDENTITY_SOURCE, "pixelforge")).toBeNull();
  });

  it("rejects occupied pair even when display titles change", () => {
    const x = fixture();
    const plan = previewPixelForgeV2Import(x.storage, pixelManifest());
    confirmPixelForgeV2Import(x.storage, plan, true);
    expect(() => previewPixelForgeV2Import(x.storage, pixelManifest())).toThrow("already");
    expect(() => previewPixelForgeV2Import(x.storage, pixelManifest("same-project", "New title")))
      .toThrow("already");
    expect(x.calls).toHaveLength(1);
  });

  it("adds multiple distinct PixelForge refs, retaining PhiOffice and first PixelForge", () => {
    const x = fixture();
    const one = previewPixelForgeV2Import(x.storage, pixelManifest());
    confirmPixelForgeV2Import(x.storage, one, true);
    const two = previewPixelForgeV2Import(x.storage, pixelManifest("another-world", "Second World"));
    expect(two.collisionWithPhiOfficeRef).toBe(false);
    expect(confirmPixelForgeV2Import(x.storage, two, true)).toBe(3);
    expect(inspectPixelForgeV2Identities(x.storage).map((e) => e.projectRef))
      .toEqual(["project:same-project", "project:another-world"]);
    expect(decodeProjectRegistryV2(x.data.get(PROJECT_REGISTRY_V2_KEY)!)![0]).toEqual(office);
    expect(x.data.get(PROJECT_REGISTRY_KEY)).toEqual(x.rawV1);
  });

  it("removal also requires preview, explicit confirmation and exact original state", () => {
    const x = fixture();
    confirmPixelForgeV2Import(x.storage, previewPixelForgeV2Import(x.storage, pixelManifest()), true);
    const originalV2 = x.data.get(PROJECT_REGISTRY_V2_KEY);
    const review = previewPixelForgeV2Removal(x.storage, "project:same-project");
    expect(review.identity.providerAppId).toBe("pixelforge");
    expect(review.resultCount).toBe(1);
    expect(() => confirmPixelForgeV2Removal(x.storage, review, false)).toThrow("approval");
    expect(x.data.get(PROJECT_REGISTRY_V2_KEY)).toBe(originalV2);
    expect(confirmPixelForgeV2Removal(x.storage, review, true)).toBe(1);
    expect(x.data.get(PROJECT_REGISTRY_V2_KEY)).toBe(x.rawV2);
    expect(x.data.get(PROJECT_REGISTRY_KEY)).toBe(x.rawV1);
    expect(inspectPixelForgeV2Identities(x.storage)).toEqual([]);
  });

  it("removes only selected PixelForge identity, never another provider or ID", () => {
    const x = fixture();
    for (const id of ["same-project", "second-project"]) {
      confirmPixelForgeV2Import(x.storage, previewPixelForgeV2Import(x.storage, pixelManifest(id)), true);
    }
    const review = previewPixelForgeV2Removal(x.storage, "project:same-project");
    confirmPixelForgeV2Removal(x.storage, review, true);
    expect(decodeProjectRegistryV2(x.data.get(PROJECT_REGISTRY_V2_KEY)!).map((e) => e.projectRef))
      .toEqual(["project:same-project", "project:second-project"]);
    expect(inspectPixelForgeV2Identities(x.storage).map((e) => e.projectRef))
      .toEqual(["project:second-project"]);
  });

  it("blocks an edit when either registry changed since the preview", () => {
    const x = fixture();
    const plan = previewPixelForgeV2Import(x.storage, pixelManifest());
    x.data.set(PROJECT_REGISTRY_V2_KEY, encodeProjectRegistryV2([...decodeProjectRegistryV2(x.rawV2),
      validateQualifiedProjectEntry({providerAppId:"pixelforge", projectRef:"project:second",
        title:"Other World",source:PIXELFORGE_V2_IDENTITY_SOURCE})]));
    expect(() => confirmPixelForgeV2Import(x.storage, plan, true)).toThrow("changed since review");
    x.data.set(PROJECT_REGISTRY_V2_KEY, x.rawV2);
    x.data.set(PROJECT_REGISTRY_KEY, encodeProjectRegistry([
      {projectRef: "project:changed", title: "Changed", source: PHIOFFICE_MANIFEST_SOURCE}]));
    expect(() => confirmPixelForgeV2Import(x.storage, plan, true)).toThrow("changed since review");
    expect(x.calls).toEqual([]);
  });

  it("blocks removal after a V1 or V2 change and keeps existing records", () => {
    const x = fixture();
    confirmPixelForgeV2Import(x.storage, previewPixelForgeV2Import(x.storage, pixelManifest()), true);
    const plan = previewPixelForgeV2Removal(x.storage, "project:same-project");
    const before = x.data.get(PROJECT_REGISTRY_V2_KEY);
    x.data.set(PROJECT_REGISTRY_KEY, encodeProjectRegistry([
      {projectRef: "project:changed", title: "Changed", source: PHIOFFICE_MANIFEST_SOURCE}]));
    expect(() => confirmPixelForgeV2Removal(x.storage, plan, true)).toThrow();
    expect(x.data.get(PROJECT_REGISTRY_V2_KEY)).toBe(before);
    x.data.set(PROJECT_REGISTRY_KEY, x.rawV1);
    x.data.set(PROJECT_REGISTRY_V2_KEY, x.rawV2);
    expect(() => confirmPixelForgeV2Removal(x.storage, plan, true)).toThrow("changed since review");
    expect(x.calls).toHaveLength(1);
  });

  it("cannot import unreviewed schema, unsafe ID, fields, authority or excessive data", () => {
    const x = fixture();
    for (const payload of [
      { schema: "pixelforge.phios-vr-world-identity.v0.2", projectId: "a",
        title: "World", worldFormat: "pixelforge.vr-world.v1" },
      { schema: PIXELFORGE_V2_IDENTITY_SOURCE, projectId: "project:../secret",
        title: "World", worldFormat: "pixelforge.vr-world.v1" },
      { schema: PIXELFORGE_V2_IDENTITY_SOURCE, projectId: "good",
        title: "World", worldFormat: "pixelforge.vr-world.v1", grant: true },
      { schema: PIXELFORGE_V2_IDENTITY_SOURCE, projectId: "good",
        title: "World", worldFormat: "pixelforge.vr-world.v1", file: "/private/file.glb" },
      { schema: PIXELFORGE_V2_IDENTITY_SOURCE, projectId: "good",
        title: "Bi\u202eDi", worldFormat: "pixelforge.vr-world.v1" },
    ]) {
      expect(() => previewPixelForgeV2Import(x.storage, JSON.stringify(payload))).toThrow();
    }
    expect(() => previewPixelForgeV2Import(x.storage, " ".repeat(4097))).toThrow("4 KiB");
    expect(x.calls).toEqual([]);
  });

  it("cannot import without preexisting reviewed PhiOffice V1 and V2", () => {
    const x = fixture();
    x.data.delete(PROJECT_REGISTRY_V2_KEY);
    expect(() => previewPixelForgeV2Import(x.storage, pixelManifest())).toThrow("first");
    x.data.set(PROJECT_REGISTRY_V2_KEY, x.rawV2);
    x.data.delete(PROJECT_REGISTRY_KEY);
    expect(() => previewPixelForgeV2Import(x.storage, pixelManifest())).toThrow("first");
    expect(x.calls).toEqual([]);
  });

  it("blocks damage, mismatched provider, duplicate keys and storage failures", () => {
    const x = fixture();
    const plan = previewPixelForgeV2Import(x.storage, pixelManifest());
    expect(() => confirmPixelForgeV2Import(x.storage,
      {...plan, plannedV2Raw: "{}"}, true)).toThrow("failed validation");
    const blocked: ProjectRegistryStorage = {
      ...x.storage,
      setItem() { throw new DOMException("Quota exceeded", "QuotaExceededError"); },
    };
    expect(() => confirmPixelForgeV2Import(blocked, plan, true)).toThrow("Quota");
    expect(x.calls).toEqual([]);
    x.data.set(PROJECT_REGISTRY_V2_KEY, "{");
    expect(() => previewPixelForgeV2Import(x.storage, pixelManifest())).toThrow("not JSON");
    x.data.set(PROJECT_REGISTRY_V2_KEY, x.rawV2);
    expect(() => previewPixelForgeV2Removal(x.storage, "project:nonexistent")).toThrow("No reviewed");
    expect(() => previewPixelForgeV2Removal(x.storage, office.projectRef)).toThrow("No reviewed");
    const invalid = {...plan.identity, providerAppId: "phioffice"};
    expect(() => validateQualifiedProjectEntry(invalid)).toThrow("Invalid PixelForge");
  });
});
