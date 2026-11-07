import type { ShellEvent, View } from "./model";

/**
 * PhiPose v0.1 OPTIONAL foreground shell-navigation receiver.
 * The only effects are typed, non-privileged PhiShell reducer events.
 * A same-origin message + session ID is NOT authentication. Host activation
 * is manual and revocable. No OS, app launches, files, tokens or Spine access.
 */
export const PHIPOSE_NAV_PROTOCOL = "phios.gesture-nav.v0.1";
export const PHIPOSE_NAV_ACTIONS: Readonly<Record<string, View | "command">> = Object.freeze({
  "phios.view.home": "home",
  "phios.view.research": "research",
  "phios.view.build": "build",
  "phios.view.ledger": "ledger",
  "phios.command.open": "command",
});
export interface PhiPoseNavSession {
  source: Window;
  origin: string;
  sessionId: string;
  expiresAt: number;
  allowSyntheticDemo: boolean;
}
export type PhiPoseNavResult =
  | { accepted: false; reason: string }
  | { accepted: true; reason: "ui_dispatch"; actionId: string; sequence: number; event: ShellEvent };

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export class PhiPoseNavigationHost {
  private session: PhiPoseNavSession | null = null;
  private lastSequence = 0;
  private lastAcceptedAt = -Infinity;

  get active(): boolean { return this.session !== null; }
  revoke(): void {
    this.session = null;
    this.lastSequence = 0;
    this.lastAcceptedAt = -Infinity;
  }
  /**
   * Call only from an explicit operator click, after the embedding UI has
   * verified the opener is the intended installed/approved companion.
   */
  enable(config: PhiPoseNavSession, nowMs: number): void {
    this.revoke();
    if (!config || !config.source || typeof config.origin !== "string" ||
      !/^https:\/\/[^\s/]+$/.test(config.origin) ||
      !/^[a-zA-Z0-9-]{16,80}$/.test(config.sessionId) ||
      typeof config.allowSyntheticDemo !== "boolean" ||
      !Number.isSafeInteger(nowMs) ||
      !Number.isSafeInteger(config.expiresAt) ||
      config.expiresAt - nowMs < 30_000 || config.expiresAt - nowMs > 300_000) {
      throw new TypeError("Invalid or unbounded PhiPose host session");
    }
    this.session = Object.freeze({ ...config });
  }
  accept(message: Pick<MessageEvent, "data" | "origin" | "source">, nowMs: number): PhiPoseNavResult {
    const session = this.session;
    if (!session) return { accepted: false, reason: "disabled" };
    if (!Number.isSafeInteger(nowMs) || nowMs > session.expiresAt) {
      this.revoke();
      return { accepted: false, reason: "expired" };
    }
    if (message.source !== session.source || message.origin !== session.origin)
      return { accepted: false, reason: "untrusted_source" };
    const data: unknown = message.data;
    if (!object(data) || data.protocol !== PHIPOSE_NAV_PROTOCOL || data.type !== "command" ||
      data.session_id !== session.sessionId ||
      !Number.isSafeInteger(data.sent_at) ||
      (data.sent_at as number) < nowMs - 2500 ||
      (data.sent_at as number) > nowMs + 250) {
      return { accepted: false, reason: "invalid_envelope" };
    }
    const intent: unknown = data.intent;
    if (!object(intent) ||
      intent.schema !== "overstrings.phipose.intent.v0.1" ||
      intent.version !== 1 || intent.advisory !== true ||
      intent.action_authority !== false || intent.execution_authority !== false ||
      typeof intent.program !== "string" || intent.program.length > 140 ||
      !/^([LR]:(open|pinch|grab|point|swipe-left|swipe-right)(\+[LR]:(open|pinch|grab|point|swipe-left|swipe-right))?)( > ([LR]:(open|pinch|grab|point|swipe-left|swipe-right)(\+[LR]:(open|pinch|grab|point|swipe-left|swipe-right))?)){1,4}$/.test(intent.program) ||
      typeof intent.action_id !== "string" ||
      !Object.prototype.hasOwnProperty.call(PHIPOSE_NAV_ACTIONS, intent.action_id) ||
      !["webxr","synthetic"].includes(String(intent.source)) ||
      (intent.source === "synthetic" && !session.allowSyntheticDemo) ||
      !Number.isSafeInteger(intent.sequence) || (intent.sequence as number) <= 0) {
      return { accepted: false, reason: "invalid_intent" };
    }
    const sequence = intent.sequence as number;
    if (sequence <= this.lastSequence) return { accepted: false, reason: "replay" };
    if (nowMs - this.lastAcceptedAt < 900) return { accepted: false, reason: "cooldown" };
    const actionId = intent.action_id;
    const kind = PHIPOSE_NAV_ACTIONS[actionId]!;
    const event: ShellEvent = kind === "command"
      ? { type: "OPEN_COMMAND" }
      : { type: "SET_VIEW", view: kind };
    // This only validates a locally approved UI navigation action.
    // Never run it through an OS/Spine executor without separate authority.
    this.lastSequence = sequence;
    this.lastAcceptedAt = nowMs;
    return { accepted: true, reason: "ui_dispatch", actionId, sequence, event };
  }
}
