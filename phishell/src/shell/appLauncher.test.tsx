import { Children, isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AppDetails, AppTiles } from "../components/AppLauncher";
import { PhiShell } from "../PhiShell";
import { findShellApp, SHELL_APPS, shellAppEvent } from "./appLauncher";
import { INITIAL_SHELL_STATE, type ShellState } from "./model";
import { shellReducer } from "./reducer";

function tileButtons(node: ReactNode): Array<{ label: string; click: () => void }> {
  return Children.toArray(node).flatMap((child) => {
    if (!isValidElement<{ children?: ReactNode; "aria-label"?: string; onClick?: () => void }>(child)) return [];
    if (child.type === "button" && child.props.onClick) {
      return [{ label: child.props["aria-label"] ?? "", click: child.props.onClick }];
    }
    return tileButtons(child.props.children);
  });
}

const destinations: Record<string, string> = {
  "Browsallax": "app:browsallax", "PhiVessel": "app:phivessel", "BrainC": "app:brainc",
  "PhiOffice": "app:phioffice", "Domistika": "app:domistika", "SOMA": "app:soma",
  "Professor Φ": "app:professor", "Reality Ledger": "ledger-window",
  "Builder": "build-window", "System Inspector": "system-window",
  "ΦDream": "dream-window", "Apps": "apps-window",
};

describe("rendered app launcher clicks", () => {
  it.each([false, true])("wires every %s-pinned tile to its actual shell destination", (pinned) => {
    let state: ShellState = { ...INITIAL_SHELL_STATE, windows: [] };
    const fetcher = vi.spyOn(globalThis, "fetch");
    try {
      const tiles = tileButtons(AppTiles({ pinned, openApp: (id) => {
        const event = shellAppEvent(id);
        if (event) state = shellReducer(state, event);
      } }));
      expect(tiles).toHaveLength(pinned ? 6 : 12);
      for (const tile of tiles) {
        tile.click();
        const name = tile.label.split(" · ")[0];
        expect(state.windows.at(-1)?.id).toBe(destinations[name]);
        expect(state.authorityRequest).toBeNull();
      }
      expect(fetcher).not.toHaveBeenCalled();
    } finally {
      fetcher.mockRestore();
    }
  });

  it("restores a minimized tool and recreates a closed tool without duplicate windows", () => {
    const event = shellAppEvent("system");
    if (!event) throw new Error("missing system launcher");
    const opened = shellReducer(INITIAL_SHELL_STATE, event);
    const minimized = shellReducer(opened, { type: "MINIMIZE_WINDOW", id: "system-window" });
    const restored = shellReducer(minimized, event);
    expect(restored.windows.filter((item) => item.id === "system-window")).toHaveLength(1);
    expect(restored.windows.find((item) => item.id === "system-window")?.state).toBe("open");
    expect(restored.windows.find((item) => item.id === "system-window")?.z).toBeGreaterThan(opened.nextZ);
    const closed = shellReducer(restored, { type: "CLOSE_WINDOW", id: "system-window" });
    expect(shellReducer(closed, event).windows.filter((item) => item.id === "system-window")).toHaveLength(1);
  });

  it.each(["", "constructor", "__proto__", "../../bin/sh", "chromium --no-sandbox"])(
    "ignores unrecognized app IDs: %s", (id) => expect(shellAppEvent(id)).toBeNull(),
  );

  it("does not let moving a window mutate the shared launch template", () => {
    const event = shellAppEvent("apps");
    if (!event || event.type !== "OPEN_WINDOW") throw new Error("missing apps launcher");
    event.window.x = 99;
    const fresh = shellAppEvent("apps");
    expect(fresh?.type === "OPEN_WINDOW" && fresh.window.x).toBe(10);
  });
});

describe("shipped integration status", () => {
  it.each([
    ["browsallax", "Not bundled", "Chromium"],
    ["phivessel", "Advisory only", "cannot answer prompts"],
    ["brainc", "Client only", "Ollama and model weights are not bundled"],
  ])("explains why %s does not launch a full runtime", (id, status, detail) => {
    const app = findShellApp(id);
    if (!app) throw new Error("missing integration");
    expect(app.status).toBe(status);
    expect(app.windowId).toBeUndefined();
    expect(renderToStaticMarkup(<AppDetails app={app} />)).toContain(detail);
  });

  it("includes status on every tile and disables the unconnected chat prompt", () => {
    const html = renderToStaticMarkup(<PhiShell />);
    for (const app of SHELL_APPS) expect(html).toContain(`${app.name} · ${app.status}`);
    expect(html).toMatch(/<input[^>]*aria-label="PhiVessel chat unavailable"[^>]*disabled/);
    expect(html).toMatch(/<button[^>]*aria-label="Send unavailable: chat runtime not connected"[^>]*disabled/);
    expect(html).toContain("Reading governed persistent history");
    expect(html).not.toContain("Ask PhiVessel anything");
    expect(html).not.toContain("shell.window.focus");
  });
});
