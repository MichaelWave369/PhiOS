import { describe, expect, it } from "vitest";
import {
  PROJECT_REGISTRY_KEY,
  PHIOFFICE_MANIFEST_SOURCE,
  encodeProjectRegistry,
  type SavedProjectReference,
} from "./projectRegistry";
import {
  PROJECT_REGISTRY_V2_KEY,
  decodeProjectRegistryV2,
  encodeProjectRegistryV2,
} from "./projectRegistryV2";
import {
  commitProviderV2Copy,
  inspectProviderV2Rollback,
  prepareProviderV2Copy,
  rollbackProviderV2Copy,
  type ProjectRegistryStorage,
} from "./projectRegistryV2Copy";

const alpha = {
  projectRef: "project:office-alpha",
  title: "Alpha", source: PHIOFFICE_MANIFEST_SOURCE,
} as const;
const beta = {
  projectRef: "project:office-beta",
  title: "Beta", source: PHIOFFICE_MANIFEST_SOURCE,
} as const;

function fixture(entries: readonly SavedProjectReference[] = [alpha]) {
  const data = new Map<string, string>([[PROJECT_REGISTRY_KEY, encodeProjectRegistry(entries)]]);
  const counts = { set: 0, remove: 0 };
  const storage: ProjectRegistryStorage = {
    getItem(key: string) { return data.get(key) ?? null; },
    setItem(key: string, value: string) { counts.set += 1; data.set(key, value); },
    removeItem(key: string) { counts.remove += 1; data.delete(key); },
  };
  return { data, counts, storage };
}

