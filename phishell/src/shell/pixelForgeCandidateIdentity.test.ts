import { describe, expect, it } from "vitest";
import {
  PIXELFORGE_CANDIDATE_MAX_BYTES,
  PIXELFORGE_CANDIDATE_PROVIDER_ID,
  PIXELFORGE_CANDIDATE_SCHEMA,
  PIXELFORGE_CANDIDATE_WORLD_FORMAT,
  PIXELFORGE_CANDIDATE_PRODUCER_SHA,
  compareCandidateIdentityWithPhiOffice,
  parsePixelForgeCandidateIdentity,
} from "./pixelForgeCandidateIdentity";
import { PHIOFFICE_MANIFEST_SOURCE, encodeProjectRegistry } from "./projectRegistry";
import { findProjectAdapterForTarget, findReviewedProjectAdapter } from "./projectAdapters";
import {
  encodeProjectRegistryV2,
  providerQualifiedProjectKey,
  validateQualifiedProjectEntry,
  type ProviderQualifiedProjectReference,
} from "./projectRegistryV2";
import { readProjectIdentityWithAdapter } from "./projectAdapterReader";

const valid = {
  schema: PIXELFORGE_CANDIDATE_SCHEMA,
  projectId: "same-project",
  title: "Shared Display Title",
  worldFormat: PIXELFORGE_CANDIDATE_WORLD_FORMAT,
};
const office = validateQualifiedProjectEntry({
  providerAppId: "phioffice",
  projectRef: "project:same-project",
  title: "Shared Display Title",
  source: PHIOFFICE_MANIFEST_SOURCE,
});
const parse = (value: unknown) => parsePixelForgeCandidateIdentity(JSON.stringify(value));

describe("PhiOS R10 quarantined PixelForge identity producer contract", () => {
  it("mirrors the exact pinned, reviewed candidate sidecar, with no ambient authority", () => {
    expect(PIXELFORGE_CANDIDATE_PRODUCER_SHA)
      .toBe("b74802b358e9c23bc520ef3c0a46699498186c51");
    const identity = parse(valid);
    expect(identity).toEqual({
      providerAppId: PIXELFORGE_CANDIDATE_PROVIDER_ID,
      projectRef: "project:same-project",
      title: valid.title,
      source: PIXELFORGE_CANDIDATE_SCHEMA,
      admission: "candidate-only",
      executionAuthority: false,
    });
    expect(Object.isFrozen(identity)).toBe(true);
    expect(JSON.stringify(identity)).not.toMatch(/worldFormat|assets|objects|glb|credentials|grant/i);
  });

  it("same text project ID across providers cannot produce a shared registry key", () => {
    const candidate = parse(valid);
    const result = compareCandidateIdentityWithPhiOffice(office, candidate);
    expect(result.sameTextRef).toBe(true);
    expect(result.differentProviderKey).toBe(true);
    expect(result.firstKey).toBe(providerQualifiedProjectKey("phioffice", "project:same-project"));
    expect(result.secondKey).toBe(providerQualifiedProjectKey("pixelforge", "project:same-project"));
    expect(result.firstKey).not.toBe(result.secondKey);
    expect(result.v2Writes).toBe(0);
    expect(result.bridgeRequests).toBe(0);
    expect(result.authorityTransferred).toBe(false);
  });

  it("PhiOffice V1 and V2 remain valid while an unadmitted PixelForge source is rejected", () => {
    const v1 = encodeProjectRegistry([{
      projectRef: office.projectRef,
      title: office.title,
      source: PHIOFFICE_MANIFEST_SOURCE,
    }]);
    const v2 = encodeProjectRegistryV2([office]);
    expect(JSON.parse(v1).version).toBe(1);
    expect(JSON.parse(v2).version).toBe(2);
    const candidate = parse(valid);
    expect(() => validateQualifiedProjectEntry({
      providerAppId: candidate.providerAppId,
      projectRef: candidate.projectRef,
      title: candidate.title,
      source: candidate.source,
    })).toThrow("Unreviewed project identity source");
    expect(() => encodeProjectRegistryV2([{
      providerAppId: candidate.providerAppId,
      projectRef: candidate.projectRef,
      title: candidate.title,
      source: candidate.source,
    } as unknown as ProviderQualifiedProjectReference])).toThrow("Unreviewed");
    expect(findReviewedProjectAdapter(PIXELFORGE_CANDIDATE_SCHEMA)).toBeNull();
    expect(findProjectAdapterForTarget(PIXELFORGE_CANDIDATE_SCHEMA, "phioffice")).toBeNull();
    expect(findProjectAdapterForTarget(PIXELFORGE_CANDIDATE_SCHEMA, "pixelforge")).toBeNull();
    expect(() => readProjectIdentityWithAdapter("pixelforge-world-v1", JSON.stringify(valid)))
      .toThrow("not reviewed");
  });

  it("accepts only four fields, exact producer schema and known world format", () => {
    for (const invalid of [
      { ...valid, schema: "phioffice369.project_manifest.v0.1" },
      { ...valid, schema: "pixelforge.phios-vr-world-identity.v0.2" },
      { ...valid, worldFormat: "pixelforge.v6.demo-world.v1" },
      { ...valid, grant: "read-all" },
      { ...valid, executionAuthority: true },
      { ...valid, assetId: "ASSET-000001" },
      { ...valid, privatePath: "/home/operator/world.json" },
      { ...valid, title: "secret\nword" },
      { ...valid, title: "\u202Edirection spoof" },
      { ...valid, title: " padded " },
      { ...valid, title: "" },
      { ...valid, title: "a".repeat(101) },
    ]) expect(() => parse(invalid)).toThrow();
  });

  it("refuses path-like, malformed, oversized, or non-ASCII IDs", () => {
    for (const projectId of [
      "", "project:already-prefixed", "../../secret", "../", "bad..id", "bad.",
      "white space", "glück", "_starts_underscore", "abc/def", "abc\\def",
      "a".repeat(65),
    ]) expect(() => parse({ ...valid, projectId })).toThrow("project ID");
    for (const projectId of ["a", "A-1_B", "a.b-c", "0".repeat(64)]) {
      expect(parse({ ...valid, projectId }).projectRef).toBe("project:" + projectId);
    }
    expect(() => parsePixelForgeCandidateIdentity("{")).toThrow("not valid JSON");
    expect(() => parsePixelForgeCandidateIdentity(" ".repeat(PIXELFORGE_CANDIDATE_MAX_BYTES + 1)))
      .toThrow("4 KiB");
    expect(() => parse([])).toThrow();
    expect(() => parse(null)).toThrow();
  });

  it("cannot compare forged candidate metadata with existing PhiOffice identities", () => {
    const candidate = parse(valid);
    for (const forgery of [
      { ...candidate, admission: "reviewed-browser-pilot" },
      { ...candidate, executionAuthority: true },
      { ...candidate, providerAppId: "phioffice" },
      { ...candidate, source: PHIOFFICE_MANIFEST_SOURCE },
      { ...candidate, projectRef: "project:../secret" },
      { ...candidate, unexpectedGrant: true },
    ]) {
      expect(() => compareCandidateIdentityWithPhiOffice(
        office, forgery as typeof candidate)).toThrow();
    }
    expect(() => compareCandidateIdentityWithPhiOffice({
      ...office, providerAppId: "pixelforge",
    }, candidate)).toThrow("Provider/source mismatch");
  });
});
