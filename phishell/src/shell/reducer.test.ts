import { describe, expect, it } from "vitest";
import { INITIAL_SHELL_STATE, type AuthorityRequest } from "./model";
import { shellReducer } from "./reducer";
import { createZeroPrivilegeLinuxAdapter } from "./linuxAdapter";

describe("PhiShell desktop reducer", () => {
  it("raises a focused window deterministically", () => {
    const next = shellReducer(INITIAL_SHELL_STATE, {
      type: "FOCUS_WINDOW",
      id: "research-window",
    });

    const research = next.windows.find((window) => window.id === "research-window");
    const ledger = next.windows.find((window) => window.id === "ledger-window");

    expect(research?.z).toBeGreaterThan(ledger?.z ?? 0);
    expect(next.nextZ).toBe(4);
  });

  it("minimizes and restores without deleting window state", () => {
    const minimized = shellReducer(INITIAL_SHELL_STATE, {
      type: "MINIMIZE_WINDOW",
      id: "research-window",
    });
    const restored = shellReducer(minimized, {
      type: "RESTORE_WINDOW",
      id: "research-window",
    });

    expect(minimized.windows.find((window) => window.id === "research-window")?.state).toBe(
      "minimized",
    );
    expect(restored.windows.find((window) => window.id === "research-window")?.state).toBe(
      "open",
    );
  });

  it("records an approved intent without manufacturing execution authority", () => {
    const request: AuthorityRequest = {
      id: "authority:test",
      capability: "network.configure",
      scope: "wlan0",
      reason: "Fixture",
      requestedBy: "operator",
      decision: "pending",
      executionAuthority: false,
    };

    const requested = shellReducer(INITIAL_SHELL_STATE, {
      type: "REQUEST_AUTHORITY",
      request,
    });
    const resolved = shellReducer(requested, {
      type: "RESOLVE_AUTHORITY",
      decision: "approved_intent",
    });

    expect(resolved.authorityRequest?.decision).toBe("approved_intent");
    expect(resolved.authorityRequest?.executionAuthority).toBe(false);
  });
});

describe("zero privilege Linux adapter", () => {
  it("cannot convert an intent into an operating-system effect", async () => {
    const adapter = createZeroPrivilegeLinuxAdapter();

    const receipt = await adapter.request({
      id: "intent:test",
      capability: "service.control",
      scope: "example.service",
      requestedBy: "operator",
    });

    expect(adapter.operationalAuthority).toBe(false);
    expect(adapter.actionAuthority).toBe(false);
    expect(adapter.executionAuthority).toBe(false);
    expect(receipt.status).toBe("blocked");
    expect(receipt.effectPerformed).toBe(false);
    expect(receipt.executionAuthority).toBe(false);
  });
});
