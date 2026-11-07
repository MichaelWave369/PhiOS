import { describe, expect, it } from "vitest";
import {
  PROJECT_REGISTRY_KEY,
  PROJECT_REGISTRY_FORMAT,
  PROJECT_REGISTRY_VERSION,
  PROJECT_REGISTRY_MAX_RECORDS,
  PHIOFFICE_MANIFEST_SOURCE,
  decodeProjectRegistry,
  encodeProjectRegistry,
  loadProjectRegistry,
  storeProjectRegistry,
  rememberProject,
  forgetProject,
  validateRegistryEntry,
} from "./projectRegistry";

const first = { projectRef: "project:phios-case", title: "PhiOS Case", source: PHIOFFICE_MANIFEST_SOURCE };
const second = { projectRef: "project:office-2026", title: "Office Planning", source: PHIOFFICE_MANIFEST_SOURCE };
const wire = (entries: unknown) => JSON.stringify({
  format: PROJECT_REGISTRY_FORMAT,
  version: PROJECT_REGISTRY_VERSION,
  entries,
});

describe("PhiOS browser-local project registry v1", () => {
  it("round-trips only explicitly saved metadata, excluding all authority and artifact fields", () => {
    const json = encodeProjectRegistry([first, second]);
    expect(decodeProjectRegistry(json)).toEqual([first, second]);
    expect(json).not.toContain("read_approved");
    expect(json).not.toContain("execution_authority");
    expect(json).not.toContain("manifest_data");
    expect(json).not.toContain("storage_key");
  });

  it("upserts by exact project reference and preserves a bounded ordered list", () => {
    const stored = rememberProject([], { projectRef: first.projectRef, title: first.title });
    const next = rememberProject(stored, { projectRef: second.projectRef, title: second.title });
    expect(next.map(({ projectRef }) => projectRef)).toEqual([second.projectRef, first.projectRef]);
    const renamed = rememberProject(next, { projectRef: first.projectRef, title: "Updated Title" });
    expect(renamed).toHaveLength(2);
    expect(renamed[0].title).toBe("Updated Title");
    expect(forgetProject(renamed, first.projectRef)).toEqual([second]);
    expect(next[1].title).toBe("PhiOS Case");
  });

  it("rejects unreviewed metadata, data payloads, app grants or tokens", () => {
    for (const extras of [
      { grant: true }, { authority: ["shell.execute"] },
      { artifacts: [{ path: "/private" }] }, { accessToken: "secret" },
      { storage: { files: [] } },
    ]) {
      expect(() => validateRegistryEntry({ ...first, ...extras })).toThrow("unsupported fields");
    }
    expect(() => validateRegistryEntry({ ...first, source: "phicloud.unverified.v0" }))
      .toThrow("Unreviewed");
    expect(() => decodeProjectRegistry(JSON.stringify({
      format: PROJECT_REGISTRY_FORMAT, version: PROJECT_REGISTRY_VERSION,
      entries: [first], grants: ["read"],
    }))).toThrow("shape");
  });

  it("rejects unsafe references, invisible titles and invalid shapes", () => {
    for (const projectRef of ["../secrets", "project:../secrets", "project:x/abc",
      "project:a..b", "project:", "project:abc.", "project:hello world"]) {
      expect(() => validateRegistryEntry({ ...first, projectRef })).toThrow();
    }
    for (const title of ["", " a", "a\nprivate", "\u007f", "t".repeat(121)]) {
      expect(() => validateRegistryEntry({ ...first, title })).toThrow();
    }
    expect(() => decodeProjectRegistry("{}")).toThrow();
    expect(() => decodeProjectRegistry("{")).toThrow("not JSON");
    expect(() => decodeProjectRegistry(wire([first, first]))).toThrow("duplicate");
    expect(() => decodeProjectRegistry(wire(new Array(PROJECT_REGISTRY_MAX_RECORDS + 1).fill(first))))
      .toThrow("24 projects");
    expect(() => decodeProjectRegistry(" ".repeat(16 * 1024 + 1))).toThrow("16 KiB");
    expect(() => decodeProjectRegistry(JSON.stringify({
      format: PROJECT_REGISTRY_FORMAT, version: 2, entries: [],
    }))).toThrow("version");
  });

  it("stores and loads only with explicit call; no grants survive a reload", () => {
    const saved = new Map<string, string>();
    const storage = {
      getItem(key: string): string | null { return saved.get(key) ?? null; },
      setItem(key: string, val: string): void { saved.set(key, val); },
    };
    expect(loadProjectRegistry(storage)).toEqual([]);
    expect(saved.size).toBe(0);
    const entries = rememberProject([], first);
    storeProjectRegistry(entries, storage);
    expect(saved.size).toBe(1);
    expect(saved.has(PROJECT_REGISTRY_KEY)).toBe(true);
    expect(loadProjectRegistry(storage)).toEqual([first]);
    expect(JSON.parse(saved.get(PROJECT_REGISTRY_KEY)!).entries[0]).toEqual(first);
    expect(Object.keys(JSON.parse(saved.get(PROJECT_REGISTRY_KEY)!)))
      .toEqual(["format", "version", "entries"]);
  });

  it("does not erase invalid existing registries silently on read failure", () => {
    const storage = { getItem: () => '{"untrusted":true}' };
    expect(() => loadProjectRegistry(storage)).toThrow();
    const failing = { setItem: () => { throw new Error("quota full"); } };
    expect(() => storeProjectRegistry([first], failing)).toThrow("quota full");
  });
});
