/**
 * Reviewed adapter input dispatcher for project ID metadata only.
 * Never executes imported adapter code or trusts descriptors in user JSON.
 */
import { extractProjectReference } from "./projectManifestSelection";
import {
  PHIOFFICE_PROJECT_ADAPTER_ID,
  findReviewedProjectAdapterById,
} from "./projectAdapters";
import type { SavedProjectReference } from "./projectRegistry";

export function readProjectIdentityWithAdapter(
  adapterId: string, json: string,
): SavedProjectReference {
  const adapter = findReviewedProjectAdapterById(adapterId);
  if (!adapter) throw new Error("Project adapter is not reviewed in this PhiOS build");
  // Explicit source-code dispatch. External JSON cannot add a parser, app or
  // capability merely by claiming a source, version or status.
  if (adapter.id === PHIOFFICE_PROJECT_ADAPTER_ID) {
    const projected = extractProjectReference(json);
    return Object.freeze({ ...projected, source: adapter.source });
  }
  throw new Error("Reviewed adapter has no project identity reader");
}
