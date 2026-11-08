/**
 * Strict PhiOS R12 PixelForge project selection for a browser pilot.
 *
 * Identity metadata alone is NOT a grant. The actual host's approval must
 * be explicit, per iframe session, and invalidated if V2 bytes change.
 */
import {
  PIXELFORGE_V2_IDENTITY_SOURCE,
  PROJECT_REGISTRY_V2_KEY,
  decodeProjectRegistryV2,
  providerQualifiedProjectKey,
  type ProviderQualifiedProjectReference,
} from "./projectRegistryV2";

export { PROJECT_REGISTRY_V2_KEY };

export type PixelForgeBridgeChoice = Readonly<ProviderQualifiedProjectReference & {
  providerAppId: "pixelforge";
  source: typeof PIXELFORGE_V2_IDENTITY_SOURCE;
}>;

function exactPixelForge(entry: ProviderQualifiedProjectReference): entry is PixelForgeBridgeChoice {
  return entry.providerAppId === "pixelforge"
    && entry.source === PIXELFORGE_V2_IDENTITY_SOURCE;
}

/** Read-only, no fallback to V1 or user-supplied project-ref strings. */
export function listPixelForgeBridgeChoices(v2Raw: string | null): readonly PixelForgeBridgeChoice[] {
  if (v2Raw === null) throw new Error("No reviewed V2 project identity registry exists");
  const entries = decodeProjectRegistryV2(v2Raw);
  return Object.freeze(entries.filter(exactPixelForge));
}

/** Stale selections or wrong-provider records cannot become grants. */
export function verifyPixelForgeBridgeChoice(
  v2Raw: string | null, candidate: PixelForgeBridgeChoice,
): PixelForgeBridgeChoice {
  if (!candidate || candidate.providerAppId !== "pixelforge"
      || candidate.source !== PIXELFORGE_V2_IDENTITY_SOURCE
      || typeof candidate.projectRef !== "string"
      || typeof candidate.title !== "string") {
    throw new Error("Unreviewed or incorrect PixelForge bridge provider");
  }
  const options = listPixelForgeBridgeChoices(v2Raw);
  const pair = providerQualifiedProjectKey("pixelforge", candidate.projectRef);
  const found = options.find(x =>
    providerQualifiedProjectKey(x.providerAppId, x.projectRef) === pair);
  if (!found || found.title !== candidate.title || found.source !== candidate.source) {
    throw new Error("PixelForge V2 project changed since selection; new review required");
  }
  return found;
}
