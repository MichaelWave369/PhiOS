/**
 * R9 operator-driven V1 -> V2 browser-local COPY and safe rollback.
 *
 * This is NOT a migration of the active registry: V1 and the existing
 * PhiOffice bridge remain authoritative for their own bounded UI semantics.
 * No permissions, cloud account, app files or identity claims are transferred.
 * localStorage has no cross-tab transaction/CAS; the code checks immediately
 * before a write/removal and refuses stale or conflicting views, but physical
 * atomicity across cooperating tabs is not claimed.
 */
import { PROJECT_REGISTRY_KEY } from "./projectRegistry";
import {
  PROJECT_REGISTRY_V2_KEY,
  decodeProjectRegistryV2,
  encodeProjectRegistryV2,
  previewV1ToV2Migration,
  type ProviderQualifiedProjectReference,
  type V2MigrationPreview,
} from "./projectRegistryV2";

export type ProjectRegistryStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export type ProviderV2CopyPlan = Readonly<{
  expectedV1Raw: string;
  plannedV2Raw: string;
  preview: V2MigrationPreview;
}>;

export type ProviderV2RollbackReview = Readonly<{
  expectedV2Raw: string;
  entries: readonly ProviderQualifiedProjectReference[];
  recordCount: number;
}>;

function requiredSourceMatch(storage: ProjectRegistryStorage, targetV2Raw: string): void {
  const v1Raw = storage.getItem(PROJECT_REGISTRY_KEY);
  if (v1Raw === null) {
    throw new Error("V1 registry is missing; refusing to remove the only saved identity copy");
  }
  const preview = previewV1ToV2Migration(v1Raw, null);
  if (preview.recordCount === 0 || encodeProjectRegistryV2(preview.entries) !== targetV2Raw) {
    throw new Error("V1 and V2 project references differ; rollback requires independent review");
  }
}

/** Read-only preparation; no storage writes and no approval. */
export function prepareProviderV2Copy(storage: ProjectRegistryStorage): ProviderV2CopyPlan {
  const v1Raw = storage.getItem(PROJECT_REGISTRY_KEY);
  if (v1Raw === null) {
    throw new Error("No V1 project registry is saved; nothing to copy");
  }
  const preview = previewV1ToV2Migration(v1Raw, storage.getItem(PROJECT_REGISTRY_V2_KEY));
  if (preview.recordCount === 0) {
    throw new Error("No saved V1 project references to copy");
  }
  return Object.freeze({
    expectedV1Raw: v1Raw,
    plannedV2Raw: encodeProjectRegistryV2(preview.entries),
    preview,
  });
}

/**
 * Operator must explicitly approve from the UI. Check the exact preview
 * against current V1 and destination immediately before one V2 setItem.
 * Never writes, deletes or rewrites V1. Read-back is an API check, NOT a
 * browser persistence/disk durability guarantee.
 */
export function commitProviderV2Copy(
  storage: ProjectRegistryStorage, plan: ProviderV2CopyPlan, confirmed: boolean,
): number {
  if (confirmed !== true) {
    throw new Error("Explicit operator confirmation is required to create V2 copy");
  }
  if (!plan || typeof plan.expectedV1Raw !== "string" ||
      typeof plan.plannedV2Raw !== "string") {
    throw new Error("Invalid V2 copy plan");
  }
  const verified = previewV1ToV2Migration(plan.expectedV1Raw, null);
  if (verified.recordCount === 0 ||
      encodeProjectRegistryV2(verified.entries) !== plan.plannedV2Raw) {
    throw new Error("V2 copy plan failed source validation");
  }
  if (storage.getItem(PROJECT_REGISTRY_KEY) !== plan.expectedV1Raw) {
    throw new Error("V1 registry changed since preview; review again before copying");
  }
  if (storage.getItem(PROJECT_REGISTRY_V2_KEY) !== null) {
    throw new Error("V2 target already exists; refusing overwrite");
  }

  storage.setItem(PROJECT_REGISTRY_V2_KEY, plan.plannedV2Raw);
  if (storage.getItem(PROJECT_REGISTRY_V2_KEY) !== plan.plannedV2Raw) {
    throw new Error("V2 storage read-back mismatch; review storage before retrying");
  }
  return verified.recordCount;
}

/** Read-only rollback inspection; refuse if the V1 copy is missing or differs. */
export function inspectProviderV2Rollback(
  storage: ProjectRegistryStorage,
): ProviderV2RollbackReview {
  const currentV2 = storage.getItem(PROJECT_REGISTRY_V2_KEY);
  if (currentV2 === null) throw new Error("No V2 project registry copy exists");
  const entries = decodeProjectRegistryV2(currentV2);
  requiredSourceMatch(storage, currentV2);
  return Object.freeze({
    expectedV2Raw: currentV2,
    entries: Object.freeze(entries),
    recordCount: entries.length,
  });
}

/**
 * Explicit operator rollback only after reviewing exact V2 bytes. Deletes
 * the verified V2 COPY, never V1. Any change after review prevents removal.
 */
export function rollbackProviderV2Copy(
  storage: ProjectRegistryStorage,
  review: ProviderV2RollbackReview,
  confirmed: boolean,
): void {
  if (confirmed !== true) {
    throw new Error("Explicit operator confirmation is required to remove V2 copy");
  }
  if (!review || typeof review.expectedV2Raw !== "string" ||
      !Array.isArray(review.entries)) {
    throw new Error("Invalid V2 rollback review");
  }
  const valid = decodeProjectRegistryV2(review.expectedV2Raw);
  if (review.recordCount !== valid.length ||
      JSON.stringify(valid) !== JSON.stringify(review.entries)) {
    throw new Error("V2 rollback review no longer matches validated project identities");
  }
  if (storage.getItem(PROJECT_REGISTRY_V2_KEY) !== review.expectedV2Raw) {
    throw new Error("V2 registry changed since review; refusing deletion");
  }
  requiredSourceMatch(storage, review.expectedV2Raw);
  storage.removeItem(PROJECT_REGISTRY_V2_KEY);
  if (storage.getItem(PROJECT_REGISTRY_V2_KEY) !== null) {
    throw new Error("V2 removal could not be verified; review current storage");
  }
}
