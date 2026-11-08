import { describe, expect, it } from "vitest";
import {
  listPixelForgeBridgeChoices,
  verifyPixelForgeBridgeChoice,
  type PixelForgeBridgeChoice,
} from "./pixelForgeBridgeSelection";
import {
  PIXELFORGE_V2_IDENTITY_SOURCE,
  PROJECT_REGISTRY_V2_KEY,
  encodeProjectRegistryV2,
  type ProviderQualifiedProjectReference,
} from "./projectRegistryV2";
import { PHIOFFICE_MANIFEST_SOURCE } from "./projectAdapters";
import { createWorkspaceBridgeHost, WORKSPACE_BRIDGE_PROTOCOL } from "./workspaceBridge";
import { reviewPhiOfficePilotEndpoint } from "./workspaceBridgePilotConfig";

const office = {
  providerAppId: "phioffice", source: PHIOFFICE_MANIFEST_SOURCE,
  projectRef: "project:same-id", title: "Office Private Title",
};
const pixel = {
  providerAppId: "pixelforge", source: PIXELFORGE_V2_IDENTITY_SOURCE,
  projectRef: "project:same-id", title: "PixelForge Title",
} as const;
const v2 = encodeProjectRegistryV2([office, pixel]);
const frame = {}, otherFrame = {};
const session = "f10342be-61dd-4ff2-bc32-4d8340fd6789";
const origin = "http://127.0.0.1:4672";

describe("PhiOS R12 separate PixelForge browser app admission", () => {
  it("selects only independently reviewed PixelForge V2 entries, never V1 or PhiOffice", () => {
    expect(PROJECT_REGISTRY_V2_KEY).toBe("phios.project-registry.v2");
    expect(listPixelForgeBridgeChoices(v2)).toEqual([pixel]);
    expect(verifyPixelForgeBridgeChoice(v2, pixel)).toEqual(pixel);
    expect(() => verifyPixelForgeBridgeChoice(v2, office as unknown as PixelForgeBridgeChoice))
      .toThrow("incorrect PixelForge bridge provider");
    expect(listPixelForgeBridgeChoices(encodeProjectRegistryV2([office]))).toEqual([]);
    expect(() => listPixelForgeBridgeChoices(null)).toThrow("No reviewed V2");
    expect(() => listPixelForgeBridgeChoices("{")).toThrow("not JSON");
  });

  it("any deletion, rename or provider spoof between selection and approval refuses", () => {
    const renamed = encodeProjectRegistryV2([
      office, { ...pixel, title: "Changed Title" },
    ]);
    expect(() => verifyPixelForgeBridgeChoice(renamed, pixel)).toThrow("changed since selection");
    expect(() => verifyPixelForgeBridgeChoice(
      encodeProjectRegistryV2([office]), pixel)).toThrow("changed since selection");
    expect(() => verifyPixelForgeBridgeChoice(v2, {
      ...pixel, source: "pixelforge.unknown"
    } as unknown as PixelForgeBridgeChoice)).toThrow("incorrect PixelForge");
    expect(() => verifyPixelForgeBridgeChoice(v2, {
      ...pixel, projectRef: "project:../../bad"
    } as unknown as PixelForgeBridgeChoice)).toThrow();
  });

  it("approved iframe endpoint is pinned to exact non-self origin, not a homepage", () => {
    const url = origin + "/vr-studio/";
    const approved = reviewPhiOfficePilotEndpoint(url, origin, "http://127.0.0.1:4671");
    expect(approved).toEqual({ url, origin });
    for (const [raw, otherOrigin] of [
      [origin + "/vr-studio/?token=1", origin],
      [origin + "/vr-studio/#trust", origin],
      [origin + "/vr-studio/", "https://other.example"],
      ["https://evil.example/", "https://evil.example"],
    ]) {
      if (raw === "https://evil.example/") continue; // a different explicit allowed origin is permissible
      expect(reviewPhiOfficePilotEndpoint(raw, otherOrigin, "http://127.0.0.1:4671")).toBeNull();
    }
    expect(reviewPhiOfficePilotEndpoint(
      "http://127.0.0.1:4671/vr-studio/", "http://127.0.0.1:4671",
      "http://127.0.0.1:4671")).toBeNull();
    expect(reviewPhiOfficePilotEndpoint(url, undefined, "http://127.0.0.1:4671")).toBeNull();
  });

  it("host shares one opaque ref only after approval and never via an unrelated frame", () => {
    const host = createWorkspaceBridgeHost({
      appId: "pixelforge", appOrigin: origin, sessionId: session, frameSource: frame,
    });
    const req = {
      protocol: WORKSPACE_BRIDGE_PROTOCOL, type: "app.context.request",
      app_id: "pixelforge", session_id: session, request_id: "r1",
    };
    expect(host.handle({ origin, source: otherFrame, data: req })).toBeNull();
    expect(host.handle({ origin: "https://other.example", source: frame, data: req })).toBeNull();
    expect(host.handle({ origin, source: frame, data: { ...req, app_id: "phioffice" } })).toBeNull();
    expect(host.handle({ origin, source: frame, data: { ...req, secret: true } })).toBeNull();
    const denied = host.handle({ origin, source: frame, data: req });
    expect(denied?.message).toMatchObject({ type: "host.denied", execution_authority: false });
    const reviewed = verifyPixelForgeBridgeChoice(v2, pixel);
    host.approveProject(reviewed.projectRef);
    const answer = host.handle({ origin, source: frame,
      data: { ...req, request_id: "r2" } });
    expect(answer?.message).toMatchObject({
      type: "host.context", project_ref: "project:same-id", execution_authority: false,
    });
    expect(Object.keys(answer!.message)).toEqual([
      "protocol", "type", "app_id", "session_id", "request_id",
      "execution_authority", "project_ref",
    ]);
    for (const forbidden of ["title", "assets", "world", "owner", "credentials", "source"]) {
      expect(answer?.message).not.toHaveProperty(forbidden);
    }
    host.revokeProject();
    expect(host.handle({ origin, source: frame, data: { ...req, request_id: "r3" } })
      ?.message.type).toBe("host.denied");
  });

  it("distinct frame sessions prevent an earlier PixelForge or PhiOffice approval crossing", () => {
    const pixelHost = createWorkspaceBridgeHost({
      appId: "pixelforge", appOrigin: origin, sessionId: session, frameSource: frame,
    });
    const officeHost = createWorkspaceBridgeHost({
      appId: "phioffice", appOrigin: "http://127.0.0.1:4673",
      sessionId: "a20342be-61dd-4ff2-bc32-4d8340fd6789", frameSource: otherFrame,
    });
    officeHost.approveProject(office.projectRef);
    const request = { protocol: WORKSPACE_BRIDGE_PROTOCOL,
      type: "app.context.request", app_id: "pixelforge",
      session_id: session, request_id: "req1" };
    expect(pixelHost.handle({ origin, source: frame, data: request })?.message.type)
      .toBe("host.denied");
    expect(pixelHost.handle({ origin: "http://127.0.0.1:4673",
      source: otherFrame, data: request })).toBeNull();
    const newSession = createWorkspaceBridgeHost({
      appId: "pixelforge", appOrigin: origin, frameSource: frame,
      sessionId: "b20342be-61dd-4ff2-bc32-4d8340fd6789",
    });
    expect(newSession.handle({ origin, source: frame, data: {
      ...request, session_id: "b20342be-61dd-4ff2-bc32-4d8340fd6789",
    } })?.message.type).toBe("host.denied");
  });
});