describe("R9 explicit browser-local provider-qualified registry copy", () => {
  it("copies only after confirmation, keeping V1 byte-for-byte and grants absent", () => {
    const { data, counts, storage } = fixture();
    const originalV1 = data.get(PROJECT_REGISTRY_KEY);
    const preview = prepareProviderV2Copy(storage);
    expect(preview.preview.recordCount).toBe(1);
    expect(preview.preview.approvalCarriedOver).toBe(false);
    expect(Object.isFrozen(preview)).toBe(true);
    expect(counts.set).toBe(0);
    expect(counts.remove).toBe(0);
    expect(() => commitProviderV2Copy(storage, preview, false)).toThrow("confirmation");
    expect(counts.set).toBe(0);
    expect(commitProviderV2Copy(storage, preview, true)).toBe(1);
    expect(data.get(PROJECT_REGISTRY_KEY)).toBe(originalV1);
    expect(counts.set).toBe(1);
    expect(counts.remove).toBe(0);
    const v2 = data.get(PROJECT_REGISTRY_V2_KEY)!;
    expect(decodeProjectRegistryV2(v2)).toEqual([
      { providerAppId: "phioffice", ...alpha },
    ]);
    for (const forbidden of ["read_approved", "execution_authority", "token", "manifest", "grant"]) {
      expect(v2).not.toContain('"' + forbidden + '"');
    }
  });

  it("explicit rollback removes V2 only and preserves V1 exactly", () => {
    const { data, counts, storage } = fixture([alpha, beta]);
    const before = data.get(PROJECT_REGISTRY_KEY);
    const plan = prepareProviderV2Copy(storage);
    commitProviderV2Copy(storage, plan, true);
    const review = inspectProviderV2Rollback(storage);
    expect(review.recordCount).toBe(2);
    expect(Object.isFrozen(review)).toBe(true);
    expect(Object.isFrozen(review.entries)).toBe(true);
    expect(() => rollbackProviderV2Copy(storage, review, false)).toThrow("confirmation");
    expect(data.has(PROJECT_REGISTRY_V2_KEY)).toBe(true);
    rollbackProviderV2Copy(storage, review, true);
    expect(data.has(PROJECT_REGISTRY_V2_KEY)).toBe(false);
    expect(data.get(PROJECT_REGISTRY_KEY)).toBe(before);
    expect(counts.set).toBe(1);
    expect(counts.remove).toBe(1);
  });

  it("stale V1 preview must be recreated; no partial V2 write", () => {
    const { data, counts, storage } = fixture();
    const plan = prepareProviderV2Copy(storage);
    data.set(PROJECT_REGISTRY_KEY, encodeProjectRegistry([alpha, beta]));
    expect(() => commitProviderV2Copy(storage, plan, true)).toThrow("changed since preview");
    expect(counts.set).toBe(0);
    expect(data.has(PROJECT_REGISTRY_V2_KEY)).toBe(false);
    const fresh = prepareProviderV2Copy(storage);
    expect(commitProviderV2Copy(storage, fresh, true)).toBe(2);
  });

  it("existing valid or malformed V2 is never overwritten, even if preview is stale", () => {
    const { data, counts, storage } = fixture();
    const plan = prepareProviderV2Copy(storage);
    data.set(PROJECT_REGISTRY_V2_KEY, encodeProjectRegistryV2([{ providerAppId: "phioffice", ...alpha }]));
    expect(() => commitProviderV2Copy(storage, plan, true)).toThrow("already exists");
    expect(() => prepareProviderV2Copy(storage)).toThrow("refusing overwrite");
    data.set(PROJECT_REGISTRY_V2_KEY, "{");
    expect(() => prepareProviderV2Copy(storage)).toThrow("not JSON");
    expect(() => commitProviderV2Copy(storage, plan, true)).toThrow("already exists");
    expect(counts.set).toBe(0);
  });

  it("cannot copy missing, empty, malformed, or forged V1 records", () => {
    const { data, counts, storage } = fixture();
    data.delete(PROJECT_REGISTRY_KEY);
    expect(() => prepareProviderV2Copy(storage)).toThrow("No V1");
    data.set(PROJECT_REGISTRY_KEY, encodeProjectRegistry([]));
    expect(() => prepareProviderV2Copy(storage)).toThrow("No saved");
    data.set(PROJECT_REGISTRY_KEY, "{");
    expect(() => prepareProviderV2Copy(storage)).toThrow("not JSON");
    data.set(PROJECT_REGISTRY_KEY, JSON.stringify({
      format: "phios.project-registry", version: 1,
      entries: [{ ...alpha, source: "phimail.manifest.unreviewed" }],
    }));
    expect(() => prepareProviderV2Copy(storage)).toThrow("Unreviewed");
    expect(counts.set).toBe(0);
  });

  it("refuses tampered plan and a storage quota error without changing V1", () => {
    const { data, storage } = fixture();
    const plan = prepareProviderV2Copy(storage);
    const before = data.get(PROJECT_REGISTRY_KEY);
    expect(() => commitProviderV2Copy(storage, { ...plan, plannedV2Raw: "{}" }, true))
      .toThrow("failed source validation");
    const full: ProjectRegistryStorage = {
      ...storage,
      setItem() { throw new DOMException("Full", "QuotaExceededError"); },
    };
    expect(() => commitProviderV2Copy(full, plan, true)).toThrow("Full");
    expect(data.get(PROJECT_REGISTRY_KEY)).toBe(before);
    expect(data.has(PROJECT_REGISTRY_V2_KEY)).toBe(false);
  });

  it("read-back disagreement is reported, never silently trusted", () => {
    const { storage, counts } = fixture();
    const plan = prepareProviderV2Copy(storage);
    const bad: ProjectRegistryStorage = {
      getItem: () => null,
      setItem: () => { counts.set += 1; },
      removeItem: () => {},
    };
    expect(() => commitProviderV2Copy(bad, plan, true)).toThrow("changed since preview");
    let calls = 0;
    const inconsistent: ProjectRegistryStorage = {
      getItem: (key) => {
        if (key === PROJECT_REGISTRY_KEY) return plan.expectedV1Raw;
        calls += 1;
        return calls === 1 ? null : "different";
      },
      setItem: () => { counts.set += 1; },
      removeItem: () => {},
    };
    expect(() => commitProviderV2Copy(inconsistent, plan, true)).toThrow("read-back mismatch");
  });

  it("refuses rollback after V2 was edited, deleted, malformed, or V1 changed", () => {
    const { data, counts, storage } = fixture();
    commitProviderV2Copy(storage, prepareProviderV2Copy(storage), true);
    const review = inspectProviderV2Rollback(storage);
    const originalV2 = data.get(PROJECT_REGISTRY_V2_KEY)!;
    data.set(PROJECT_REGISTRY_V2_KEY, encodeProjectRegistryV2([{ providerAppId: "phioffice", ...beta }]));
    expect(() => rollbackProviderV2Copy(storage, review, true)).toThrow("changed since review");
    expect(() => inspectProviderV2Rollback(storage)).toThrow("differ");
    data.set(PROJECT_REGISTRY_V2_KEY, originalV2);
    data.set(PROJECT_REGISTRY_KEY, encodeProjectRegistry([alpha, beta]));
    expect(() => rollbackProviderV2Copy(storage, review, true)).toThrow("differ");
    data.delete(PROJECT_REGISTRY_KEY);
    expect(() => inspectProviderV2Rollback(storage)).toThrow("missing");
    data.set(PROJECT_REGISTRY_KEY, encodeProjectRegistry([alpha]));
    data.set(PROJECT_REGISTRY_V2_KEY, "{");
    expect(() => inspectProviderV2Rollback(storage)).toThrow("not JSON");
    data.delete(PROJECT_REGISTRY_V2_KEY);
    expect(() => inspectProviderV2Rollback(storage)).toThrow("No V2");
    expect(counts.remove).toBe(0);
  });

  it("no unknown or unrelated data removed by a stale/tampered rollback review", () => {
    const { data, counts, storage } = fixture();
    commitProviderV2Copy(storage, prepareProviderV2Copy(storage), true);
    const review = inspectProviderV2Rollback(storage);
    expect(() => rollbackProviderV2Copy(storage, {
      ...review, entries: [{ ...review.entries[0], title: "tampered" }],
    }, true)).toThrow("no longer matches");
    expect(data.has(PROJECT_REGISTRY_V2_KEY)).toBe(true);
    expect(counts.remove).toBe(0);
  });
});
