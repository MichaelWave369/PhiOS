import { describe, expect, it } from "vitest";
import { INITIAL_SHELL_STATE } from "./model";
import { decodeWorkspace, encodeWorkspace } from "./workspaceSession";

describe("PhiOS portable workspace layout v1", () => {
  it("round-trips windows and view while dropping authority and transient UI", () => {
    const input = {
      ...INITIAL_SHELL_STATE,
      view: "build" as const,
      commandOpen: true,
      commandQuery: "sensitive query",
      authorityRequest: {
        id: "authority:test", capability: "network.configure", scope: "host",
        reason: "test", requestedBy: "operator" as const,
        decision: "approved_intent" as const, executionAuthority: false as const,
      },
    };
    const wire = encodeWorkspace(input);
    const restored = decodeWorkspace(wire);
    expect(restored.view).toBe("build");
    expect(restored.windows).toEqual(input.windows);
    expect(restored.authorityRequest).toBeNull();
    expect(restored.commandOpen).toBe(false);
    expect(wire).not.toContain("sensitive query");
    expect(wire).not.toContain("network.configure");
    expect(wire).not.toContain("authorityRequest");
  });

  it("rejects unknown windows rather than treating source bookmarks as installed apps", () => {
    const original = JSON.parse(encodeWorkspace(INITIAL_SHELL_STATE));
    original.windows[0].id = "app:made-up-app";
    expect(() => decodeWorkspace(JSON.stringify(original))).toThrow("unknown shell window");
  });

  it("rejects grants, execution requests, and unknown fields", () => {
    const original = JSON.parse(encodeWorkspace(INITIAL_SHELL_STATE));
    original.executionAuthority = true;
    expect(() => decodeWorkspace(JSON.stringify(original))).toThrow("Unsupported workspace");
    delete original.executionAuthority;
    original.windows[0].permissions = ["shell.execute"];
    expect(() => decodeWorkspace(JSON.stringify(original))).toThrow("unsupported fields");
  });

  it("rejects duplicated windows, off-desktop geometry and oversized layouts", () => {
    const original = JSON.parse(encodeWorkspace(INITIAL_SHELL_STATE));
    original.windows.push({ ...original.windows[0] });
    expect(() => decodeWorkspace(JSON.stringify(original))).toThrow("duplicate");
    original.windows.pop();
    original.windows[0].width = 200;
    expect(() => decodeWorkspace(JSON.stringify(original))).toThrow("geometry");
    expect(() => decodeWorkspace(" ".repeat(16 * 1024 + 1))).toThrow("16 KiB");
  });

  it("restores only the layout portion of the known app catalog", () => {
    const original = JSON.parse(encodeWorkspace(INITIAL_SHELL_STATE));
    original.windows.push({
      id: "app:phioffice", x: 10, y: 8, width: 78, height: 80, z: 9, state: "open",
    });
    const restored = decodeWorkspace(JSON.stringify(original));
    expect(restored.windows.at(-1)?.title).toBe("PhiOffice");
    expect(restored.windows.at(-1)?.subtitle).toBe("Not bundled");
    expect(restored.nextZ).toBe(10);
  });
});
