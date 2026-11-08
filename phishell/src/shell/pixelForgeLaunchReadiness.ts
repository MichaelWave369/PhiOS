/**
 * R14 PixelForge launch discovery is observation, NEVER install or authority.
 * It makes no network requests, performs no writes and creates no iframe.
 */
import { reviewPhiOfficePilotEndpoint } from "./workspaceBridgePilotConfig";
import { listPixelForgeBridgeChoices } from "./pixelForgeBridgeSelection";

export type PixelForgeLaunchReadiness = Readonly<{
  status: "endpoint-disabled" | "registry-invalid" | "no-pixelforge-identity" | "browser-pilot-ready";
  endpointOrigin: string | null;
  pixelForgeIdentityCount: number;
  browserPilotConfigured: boolean;
  nativeInstalled: false;
  automaticallyLaunched: false;
  permissionGranted: false;
}>;

export function inspectPixelForgeLaunchReadiness(args: {
  configuredUrl?: string;
  approvedOrigin?: string;
  shellOrigin: string;
  v2Raw: string | null;
}): PixelForgeLaunchReadiness {
  const endpoint = reviewPhiOfficePilotEndpoint(
    args.configuredUrl, args.approvedOrigin, args.shellOrigin,
  );
  // Failure of the endpoint gate always disables the bridge, regardless of
  // arbitrary user-managed registry records or apparent app catalog entries.
  if (!endpoint) {
    return Object.freeze({
      status: "endpoint-disabled" as const, endpointOrigin: null,
      pixelForgeIdentityCount: 0, browserPilotConfigured: false,
      nativeInstalled: false as const, automaticallyLaunched: false as const,
      permissionGranted: false as const,
    });
  }
  try {
    const entries = listPixelForgeBridgeChoices(args.v2Raw);
    return Object.freeze({
      status: (entries.length ? "browser-pilot-ready" : "no-pixelforge-identity") as
        "browser-pilot-ready" | "no-pixelforge-identity",
      endpointOrigin: endpoint.origin,
      pixelForgeIdentityCount: entries.length,
      browserPilotConfigured: true,
      nativeInstalled: false as const, automaticallyLaunched: false as const,
      permissionGranted: false as const,
    });
  } catch {
    return Object.freeze({
      status: "registry-invalid" as const, endpointOrigin: endpoint.origin,
      pixelForgeIdentityCount: 0, browserPilotConfigured: true,
      nativeInstalled: false as const, automaticallyLaunched: false as const,
      permissionGranted: false as const,
    });
  }
}
