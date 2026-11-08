/**
 * R10: independent, quarantined parser for PixelForge VR identity-only R1.
 *
 * Producer under review: parallax-pixelforge PR #88, exact source commit
 * b74802b358e9c23bc520ef3c0a46699498186c51.
 *
 * This module DOES NOT add PixelForge to REVIEWED_PROJECT_ADAPTERS, select
 * an iframe, write either registry, claim owner identity, or grant authority.
 * It only parses one file selected by an operator in an independent test.
 */
import {
  providerQualifiedProjectKey,
  validateQualifiedProjectEntry,
  type ProviderQualifiedProjectReference,
} from "./projectRegistryV2";

export const PIXELFORGE_CANDIDATE_PRODUCER_SHA =
  "b74802b358e9c23bc520ef3c0a46699498186c51" as const;
export const PIXELFORGE_CANDIDATE_SCHEMA =
  "pixelforge.phios-vr-world-identity.v0.1" as const;
export const PIXELFORGE_CANDIDATE_WORLD_FORMAT = "pixelforge.vr-world.v1" as const;
export const PIXELFORGE_CANDIDATE_PROVIDER_ID = "pixelforge" as const;
export const PIXELFORGE_CANDIDATE_MAX_BYTES = 4 * 1024;

export type PixelForgeCandidateIdentity = Readonly<{
  providerAppId: typeof PIXELFORGE_CANDIDATE_PROVIDER_ID;
  source: typeof PIXELFORGE_CANDIDATE_SCHEMA;
  projectRef: string;
  title: string;
  admission: "candidate-only";
  executionAuthority: false;
}>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactly(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length
    && Object.keys(value).every((key) => keys.includes(key));
}

/** Strictly mirrors the pinned PixelForge R1 producer contract, not its UI. */
export function parsePixelForgeCandidateIdentity(raw: string): PixelForgeCandidateIdentity {
  if (typeof raw !== "string" ||
      new TextEncoder().encode(raw).byteLength > PIXELFORGE_CANDIDATE_MAX_BYTES) {
    throw new Error("PixelForge candidate identity exceeds 4 KiB");
  }
  let input: unknown;
  try {
    input = JSON.parse(raw);
  } catch {
    throw new Error("PixelForge candidate identity is not valid JSON");
  }
  if (!isRecord(input)
      || !exactly(input, ["schema", "projectId", "title", "worldFormat"])
      || input.schema !== PIXELFORGE_CANDIDATE_SCHEMA
      || input.worldFormat !== PIXELFORGE_CANDIDATE_WORLD_FORMAT) {
    throw new Error("PixelForge candidate identity has unsupported fields or format");
  }
  const { projectId, title } = input;
  if (typeof projectId !== "string"
      || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(projectId)
      || projectId.includes("..") || projectId.endsWith(".")) {
    throw new Error("PixelForge candidate project ID is invalid");
  }
  if (typeof title !== "string" || title.length < 1 || title.length > 100
      || title.trim() !== title
      || /[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/.test(title)) {
    throw new Error("PixelForge candidate project title is invalid");
  }
  return Object.freeze({
    providerAppId: PIXELFORGE_CANDIDATE_PROVIDER_ID,
    projectRef: "project:" + projectId,
    title,
    source: PIXELFORGE_CANDIDATE_SCHEMA,
    admission: "candidate-only" as const,
    executionAuthority: false as const,
  });
}

export type PixelForgeIdentityCollisionEvidence = Readonly<{
  sameTextRef: boolean;
  differentProviderKey: boolean;
  firstProvider: "phioffice";
  secondProvider: "pixelforge";
  firstKey: string;
  secondKey: string;
  v2Writes: 0;
  bridgeRequests: 0;
  authorityTransferred: false;
}>;

/**
 * Pure review-time comparison. This function never decodes/stores a V2
 * record for an unadmitted PixelForge source and never speaks to an iframe.
 */
export function compareCandidateIdentityWithPhiOffice(
  reviewedOffice: ProviderQualifiedProjectReference,
  candidate: PixelForgeCandidateIdentity,
): PixelForgeIdentityCollisionEvidence {
  const office = validateQualifiedProjectEntry(reviewedOffice);
  if (office.providerAppId !== "phioffice" ||
      !candidate || candidate.admission !== "candidate-only"
      || candidate.providerAppId !== PIXELFORGE_CANDIDATE_PROVIDER_ID
      || candidate.source !== PIXELFORGE_CANDIDATE_SCHEMA
      || candidate.executionAuthority !== false) {
    throw new Error("Unadmitted PixelForge identity cannot be compared as a trusted project");
  }
  // Validate *all* candidate fields by round-tripping through the independent
  // candidate parser. An extra field can never become a registry permission.
  const id = candidate.projectRef.startsWith("project:")
    ? candidate.projectRef.slice("project:".length) : "";
  const validated = parsePixelForgeCandidateIdentity(JSON.stringify({
    schema: PIXELFORGE_CANDIDATE_SCHEMA,
    projectId: id,
    title: candidate.title,
    worldFormat: PIXELFORGE_CANDIDATE_WORLD_FORMAT,
  }));
  if (validated.projectRef !== candidate.projectRef ||
      !exactly(candidate as unknown as Record<string, unknown>, [
        "providerAppId", "projectRef", "title", "source",
        "admission", "executionAuthority",
      ])) throw new Error("Unreviewed candidate identity fields");
  const firstKey = providerQualifiedProjectKey("phioffice", office.projectRef);
  const secondKey = providerQualifiedProjectKey("pixelforge", validated.projectRef);
  return Object.freeze({
    sameTextRef: office.projectRef === validated.projectRef,
    differentProviderKey: firstKey !== secondKey,
    firstProvider: "phioffice" as const,
    secondProvider: "pixelforge" as const,
    firstKey, secondKey,
    v2Writes: 0 as const,
    bridgeRequests: 0 as const,
    authorityTransferred: false as const,
  });
}
