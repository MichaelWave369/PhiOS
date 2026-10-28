import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SecurityCenter } from "../components/SecurityCenter";
import { MAX_SECURITY_RECEIPT_BYTES, parseSecurityReceipt } from "./receiptPreview";

const HASH = "a".repeat(64);

const phiark = () => ({
  checked: 2, passed: 1,
  results: [
    { id: HASH, status: "VERIFIED_NOW", publisher: "test-lab" },
    { id: "b".repeat(64), status: "FAIL", reason: "blocked" },
  ],
  note: "Synthetic only",
});

const sentinel = () => ({
  schema: "fieldshield.sentinel.v1",
  version: "0.1.0", mode: "observations",
  generated_at: "2026-10-28T13:00:00+00:00",
  counts: { inspected: 1, findings: 1, uninspected: 0 },
  decision: "INDICATORS_FOUND",
  findings: [{ indicator_id: "synthetic-dom", kind: "domain", location: { index: 0 } }],
  indicator_pack: { verification: { status: "ed25519-verified", publisher: "test-lab" } },
});

const offlineReview = () => ({
  schema: "phios.security_center.offline_pack_review.v0.2",
  status: "ED25519_VALID_UNDER_CALLER_SUPPLIED_PIN_NO_HOST_SCAN",
  reviewed_at: "2026-10-28T18:00:00+00:00",
  pack_sha256: "1".repeat(64),
  external_pinned_key_sha256: "2".repeat(64),
  publisher_claim: "synthetic-lab",
  manifest_expires_at: "2027-01-01T00:00:00+00:00",
  indicators_claimed: 2,
  signature_valid_for_pinned_key: true,
  external_key_pin_independently_authenticated_by_phios: false,
  publisher_real_world_identity_authenticated: false,
  indicator_accuracy_verified: false,
  host_security_observed: false,
  scan_performed: false,
  network_access_performed: false,
  launch_authority: false,
  gateway_authority: false,
  effects_performed: [],
});

describe("PhiOS Security Center", () => {
  it("previews only a claimed, historical offline cryptographic review", () => {
    const view = parseSecurityReceipt("phios-review", JSON.stringify(offlineReview()));
    expect(view.kind).toBe("phios-review");
    if (view.kind !== "phios-review") throw new Error("wrong receipt kind");
    expect(view.label).toContain("NOT REVERIFIED");
    expect(view.packSha256).toBe("1".repeat(64));
    expect(view.indicatorCount).toBe(2);
    const html = renderToStaticMarkup(<SecurityCenter />);
    expect(html).toContain("Import PhiOS offline review JSON");
    expect(html).toContain("HOST SECURITY STATUS: NOT OBSERVED");
  });

  it("rejects forged authority in a historical cryptographic review", () => {
    const fake = offlineReview();
    fake.host_security_observed = true;
    expect(() => parseSecurityReceipt("phios-review", JSON.stringify(fake)))
      .toThrow("offline signed-pack review");
    fake.host_security_observed = false;
    fake.external_pinned_key_sha256 = "unverified";
    expect(() => parseSecurityReceipt("phios-review", JSON.stringify(fake)))
      .toThrow("offline signed-pack review");
  });


  it("is a read-only desktop panel with no scan or live-verification controls", () => {
    const html = renderToStaticMarkup(<SecurityCenter />);
    expect(html).toContain("HOST SECURITY STATUS: NOT OBSERVED");
    expect(html).toContain("No local PhiARK receipt selected");
    expect(html).toContain("No local Sentinel report selected");
    expect(html).toContain("NOT");
    expect(html).toContain("Import PhiARK intelligence verification JSON");
    expect(html).toContain("Import Sentinel scan report JSON");
    expect(html).not.toContain("Start scan");
    expect(html).not.toContain("All clear");
  });

  it("displays only a historical PhiARK claim, not live proof", () => {
    const view = parseSecurityReceipt("phiark", JSON.stringify(phiark()));
    expect(view.kind).toBe("phiark");
    if (view.kind !== "phiark") throw new Error("expected PhiARK");
    expect(view.claimedVerified).toBe(1);
    expect(view.failed).toBe(1);
    expect(view.label).toContain("NOT LIVE VERIFIED");
    expect(view.publisherNames).toEqual(["test-lab"]);
  });

  it("rejects impossible PhiARK totals and malformed rows", () => {
    const modified = phiark();
    modified.passed = 2;
    expect(() => parseSecurityReceipt("phiark", JSON.stringify(modified)))
      .toThrow("contradicts");
    modified.passed = 1;
    modified.results[0].id = "not-a-digest";
    expect(() => parseSecurityReceipt("phiark", JSON.stringify(modified)))
      .toThrow("unsupported shape");
  });

  it("shows Sentinel reports as imported claims, not infection verdicts", () => {
    const view = parseSecurityReceipt("sentinel", JSON.stringify(sentinel()));
    expect(view.kind).toBe("sentinel");
    if (view.kind !== "sentinel") throw new Error("expected Sentinel");
    expect(view.decision).toBe("INDICATORS_FOUND");
    expect(view.findings).toBe(1);
    expect(view.indicatorIds).toEqual(["synthetic-dom"]);
    expect(view.packClaim).toContain("NOT REVERIFIED");
  });

  it("rejects mismatching scan finding counts and unrecognized schemas", () => {
    const invalid = sentinel();
    invalid.counts.findings = 0;
    expect(() => parseSecurityReceipt("sentinel", JSON.stringify(invalid)))
      .toThrow("FieldShield Sentinel");
    invalid.counts.findings = 1;
    invalid.schema = "forged-v99";
    expect(() => parseSecurityReceipt("sentinel", JSON.stringify(invalid)))
      .toThrow("FieldShield Sentinel");
  });

  it("rejects oversized, malformed, or non-JSON inputs", () => {
    expect(() => parseSecurityReceipt("phiark", "x".repeat(MAX_SECURITY_RECEIPT_BYTES + 1)))
      .toThrow("1 MiB");
    expect(() => parseSecurityReceipt("phiark", "{"))
      .toThrow("valid JSON");
    expect(() => parseSecurityReceipt("sentinel", "[]"))
      .toThrow("JSON object");
  });

  it("does not copy raw observation or path contents into the preview model", () => {
    const data = sentinel();
    data.findings[0].location = { index: 0, path: "/secret/raw/device/path" } as unknown as { index: number };
    const view = parseSecurityReceipt("sentinel", JSON.stringify(data));
    expect(JSON.stringify(view)).not.toContain("/secret/raw/device/path");
  });
});
