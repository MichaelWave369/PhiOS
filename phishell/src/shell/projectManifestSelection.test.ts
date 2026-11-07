import { describe, expect, it } from "vitest";
import {
  extractProjectReference,
  MAX_PROJECT_MANIFEST_BYTES,
  PROJECT_MANIFEST_SCHEMA,
} from "./projectManifestSelection";

function manifest(projectId = "phi369-2026") {
  return {
    schema: PROJECT_MANIFEST_SCHEMA,
    projectId,
    title: "Shared R&D Workspace",
    description: "Contains private plans",
    owner: "private account",
    tags: ["confidential", "internal"],
    artifacts: [{
      title: "PRIVATE DOCUMENT",
      path: "/home/example/private.docx",
      receipts: ["private-token"],
    }],
    createdAt: "2026-11-06T15:00:00.000Z",
    updatedAt: "2026-11-06T15:00:00.000Z",
  };
}

describe("Local PhiOffice project manifest selection", () => {
  it("extracts only an opaque, wire-typed ID and an on-host display title", () => {
    const selected = extractProjectReference(JSON.stringify(manifest()));
    expect(selected).toEqual({
      projectRef: "project:phi369-2026", title: "Shared R&D Workspace",
    });
    const serialized = JSON.stringify(selected);
    expect(serialized).not.toContain("PRIVATE DOCUMENT");
    expect(serialized).not.toContain("private-token");
    expect(serialized).not.toContain("private account");
    expect(serialized).not.toContain("home/example");
    expect(serialized).not.toContain("confidential");
  });

  it("preserves already typed project identifiers", () => {
    expect(extractProjectReference(JSON.stringify(manifest("project:case-123"))).projectRef)
      .toBe("project:case-123");
  });

  it("rejects malformed, unrelated and oversized files before selection", () => {
    expect(() => extractProjectReference("{oops")).toThrow("JSON");
    expect(() => extractProjectReference("{}")).toThrow("manifest header");
    expect(() => extractProjectReference(JSON.stringify({
      ...manifest(), schema: "phioffice369.workspace_backup.v0.1",
    }))).toThrow("manifest header");
    expect(() => extractProjectReference(" ".repeat(MAX_PROJECT_MANIFEST_BYTES + 1)))
      .toThrow("256 KiB");
  });

  it("rejects identities that could be paths or unsafe project references", () => {
    for (const id of ["", "hello/world", "../secret", "project:../secret",
      "project:", "hello world", "a".repeat(129)]) {
      expect(() => extractProjectReference(JSON.stringify(manifest(id)))).toThrow();
    }
  });

  it("does not silently accept malformed headers or long display labels", () => {
    for (const change of [
      { title: " " },
      { title: "a".repeat(121) },
      { artifacts: {} },
      { tags: ["public", 7] },
      { owner: "" },
      { projectId: null },
      { createdAt: "" },
    ]) {
      expect(() => extractProjectReference(JSON.stringify({ ...manifest(), ...change })))
        .toThrow();
    }
  });
});
