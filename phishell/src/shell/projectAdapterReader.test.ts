import { describe, expect, it } from "vitest";
import {
  PHIOFFICE_MANIFEST_SOURCE,
  PHIOFFICE_PROJECT_ADAPTER_ID,
} from "./projectAdapters";
import { readProjectIdentityWithAdapter } from "./projectAdapterReader";

function manifest() {
  return {
    schema: PHIOFFICE_MANIFEST_SOURCE,
    projectId: "safe-project",
    title: "Test Project",
    description: "top secret notes",
    owner: "private owner",
    tags: ["private"], artifacts: [{ path: "/internal/private" }],
    createdAt: "2026-11-06T18:00:00Z",
    updatedAt: "2026-11-06T18:00:00Z",
  };
}

describe("reviewed project identity adapter reader", () => {
  it("projects only identity metadata from the reviewed versioned local manifest", () => {
    const result = readProjectIdentityWithAdapter(
      PHIOFFICE_PROJECT_ADAPTER_ID, JSON.stringify(manifest()),
    );
    expect(result).toEqual({
      projectRef: "project:safe-project",
      title: "Test Project",
      source: PHIOFFICE_MANIFEST_SOURCE,
    });
    const json = JSON.stringify(result);
    for (const leak of ["top secret notes", "private owner", "/internal/private",
      '"artifacts"', '"tags"', '"permission"', '"authorization"']) {
      expect(json).not.toContain(leak);
    }
  });

  it("refuses unreviewed adapter IDs even when the payload claims trusted status", () => {
    for (const id of ["phicloud-project-v1", "phiid-project-v1", "phioffice-manifest-v2",
      "", "PHIOFFICE-MANIFEST-BRIDGE-V1", "*"]) {
      expect(() => readProjectIdentityWithAdapter(id, JSON.stringify(manifest())))
        .toThrow("not reviewed");
    }
    const forged = JSON.stringify({
      ...manifest(),
      source: PHIOFFICE_MANIFEST_SOURCE,
      adapterId: PHIOFFICE_PROJECT_ADAPTER_ID,
      executionAuthority: true,
    });
    expect(() => readProjectIdentityWithAdapter("phicloud-project-v1", forged))
      .toThrow("not reviewed");
  });

  it("rejects mismatched manifests, unsafe ref IDs and malformed JSON", () => {
    expect(() => readProjectIdentityWithAdapter(PHIOFFICE_PROJECT_ADAPTER_ID, "{"))
      .toThrow("not valid JSON");
    expect(() => readProjectIdentityWithAdapter(PHIOFFICE_PROJECT_ADAPTER_ID,
      JSON.stringify({ ...manifest(), schema: "phicloud.project.v1" })))
      .toThrow("manifest header");
    expect(() => readProjectIdentityWithAdapter(PHIOFFICE_PROJECT_ADAPTER_ID,
      JSON.stringify({ ...manifest(), projectId: "../secret" })))
      .toThrow("cannot be represented safely");
  });
});
