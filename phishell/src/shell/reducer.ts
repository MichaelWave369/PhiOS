import type { ShellEvent, ShellState, ShellWindow } from "./model";

function raiseWindow(state: ShellState, id: string): ShellState {
  const nextZ = state.nextZ + 1;
  return {
    ...state,
    nextZ,
    windows: state.windows.map((window) =>
      window.id === id ? { ...window, z: nextZ } : window,
    ),
  };
}

function updateWindow(
  state: ShellState,
  id: string,
  update: (window: ShellWindow) => ShellWindow,
): ShellState {
  return {
    ...state,
    windows: state.windows.map((window) => (window.id === id ? update(window) : window)),
  };
}

export function shellReducer(state: ShellState, event: ShellEvent): ShellState {
  switch (event.type) {
    case "SET_VIEW":
      return { ...state, view: event.view };

    case "OPEN_WINDOW": {
      const existing = state.windows.find((window) => window.id === event.window.id);
      if (existing) {
        return raiseWindow(
          {
            ...state,
            windows: state.windows.map((window) =>
              window.id === event.window.id ? { ...window, state: "open" } : window,
            ),
          },
          event.window.id,
        );
      }

      return {
        ...state,
        nextZ: state.nextZ + 1,
        windows: [...state.windows, { ...event.window, z: state.nextZ + 1 }],
      };
    }

    case "FOCUS_WINDOW":
      return raiseWindow(state, event.id);

    case "MOVE_WINDOW":
      return updateWindow(state, event.id, (window) =>
        window.state === "maximized"
          ? window
          : {
              ...window,
              x: Math.max(0, Math.min(84, event.x)),
              y: Math.max(0, Math.min(78, event.y)),
            },
      );

    case "MINIMIZE_WINDOW":
      return updateWindow(state, event.id, (window) => ({ ...window, state: "minimized" }));

    case "RESTORE_WINDOW":
      return raiseWindow(
        updateWindow(state, event.id, (window) => ({ ...window, state: "open" })),
        event.id,
      );

    case "TOGGLE_MAXIMIZE_WINDOW":
      return raiseWindow(
        updateWindow(state, event.id, (window) => ({
          ...window,
          state: window.state === "maximized" ? "open" : "maximized",
        })),
        event.id,
      );

    case "CLOSE_WINDOW":
      return { ...state, windows: state.windows.filter((window) => window.id !== event.id) };

    case "OPEN_COMMAND":
      return { ...state, commandOpen: true, commandQuery: "" };

    case "CLOSE_COMMAND":
      return { ...state, commandOpen: false, commandQuery: "" };

    case "SET_COMMAND_QUERY":
      return { ...state, commandQuery: event.query };

    case "REQUEST_AUTHORITY":
      return { ...state, authorityRequest: event.request };

    case "RESOLVE_AUTHORITY":
      if (!state.authorityRequest) return state;
      return {
        ...state,
        authorityRequest: {
          ...state.authorityRequest,
          decision: event.decision,
          executionAuthority: false,
        },
      };

    default:
      return state;
  }
}
