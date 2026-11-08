import { describe, expect, it } from "vitest";
import { inspectPixelForgeLaunchReadiness } from "./pixelForgeLaunchReadiness";
import { encodeProjectRegistryV2 } from "./projectRegistryV2";
import { PHIOFFICE_MANIFEST_SOURCE } from "./projectRegistry";
import { findShellApp, shellAppEvent } from "./appLauncher";

const shellOrigin = "http://127.0.0.1:4671";
const pixelOrigin = "http://127.0.0.1:4672";
const endpoint = {
  configuredUrl: pixelOrigin + "/",
  approvedOrigin: pixelOrigin,
  shellOrigin,
};
const office = {
  providerAppId: "phioffice", projectRef: "project:same-project",
  title: "Office title", source: PHIOFFICE_MANIFEST_SOURCE,
};
const pixel = {
  providerAppId: "pixelforge", projectRef: "project:same-project",
  title: "PixelForge title", source: "pixelforge.phios-vr-world-identity.v0.1",
};
const v2 = encodeProjectRegistryV2([office, pixel]);

describe("PhiOS R14 PixelForge governed launch discovery", () => {
  it("has an honest app tile that opens Build, not an external iframe or native package", () => {
    const app = findShellApp("pixelforge");
    expect(app).toBeDefined();
    expect(app?.windowId).toBe("build-window");
    expect(app?.status).toContain("Browser pilot");
    expect(app?.description).toContain("not installed");
    expect(shellAppEvent("pixelforge")).toMatchObject({
      type: "OPEN_WINDOW",
      window: { id: "build-window", state: "open", kind: "workspace" },
    });
    expect(shellAppEvent("pixelforge")).toEqual(shellAppEvent("builder"));
  });

  it("defaults to disabled without an exact reviewed endpoint", () => {
    for (const input of [
      { ...endpoint, configuredUrl: undefined },
      { ...endpoint, approvedOrigin: undefined },
      { ...endpoint, configuredUrl: "https://unreviewed.example.test/" },
      { ...endpoint, configuredUrl: shellOrigin + "/", approvedOrigin: shellOrigin },
      { ...endpoint, configuredUrl: pixelOrigin + "/?grant=true" },
    ]) {
      const receipt = inspectPixelForgeLaunchReadiness({ ...input, v2Raw: v2 });
      expect(receipt.status).toBe("endpoint-disabled");
      expect(receipt.browserPilotConfigured).toBe(false);
      expect(receipt.pixelForgeIdentityCount).toBe(0);
      expect(receipt.nativeInstalled).toBe(false);
      expect(receipt.permissionGranted).toBe(false);
      expect(receipt.automaticallyLaunched).toBe(false);
    }
  });

  it("will not call an empty, corrupted, or absent V2 record ready", () => {
    const missing = inspectPixelForgeLaunchReadiness({ ...endpoint, v2Raw: null });
    const malformed = inspectPixelForgeLaunchReadiness({ ...endpoint, v2Raw: "{" });
    const officeOnly = inspectPixelForgeLaunchReadiness({
      ...endpoint, v2Raw: encodeProjectRegistryV2([office]),
    });
    expect(missing.status).toBe("registry-invalid");
    expect(malformed.status).toBe("registry-invalid");
    expect(officeOnly.status).toBe("no-pixelforge-identity");
    expect(officeOnly.pixelForgeIdentityCount).toBe(0);
  });

  it("readiness counts only exact provider-qualified PixelForge records", () => {
    const receipt = inspectPixelForgeLaunchReadiness({ ...endpoint, v2Raw: v2 });
    expect(receipt).toEqual({
      status: "browser-pilot-ready", endpointOrigin: pixelOrigin,
      pixelForgeIdentityCount: 1, browserPilotConfigured: true,
      nativeInstalled: false, automaticallyLaunched: false,
      permissionGranted: false,
    });
    expect(Object.isFrozen(receipt)).toBe(true);
    expect(receipt).not.toHaveProperty("executionAuthority");
    expect(receipt).not.toHaveProperty("installed");
    expect(receipt).not.toHaveProperty("grant");
  });
});
