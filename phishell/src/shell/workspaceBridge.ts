/**
 * PhiOS read-only workspace context bridge v1.
 *
 * No iframe or application is created here. The host must register one exact
 * origin and WindowProxy from a separately reviewed, operator-selected app.
 * No native privileges, installs, filesystem paths or document data cross.
 */
export const WORKSPACE_BRIDGE_PROTOCOL = "phios.workspace-bridge.v1";
export const WORKSPACE_BRIDGE_MAX_BYTES = 2048;

export type BridgeEvent = { origin: string; source: unknown; data: unknown };
export type BridgeSend = { targetOrigin: string; message: Record<string, unknown> };
export type BridgeHostConfig = {
  appId: string;
  appOrigin: string;
  frameSource: object;
  sessionId: string;
};

const APP_ID = /^[a-z][a-z0-9._-]{0,63}$/;
const PROJECT_ID = /^project:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const SESSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function keysAre(value: Record<string, unknown>, allowed: readonly string[]): boolean {
  return Object.keys(value).length === allowed.length
    && Object.keys(value).every((key) => allowed.includes(key));
}

/** No wildcard origins. HTTPS required except explicitly local loopback. */
export function normalizeBridgeOrigin(input: string): string {
  if (typeof input !== "string" || !input || input.length > 300) {
    throw new Error("Bridge origin must be an exact URL origin");
  }
  let url: URL;
  try { url = new URL(input); } catch { throw new Error("Invalid bridge origin"); }
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.origin !== input || url.username || url.password
      || (url.protocol !== "https:" && !(url.protocol === "http:" && loopback))) {
    throw new Error("Bridge requires an exact HTTPS origin (or local loopback)");
  }
  return url.origin;
}

function incoming(value: unknown): {
  type: "app.hello" | "app.context.request";
  app_id: string;
  session_id: string;
  request_id: string;
} | null {
  if (!object(value) || !keysAre(value, ["protocol", "type", "app_id", "session_id", "request_id"])) {
    return null;
  }
  if (value.protocol !== WORKSPACE_BRIDGE_PROTOCOL
      || (value.type !== "app.hello" && value.type !== "app.context.request")
      || typeof value.app_id !== "string" || !APP_ID.test(value.app_id)
      || typeof value.session_id !== "string" || !SESSION_ID.test(value.session_id)
      || typeof value.request_id !== "string" || !REQUEST_ID.test(value.request_id)) {
    return null;
  }
  try {
    if (new TextEncoder().encode(JSON.stringify(value)).byteLength > WORKSPACE_BRIDGE_MAX_BYTES) {
      return null;
    }
  } catch { return null; }
  return {
    type: value.type,
    app_id: value.app_id,
    session_id: value.session_id,
    request_id: value.request_id,
  } as {
    type: "app.hello" | "app.context.request";
    app_id: string; session_id: string; request_id: string;
  };
}

/**
 * Only the embedding host can approve or revoke read access. The returned
 * payload is for source.postMessage(message, targetOrigin), never '*'.
 */
export function createWorkspaceBridgeHost(config: BridgeHostConfig) {
  if (!APP_ID.test(config.appId) || !SESSION_ID.test(config.sessionId)
      || !object(config.frameSource)) {
    throw new Error("Invalid app identity, source binding, or session ID");
  }
  const targetOrigin = normalizeBridgeOrigin(config.appOrigin);
  let approvedProject: string | null = null;

  const send = (message: Record<string, unknown>): BridgeSend => ({
    targetOrigin, message,
  });
  const envelope = (type: string, requestId?: string): Record<string, unknown> => ({
    protocol: WORKSPACE_BRIDGE_PROTOCOL,
    type,
    app_id: config.appId,
    session_id: config.sessionId,
    ...(requestId ? { request_id: requestId } : {}),
    execution_authority: false,
  });

  return {
    bootstrap(): BridgeSend {
      return send(envelope("host.bootstrap"));
    },
    /** Call only in a visible, explicit operator approval flow. */
    approveProject(projectId: string): void {
      if (typeof projectId !== "string" || !PROJECT_ID.test(projectId)) {
        throw new Error("Only bounded opaque project references may be shared");
      }
      approvedProject = projectId;
    },
    revokeProject(): void { approvedProject = null; },
    handle(event: BridgeEvent): BridgeSend | null {
      if (event.origin !== targetOrigin || event.source !== config.frameSource) return null;
      const message = incoming(event.data);
      if (!message || message.app_id !== config.appId
          || message.session_id !== config.sessionId) return null;
      if (message.type === "app.hello") {
        return send({ ...envelope("host.ready", message.request_id),
          read_approved: approvedProject !== null });
      }
      if (!approvedProject) {
        return send({ ...envelope("host.denied", message.request_id),
          reason: "operator_approval_required" });
      }
      return send({
        ...envelope("host.context", message.request_id),
        project_ref: approvedProject,
      });
    },
  };
}

/** Each embedding session gets a fresh, host-generated identifier. */
export function generateBridgeSessionId(): string {
  return globalThis.crypto.randomUUID();
}
