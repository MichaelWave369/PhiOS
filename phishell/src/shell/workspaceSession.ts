import { findShellApp, windowTemplates } from "./appLauncher";
import {
  INITIAL_SHELL_STATE,
  type ShellState,
  type ShellWindow,
  type View,
  type WindowState,
} from "./model";

/**
 * Portable, *layout-only* state. This intentionally excludes identities, files,
 * app data, authority requests, access tokens, receipts and execution grants.
 */
export const WORKSPACE_STORAGE_KEY = "phios.workspace-layout.v1";
export const WORKSPACE_FORMAT = "phios.workspace-layout";
export const WORKSPACE_VERSION = 1;
export const MAX_WORKSPACE_BYTES = 16 * 1024;
const MAX_WINDOWS = 24;
const VIEWS: readonly View[] = [
  "home", "research", "dream", "build", "memory", "ledger", "governance", "settings",
];
const WINDOW_STATES: readonly WindowState[] = ["open", "minimized", "maximized"];
const WINDOW_FIELDS = ["id", "x", "y", "width", "height", "z", "state"] as const;

type SavedWindow = Pick<ShellWindow, (typeof WINDOW_FIELDS)[number]>;

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length
    && Object.keys(value).every((key) => keys.includes(key));
}

function finiteRange(value: unknown, lower: number, upper: number): value is number {
  return typeof value === "number" && Number.isFinite(value)
    && value >= lower && value <= upper;
}

function templateFor(id: string): ShellWindow | undefined {
  if (Object.hasOwn(windowTemplates, id)) return windowTemplates[id];
  if (!id.startsWith("app:")) return undefined;
  const app = findShellApp(id.slice(4));
  if (!app || app.windowId) return undefined;
  return {
    id, title: app.name, subtitle: app.status, kind: "workspace",
    x: 10, y: 8, width: 78, height: 80, z: 1, state: "open",
  };
}

function readWindow(input: unknown): ShellWindow {
  if (!record(input) || !exactKeys(input, WINDOW_FIELDS)) {
    throw new Error("Workspace window has unsupported fields");
  }
  const { id, x, y, width, height, z, state } = input;
  if (typeof id !== "string") throw new Error("Invalid workspace window id");
  const template = templateFor(id);
  if (!template) throw new Error("Workspace references an unknown shell window");
  if (!finiteRange(x, 0, 84) || !finiteRange(y, 0, 78)
      || !finiteRange(width, 16, 100) || !finiteRange(height, 22, 100)
      || x + width > 100 || y + height > 100) {
    throw new Error("Workspace window geometry is outside the desktop");
  }
  if (!Number.isInteger(z) || !finiteRange(z, 0, 100000)
      || !WINDOW_STATES.includes(state as WindowState)) {
    throw new Error("Invalid workspace window state");
  }
  return {
    ...template,
    x, y, width, height, z, state: state as WindowState,
  };
}

function savedWindow(window: ShellWindow): SavedWindow {
  const { id, x, y, width, height, z, state } = window;
  return { id, x, y, width, height, z, state };
}

export function encodeWorkspace(state: ShellState): string {
  // Validate our own snapshot too, so future callers cannot bypass the wire rules.
  const payload = {
    format: WORKSPACE_FORMAT,
    version: WORKSPACE_VERSION,
    view: state.view,
    windows: state.windows.map(savedWindow),
  };
  const json = JSON.stringify(payload);
  decodeWorkspace(json);
  return json + "\n";
}

export function decodeWorkspace(json: string): ShellState {
  if (new TextEncoder().encode(json).byteLength > MAX_WORKSPACE_BYTES) {
    throw new Error("Workspace layout exceeds 16 KiB");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new Error("Workspace layout is not valid JSON");
  }
  if (!record(parsed) || !exactKeys(parsed, ["format", "version", "view", "windows"])
      || parsed.format !== WORKSPACE_FORMAT || parsed.version !== WORKSPACE_VERSION
      || !VIEWS.includes(parsed.view as View) || !Array.isArray(parsed.windows)
      || parsed.windows.length > MAX_WINDOWS) {
    throw new Error("Unsupported workspace layout version or shape");
  }

  const windows = parsed.windows.map(readWindow);
  const ids = windows.map((window) => window.id);
  if (new Set(ids).size !== ids.length) {
    throw new Error("Workspace layout contains duplicate windows");
  }
  return {
    ...INITIAL_SHELL_STATE,
    view: parsed.view as View,
    windows,
    nextZ: Math.max(0, ...windows.map((window) => window.z)) + 1,
    authorityRequest: null,
    commandOpen: false,
    commandQuery: "",
  };
}

export function loadWorkspaceFromLocalStorage(): ShellState {
  try {
    const saved = globalThis.localStorage.getItem(WORKSPACE_STORAGE_KEY);
    return saved ? decodeWorkspace(saved) : INITIAL_SHELL_STATE;
  } catch {
    return INITIAL_SHELL_STATE;
  }
}

export function persistWorkspaceToLocalStorage(state: ShellState): void {
  globalThis.localStorage.setItem(WORKSPACE_STORAGE_KEY, encodeWorkspace(state));
}
