export type View =
  | "home"
  | "research"
  | "dream"
  | "build"
  | "memory"
  | "ledger"
  | "governance"
  | "settings";

export type VesselMode = "chat" | "dream" | "translate" | "build" | "ledger";
export type WindowKind = "workspace" | "system" | "authority";
export type WindowState = "open" | "minimized" | "maximized";
export type AuthorityDecision = "pending" | "approved_intent" | "denied";

export interface ShellWindow {
  id: string;
  title: string;
  subtitle: string;
  kind: WindowKind;
  x: number;
  y: number;
  width: number;
  height: number;
  z: number;
  state: WindowState;
}

export interface AuthorityRequest {
  id: string;
  capability: string;
  scope: string;
  reason: string;
  requestedBy: "operator" | "phivessel" | "system";
  decision: AuthorityDecision;
  executionAuthority: false;
}

export interface CommandItem {
  id: string;
  label: string;
  detail: string;
  action:
    | { type: "open-view"; view: View }
    | { type: "open-window"; windowId: string }
    | { type: "request-authority"; capability: string };
}

export interface ShellState {
  view: View;
  windows: ShellWindow[];
  commandOpen: boolean;
  commandQuery: string;
  authorityRequest: AuthorityRequest | null;
  nextZ: number;
}

export type ShellEvent =
  | { type: "SET_VIEW"; view: View }
  | { type: "OPEN_WINDOW"; window: ShellWindow }
  | { type: "FOCUS_WINDOW"; id: string }
  | { type: "MOVE_WINDOW"; id: string; x: number; y: number }
  | { type: "MINIMIZE_WINDOW"; id: string }
  | { type: "RESTORE_WINDOW"; id: string }
  | { type: "TOGGLE_MAXIMIZE_WINDOW"; id: string }
  | { type: "CLOSE_WINDOW"; id: string }
  | { type: "OPEN_COMMAND" }
  | { type: "CLOSE_COMMAND" }
  | { type: "SET_COMMAND_QUERY"; query: string }
  | { type: "REQUEST_AUTHORITY"; request: AuthorityRequest }
  | { type: "RESOLVE_AUTHORITY"; decision: Exclude<AuthorityDecision, "pending"> }
  | { type: "CLEAR_AUTHORITY" };

export const INITIAL_WINDOWS: ShellWindow[] = [
  {
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
  {
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
];

export const INITIAL_SHELL_STATE: ShellState = {
  view: "home",
  windows: INITIAL_WINDOWS,
  commandOpen: false,
  commandQuery: "",
  authorityRequest: null,
  nextZ: 3,
};
