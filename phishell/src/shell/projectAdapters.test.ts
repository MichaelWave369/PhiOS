import { describe, expect, it } from "vitest";
import {
  PROJECT_ADAPTER_CATALOG_VERSION,
  PHIOFFICE_MANIFEST_SOURCE,
  REVIEWED_PROJECT_ADAPTERS,
  findReviewedProjectAdapter,
  findProjectAdapterForTarget,
  isReviewedProjectSource,
  listReviewedProjectAdapters,
} from "./projectAdapters";
import { WORKSPACE_BRIDGE_PROTOCOL } from "./workspaceBridge";

describe("reviewed PhiOS project adapter catalog R1", () => {
  it("lists only a real, explicitly reviewed PhiOffice browser pilot", () => {
    expect(PROJECT_ADAPTER_CATALOG_VERSION).toBe(1);
    expect(listReviewedProjectAdapters()).toHaveLength(1);
    expect(REVIEWED_PROJECT_ADAPTERS[0]).toMatchObject({
      source: PHIOFFICE_MANIFEST_SOURCE,
      providerAppId: "phioffice",
      targetAppId: "phioffice",
      selection: "operator-selected-local-manifest",
      transfer: "opaque-project-ref-only",
      protocol: WORKSPACE_BRIDGE_PROTOCOL,
      executionAuthority: false,
      status: "reviewed-browser-pilot",
    });
    expect(JSON.stringify(REVIEWED_PROJECT_ADAPTERS)).not.toMatch(/access_token|read_approved|artifact_data/i);
    expect(Object.isFrozen(REVIEWED_PROJECT_ADAPTERS)).toBe(true);
    expect(Object.isFrozen(REVIEWED_PROJECT_ADAPTERS[0])).toBe(true);
  });

  it("does not falsely admit PhiID, PhiCloud, unreviewed apps or spoofed formats", () => {
    for (const source of [
      "phiid.project.v1", "phicloud.project_manifest.v1", "phioffice369.project_manifest.v0.2",
      "PHIOFFICE369.PROJECT_MANIFEST.V0.1", "", "*", null, {}, 1,
    ]) {
      expect(findReviewedProjectAdapter(source)).toBeNull();
      expect(isReviewedProjectSource(source)).toBe(false);
      expect(findProjectAdapterForTarget(source, "phioffice")).toBeNull();
    }
    expect(findProjectAdapterForTarget(PHIOFFICE_MANIFEST_SOURCE, "phiid")).toBeNull();
    expect(findProjectAdapterForTarget(PHIOFFICE_MANIFEST_SOURCE, "phicloud")).toBeNull();
    expect(findProjectAdapterForTarget(PHIOFFICE_MANIFEST_SOURCE, "*")).toBeNull();
    expect(findProjectAdapterForTarget(PHIOFFICE_MANIFEST_SOURCE, {})).toBeNull();
    expect(findProjectAdapterForTarget(PHIOFFICE_MANIFEST_SOURCE, "phioffice")?.id)
      .toBe("phioffice-manifest-bridge-v1");
  });

  it("does not let a JSON object claiming review become a registered adapter", () => {
    const injected = {
      id: "phicloud-fake", source: "phicloud.project_manifest.v1",
      targetAppId: "phioffice", status: "reviewed-browser-pilot",
      executionAuthority: false,
    };
    expect(findReviewedProjectAdapter(injected)).toBeNull();
    expect(findReviewedProjectAdapter(injected.source)).toBeNull();
    expect(listReviewedProjectAdapters()).toEqual(REVIEWED_PROJECT_ADAPTERS);
  });
});
