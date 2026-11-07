/**
 * PhiOS project identity adapter catalog R1.
 *
 * The catalog is reviewed source code, not a writable plugin registry.
 * Reading an identity ref is NOT verifying ownership or granting file access.
 * Future adapters require explicit code review, validation and browser tests.
 */
import { WORKSPACE_BRIDGE_PROTOCOL } from "./workspaceBridge";

export const PROJECT_ADAPTER_CATALOG_VERSION = 1;
export const PHIOFFICE_MANIFEST_SOURCE = "phioffice369.project_manifest.v0.1" as const;

export type ProjectAdapterDefinition = Readonly<{
  id: string;
  source: string;
  providerAppId: string;
  targetAppId: string;
  title: string;
  selection: "operator-selected-local-manifest";
  transfer: "opaque-project-ref-only";
  protocol: typeof WORKSPACE_BRIDGE_PROTOCOL;
  executionAuthority: false;
  status: "reviewed-browser-pilot";
}>;

/**
 * A build-time allowlist. This does not discover network services or attest
 * external code. Only PhiOffice's v0.1 manifest + tested browser bridge are
 * admitted. PhiID and PhiCloud are deliberately not registered.
 */
export const REVIEWED_PROJECT_ADAPTERS = Object.freeze([
  Object.freeze({
    id: "phioffice-manifest-bridge-v1",
    source: PHIOFFICE_MANIFEST_SOURCE,
    providerAppId: "phioffice",
    targetAppId: "phioffice",
    title: "PhiOffice project manifest v0.1",
    selection: "operator-selected-local-manifest",
    transfer: "opaque-project-ref-only",
    protocol: WORKSPACE_BRIDGE_PROTOCOL,
    executionAuthority: false,
    status: "reviewed-browser-pilot",
  } as const satisfies ProjectAdapterDefinition),
]);

export type ReviewedProjectAdapter = (typeof REVIEWED_PROJECT_ADAPTERS)[number];
export type ReviewedProjectSource = ReviewedProjectAdapter["source"];

export function findReviewedProjectAdapter(source: unknown): ReviewedProjectAdapter | null {
  if (typeof source !== "string") return null;
  return REVIEWED_PROJECT_ADAPTERS.find((adapter) => adapter.source === source) ?? null;
}

export function isReviewedProjectSource(source: unknown): source is ReviewedProjectSource {
  return findReviewedProjectAdapter(source) !== null;
}

export function findProjectAdapterForTarget(
  source: unknown, targetAppId: unknown,
): ReviewedProjectAdapter | null {
  const adapter = findReviewedProjectAdapter(source);
  if (typeof targetAppId !== "string"
      || !adapter || adapter.targetAppId !== targetAppId) return null;
  return adapter;
}

/** Intended for read-only provenance display, not an authorization check. */
export function listReviewedProjectAdapters(): readonly ReviewedProjectAdapter[] {
  return REVIEWED_PROJECT_ADAPTERS;
}
