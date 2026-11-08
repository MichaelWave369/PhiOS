/**
 * R11 explicit PixelForge identity-only V2 import/removal.
 * Every write is a user-confirmed replacement of V2 metadata bytes only.
 * No V1 upgrade, bridge grant, execution, file content or native app install.
 *
 * localStorage provides no cross-tab compare-and-swap; exact pre-write
 * checks narrow but do not eliminate simultaneous-tab races.
 */
import { PROJECT_REGISTRY_KEY, decodeProjectRegistry } from "./projectRegistry";
import {
  PROJECT_REGISTRY_V2_KEY,
  PIXELFORGE_V2_IDENTITY_SOURCE,
  PIXELFORGE_V2_PROVIDER,
  decodeProjectRegistryV2,
  encodeProjectRegistryV2,
  providerQualifiedProjectKey,
  validateQualifiedProjectEntry,
  type ProviderQualifiedProjectReference,
} from "./projectRegistryV2";
import { parsePixelForgeCandidateIdentity } from "./pixelForgeCandidateIdentity";
import type { ProjectRegistryStorage } from "./projectRegistryV2Copy";

export type PixelForgeV2ImportReview = Readonly<{
  existingV1Raw: string;
  existingV2Raw: string;
  plannedV2Raw: string;
  identity: ProviderQualifiedProjectReference;
  collisionWithPhiOfficeRef: boolean;
  resultCount: number;
}>;
export type PixelForgeV2RemovalReview = Readonly<{
  existingV1Raw: string;
  existingV2Raw: string;
  plannedV2Raw: string;
  identity: ProviderQualifiedProjectReference;
  resultCount: number;
}>;

function loadForEdit(storage: ProjectRegistryStorage) {
  const v1Raw = storage.getItem(PROJECT_REGISTRY_KEY);
  const v2Raw = storage.getItem(PROJECT_REGISTRY_V2_KEY);
  if (v1Raw === null || v2Raw === null) {
    throw new Error("Create the confirmed PhiOffice V2 metadata copy first; no registry initialized");
  }
  // Existing R9 source remains separately available and valid.
  const v1Entries = decodeProjectRegistry(v1Raw);
  const v2Entries = decodeProjectRegistryV2(v2Raw);
  if (v1Entries.length === 0 || !v2Entries.some((e) => e.providerAppId === "phioffice")) {
    throw new Error("Reviewed PhiOffice V1/V2 foundation is missing");
  }
  // Do NOT require exact R9 V1/V2 equality after the first PixelForge import.
  // Requiring original PhiOffice entries still present prevents replacing the
  // only older provider metadata during a malformed/partial V2 edit.
  const v2Office = new Map(v2Entries.filter((e) => e.providerAppId === "phioffice")
    .map((e) => [providerQualifiedProjectKey(e.providerAppId, e.projectRef), e] as const));
  if (v1Entries.some((entry) => {
    const id = providerQualifiedProjectKey("phioffice", entry.projectRef);
    const verified = v2Office.get(id);
    return !verified || verified.title !== entry.title || verified.source !== entry.source;
  })) {
    throw new Error("V2 no longer matches all saved PhiOffice V1 identities");
  }
  return { v1Raw, v2Raw, v1Entries, v2Entries };
}

function checkCurrent(storage: ProjectRegistryStorage, v1Raw: string, v2Raw: string) {
  if (storage.getItem(PROJECT_REGISTRY_KEY) !== v1Raw ||
      storage.getItem(PROJECT_REGISTRY_V2_KEY) !== v2Raw) {
    throw new Error("Project registry changed since review; inspect again before writing");
  }
}

function exactIdentity(a: ProviderQualifiedProjectReference, b: ProviderQualifiedProjectReference) {
  return a.providerAppId === b.providerAppId &&
    a.projectRef === b.projectRef && a.title === b.title && a.source === b.source;
}

/** Parse the real independent PixelForge producer output: never trust filename. */
export function previewPixelForgeV2Import(
  storage: ProjectRegistryStorage, manifestRaw: string,
): PixelForgeV2ImportReview {
  const parsed = parsePixelForgeCandidateIdentity(manifestRaw);
  if (parsed.admission !== "candidate-only" || parsed.executionAuthority !== false) {
    throw new Error("PixelForge identity import includes forbidden authority");
  }
  const candidate = validateQualifiedProjectEntry({
    providerAppId: parsed.providerAppId,
    projectRef: parsed.projectRef,
    title: parsed.title,
    source: parsed.source,
  });
  const { v1Raw, v2Raw, v2Entries } = loadForEdit(storage);
  const candidateKey = providerQualifiedProjectKey(candidate.providerAppId, candidate.projectRef);
  if (v2Entries.some((e) =>
      providerQualifiedProjectKey(e.providerAppId, e.projectRef) === candidateKey)) {
    throw new Error("PixelForge identity is already in V2; refusing implicit overwrite");
  }
  const plannedV2Raw = encodeProjectRegistryV2([...v2Entries, candidate]);
  return Object.freeze({
    existingV1Raw: v1Raw, existingV2Raw: v2Raw, plannedV2Raw,
    identity: candidate,
    collisionWithPhiOfficeRef: v2Entries.some((e) =>
      e.providerAppId === "phioffice" && e.projectRef === candidate.projectRef),
    resultCount: v2Entries.length + 1,
  });
}

