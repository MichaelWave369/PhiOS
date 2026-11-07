import { normalizeBridgeOrigin } from "./workspaceBridge";

export interface PhiOfficePilotEndpoint {
  url: string;
  origin: string;
}

/**
 * Build-time operator configuration, not an app-store listing.
 * Two explicit matching settings prevent accidentally trusting a homepage.
 */
export function reviewPhiOfficePilotEndpoint(
  rawUrl: string | undefined,
  rawOrigin: string | undefined,
  shellOrigin: string,
): PhiOfficePilotEndpoint | null {
  if (!rawUrl || !rawOrigin) return null;
  try {
    const origin = normalizeBridgeOrigin(rawOrigin);
    const parent = normalizeBridgeOrigin(shellOrigin);
    const url = new URL(rawUrl);
    if (url.href !== rawUrl || url.origin !== origin || origin === parent
        || url.username || url.password || url.search || url.hash
        || !url.pathname.startsWith("/") || rawUrl.length > 600) return null;
    return { url: rawUrl, origin };
  } catch {
    return null;
  }
}
