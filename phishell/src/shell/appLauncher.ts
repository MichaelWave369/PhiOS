import type { ShellEvent, ShellWindow } from "./model";

export interface ShellApp {
  id: string;
  name: string;
  icon: string;
  status: string;
  description: string;
  windowId?: string;
}

// Shipped shell destinations, not an installed-app or runtime-health probe.
export const SHELL_APPS: readonly ShellApp[] = [
  { id: "browsallax", name: "Browsallax", icon: "◉", status: "Not bundled",
    description: "Browsallax is not included in this image. Chromium is the included browser; open it from the desktop application menu with Super+Space." },
  { id: "phivessel", name: "PhiVessel", icon: "◉", status: "Advisory only",
    description: "The PhiVessel dock shows read-only runtime context. A conversational PhiVessel runtime is not connected, so the dock cannot answer prompts." },
  { id: "brainc", name: "BrainC", icon: "Φ", status: "Client only",
    description: "PhiOS includes BrainC client code and the brainc status terminal command. Ollama and model weights are not bundled; local inference needs a separately configured runtime. Open the Phi terminal with Super+Enter and enter brainc status to check the configured endpoint." },
  { id: "phioffice", name: "PhiOffice", icon: "▧", status: "Not bundled",
    description: "PhiOffice is not included in this image." },
  { id: "domistika", name: "Domistika", icon: "⌂", status: "Not bundled",
    description: "Domistika is not included in this image." },
  { id: "soma", name: "SOMA", icon: "◌", status: "CLI tools only",
    description: "PhiOS includes SOMA contracts and Spine terminal tools. This image does not include a separate SOMA graphical app. Open Foot with Super+Alt+Enter and run phi-spine --help to inspect the included commands." },
  { id: "professor", name: "Professor Φ", icon: "Φ", status: "Not bundled",
    description: "A Professor Φ application runtime is not included in this image." },
  { id: "ledger", name: "Reality Ledger", icon: "▤", status: "Read-only tool",
    description: "Open governed canonical history. Reads still require the existing history and memory grants.", windowId: "ledger-window" },
  { id: "builder", name: "Builder", icon: "⌘", status: "Workspace preview",
    description: "Open the build proposal workspace. It does not compile projects or run commands.", windowId: "build-window" },
  { id: "system", name: "System Inspector", icon: "⚙", status: "Read-only tool",
    description: "Inspect host, services, processes, packages and devices.", windowId: "system-window" },
  { id: "dream", name: "ΦDream", icon: "☾", status: "Symbol Lab",
    description: "Open the included Symbol Lab curiosity workspace.", windowId: "dream-window" },
  { id: "apps", name: "Apps", icon: "⊞", status: "App status",
    description: "See what this image includes and how to open ordinary Linux apps.", windowId: "apps-window" },
];

export function findShellApp(id: string): ShellApp | undefined {
  return SHELL_APPS.find((app) => app.id === id);
}

function appWindow(id: string, title: string, subtitle: string): ShellWindow {
  return { id, title, subtitle, kind: "workspace", x: 10, y: 8, width: 78,
    height: 80, z: 1, state: "open" };
}

export const appWindowTemplates: Record<string, ShellWindow> = {
  "apps-window": appWindow("apps-window", "Apps", "Included tools and integration status."),
  "dream-window": appWindow("dream-window", "ΦDream / Symbol Lab", "Curiosity workspace."),
};

export const windowTemplates: Record<string, ShellWindow> = {
  ...appWindowTemplates,
  "research-window": {
    id: "research-window",
    title: "Research Field",
    subtitle: "Evidence, provenance, synthesis, and source context.",
    kind: "workspace",
    x: 7,
    y: 10,
    width: 54,
    height: 58,
    z: 1,
    state: "open",
  },
  "ledger-window": {
    id: "ledger-window",
    title: "Reality Ledger",
    subtitle: "Read-only receipts and system history projection.",
    kind: "system",
    x: 46,
    y: 30,
    width: 46,
    height: 48,
    z: 2,
    state: "open",
  },
  "build-window": {
    id: "build-window",
    title: "Build Field",
    subtitle: "Projects, tests, artifacts, and governed execution proposals.",
    kind: "workspace",
    x: 20,
    y: 16,
    width: 58,
    height: 56,
    z: 1,
    state: "open",
  },
  "system-window": {
    id: "system-window",
    title: "System Inspector",
    subtitle: "Session history, canonical recall, and temporary governed comparison of two persistent machine states.",
    kind: "system",
    x: 22,
    y: 10,
    width: 68,
    height: 72,
    z: 1,
    state: "open",
  },
};

export function shellAppEvent(id: string): ShellEvent | null {
  const app = findShellApp(id);
  if (!app) return null;
  const template = app.windowId
    ? windowTemplates[app.windowId]
    : appWindow(`app:${app.id}`, app.name, app.status);
  return template ? { type: "OPEN_WINDOW", window: { ...template } } : null;
}