export function confirmPixelForgeV2Import(
  storage: ProjectRegistryStorage, plan: PixelForgeV2ImportReview, approved: boolean,
): number {
  if (approved !== true) throw new Error("Explicit identity import approval required");
  if (!plan || typeof plan.existingV1Raw !== "string" ||
      typeof plan.existingV2Raw !== "string" || typeof plan.plannedV2Raw !== "string") {
    throw new Error("Invalid identity import review");
  }
  const previous = loadForEdit(storage);
  checkCurrent(storage, plan.existingV1Raw, plan.existingV2Raw);
  const expected = validateQualifiedProjectEntry(plan.identity);
  if (expected.providerAppId !== PIXELFORGE_V2_PROVIDER ||
      expected.source !== PIXELFORGE_V2_IDENTITY_SOURCE ||
      !plan.plannedV2Raw.endsWith("\n") ||
      plan.plannedV2Raw !== encodeProjectRegistryV2([...previous.v2Entries, expected]) ||
      plan.resultCount !== previous.v2Entries.length + 1) {
    throw new Error("Identity import review failed validation");
  }
  storage.setItem(PROJECT_REGISTRY_V2_KEY, plan.plannedV2Raw);
  if (storage.getItem(PROJECT_REGISTRY_V2_KEY) !== plan.plannedV2Raw) {
    throw new Error("PixelForge V2 read-back mismatch; inspect storage before retrying");
  }
  return plan.resultCount;
}

/** No deletion on discovery; output is an operator-reviewable removal plan. */
export function previewPixelForgeV2Removal(
  storage: ProjectRegistryStorage, projectRef: string,
): PixelForgeV2RemovalReview {
  const { v1Raw, v2Raw, v2Entries } = loadForEdit(storage);
  const candidate = v2Entries.find((e) =>
    e.providerAppId === PIXELFORGE_V2_PROVIDER && e.projectRef === projectRef);
  if (!candidate || candidate.source !== PIXELFORGE_V2_IDENTITY_SOURCE) {
    throw new Error("No reviewed PixelForge identity to remove");
  }
  const remaining = v2Entries.filter((e) =>
    providerQualifiedProjectKey(e.providerAppId, e.projectRef) !==
    providerQualifiedProjectKey(candidate.providerAppId, candidate.projectRef));
  const plannedV2Raw = encodeProjectRegistryV2(remaining);
  return Object.freeze({
    existingV1Raw: v1Raw,
    existingV2Raw: v2Raw,
    plannedV2Raw,
    identity: candidate,
    resultCount: remaining.length,
  });
}

export function confirmPixelForgeV2Removal(
  storage: ProjectRegistryStorage, plan: PixelForgeV2RemovalReview, approved: boolean,
): number {
  if (approved !== true) throw new Error("Explicit PixelForge identity removal approval required");
  if (!plan || typeof plan.existingV1Raw !== "string" ||
      typeof plan.existingV2Raw !== "string" || typeof plan.plannedV2Raw !== "string") {
    throw new Error("Invalid identity removal review");
  }
  const current = loadForEdit(storage);
  checkCurrent(storage, plan.existingV1Raw, plan.existingV2Raw);
  const candidate = validateQualifiedProjectEntry(plan.identity);
  if (candidate.providerAppId !== PIXELFORGE_V2_PROVIDER ||
      candidate.source !== PIXELFORGE_V2_IDENTITY_SOURCE) {
    throw new Error("Unreviewed identity cannot be removed via PixelForge control");
  }
  const removed = current.v2Entries.filter((e) => exactIdentity(e, candidate));
  const remaining = current.v2Entries.filter((e) => !exactIdentity(e, candidate));
  if (removed.length !== 1 ||
      plan.plannedV2Raw !== encodeProjectRegistryV2(remaining) ||
      plan.resultCount !== remaining.length) {
    throw new Error("Identity removal review no longer matches current V2");
  }
  storage.setItem(PROJECT_REGISTRY_V2_KEY, plan.plannedV2Raw);
  if (storage.getItem(PROJECT_REGISTRY_V2_KEY) !== plan.plannedV2Raw) {
    throw new Error("PixelForge V2 removal read-back mismatch; inspect storage");
  }
  return remaining.length;
}

export function inspectPixelForgeV2Identities(
  storage: ProjectRegistryStorage,
): readonly ProviderQualifiedProjectReference[] {
  const { v2Entries } = loadForEdit(storage);
  return Object.freeze(v2Entries.filter((e) => e.providerAppId === PIXELFORGE_V2_PROVIDER));
}
