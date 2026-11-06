import { describe, expect, it } from "vitest";
import {
  WORKSPACE_BRIDGE_PROTOCOL,
  createWorkspaceBridgeHost,
  normalizeBridgeOrigin,
} from "./workspaceBridge";

const appOrigin = "https://michaelwave369.github.io";
const sessionId = "f10342be-61dd-4ff2-bc32-4d8340fd6789";
const frameSource = {};
function fixture() {
  return createWorkspaceBridgeHost({
    appId: "phioffice", appOrigin, frameSource, sessionId,
  });
}
function request(type: "app.hello" | "app.context.request" = "app.context.request") {
  return {
    protocol: WORKSPACE_BRIDGE_PROTOCOL, type,
    app_id: "phioffice", session_id: sessionId, request_id: "req-1",
  };
}
function incoming(data: unknown, origin = appOrigin, source: unknown = frameSource) {
  return { data, origin, source };
}

describe("PhiOS workspace bridge v1", () => {
  it("accepts only exact approved host configuration origins", () => {
    expect(normalizeBridgeOrigin("https://example.com")).toBe("https://example.com");
    expect(normalizeBridgeOrigin("http://localhost:5173")).toBe("http://localhost:5173");
    for (const origin of [
      "*", "http://evil.test", "https://example.com/a", "https://a.test@b.test",
      "https://example.com?x=1", "https://example.com/",
    ]) expect(() => normalizeBridgeOrigin(origin)).toThrow();
  });

  it("bootstrap binds one session to one exact frame and origin", () => {
    const host = fixture();
    const boot = host.bootstrap();
    expect(boot.targetOrigin).toBe(appOrigin);
    expect(boot.message).toMatchObject({
      type: "host.bootstrap", app_id: "phioffice", session_id: sessionId,
      execution_authority: false,
    });
    expect(host.handle(incoming(request(), "https://lookalike.github.io"))).toBeNull();
    expect(host.handle(incoming(request(), appOrigin, {}))).toBeNull();
    expect(host.handle(incoming({ ...request(), session_id: "wrong" }))).toBeNull();
    expect(host.handle(incoming({ ...request(), app_id: "another" }))).toBeNull();
  });

  it("denies context until explicit approval and supports immediate revocation", () => {
    const host = fixture();
    expect(host.handle(incoming(request()))?.message).toMatchObject({
      type: "host.denied", reason: "operator_approval_required",
      execution_authority: false,
    });
    host.approveProject("project:phi369-office");
    expect(host.handle(incoming(request()))?.message).toMatchObject({
      type: "host.context", project_ref: "project:phi369-office",
      execution_authority: false,
    });
    host.revokeProject();
    expect(host.handle(incoming(request()))?.message.type).toBe("host.denied");
  });

  it("never accepts command payloads, credentials or arbitrary project paths", () => {
    const host = fixture();
    for (const bad of [
      { ...request(), command: "rm -rf /" },
      { ...request(), execution_authority: true },
      { ...request(), capabilities: ["shell.execute"] },
      { ...request(), type: "app.execute" },
      { ...request(), request_id: "a".repeat(3000) },
    ]) expect(host.handle(incoming(bad))).toBeNull();
    for (const badProject of ["../secrets", "/home/user/docs", "file:///etc/passwd", "project:../secret"]) {
      expect(() => host.approveProject(badProject)).toThrow();
    }
  });

  it("hello announces permission state without leaking a project reference", () => {
    const host = fixture();
    host.approveProject("project:secret");
    const response = host.handle(incoming(request("app.hello")));
    expect(response?.message).toMatchObject({ type: "host.ready", read_approved: true });
    expect(JSON.stringify(response)).not.toContain("project:secret");
  });
});
