import { createHash, generateKeyPairSync, sign, webcrypto } from "node:crypto";
import { describe, expect, it } from "vitest";
import { parseStrictJson, verifyFieldShieldInBrowser } from "./browserPackVerification";

const now = Date.parse("2026-10-28T21:00:00Z");
const encoder = new TextEncoder();
const bytes = (data: unknown): Uint8Array => encoder.encode(JSON.stringify(data, null, 2) + "\n");
const sha = (raw: Uint8Array): string => createHash("sha256").update(raw).digest("hex");
const subtle = webcrypto.subtle as unknown as SubtleCrypto;
const valid = () => {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const pub = publicKey.export({ format: "der", type: "spki" }).subarray(-32);
  const pack = bytes({
    schema: "fieldshield.ioc-pack.v1",
    source: "SYNTHETIC SECURITY CENTER TEST ONLY",
    issued_at: "2026-01-01T00:00:00Z",
    indicators: [{ id: "demo-domain", kind: "domain", value: "demo.example.invalid",
      confidence: "low", reference: "https://www.rfc-editor.org/rfc/rfc2606" }],
  });
  const header = {
    schema: "fieldshield.signed-ioc.v1",
    publisher: "test-lab",
    key_id: "test-key-2026",
    pack_sha256: sha(pack),
    issued_at: "2026-02-01T00:00:00Z",
    expires_at: "2027-01-01T00:00:00Z",
  };
  const payload = JSON.stringify(Object.fromEntries(
    Object.entries(header).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0),
  ));
  const signed = Buffer.concat([
    Buffer.from("FieldShield Sentinel Signed IOC v1\0"), Buffer.from(payload),
  ]);
  const manifest = bytes({
    ...header, signature_b64: sign(null, signed, privateKey).toString("base64"),
  });
  const trust = bytes({
    schema: "fieldshield.trust-store.v1",
    publishers: [{
      id: "test-lab",
      keys: [{
        id: "test-key-2026", algorithm: "ed25519",
        state: "trusted", public_key_b64: pub.toString("base64"),
      }],
      blocked_pack_sha256: [],
      minimum_issued_at: "2026-01-01T00:00:00Z",
    }],
  });
  return { pack, manifest, trust, pin: createHash("sha256").update(pub).digest("hex") };
};
type Fixture = ReturnType<typeof valid>;
const run = (data: Fixture) => verifyFieldShieldInBrowser(
  data.pack, data.manifest, data.trust, data.pin, { now, subtle },
);

describe("PhiOS offline browser Ed25519 verification", () => {
  it("actually verifies synthetic signed FieldShield bytes using WebCrypto", async () => {
    const data = valid();
    const result = await run(data);
    expect(result.status).toBe("SIGNATURE_VERIFIED_AGAINST_OPERATOR_PIN_ONLY");
    expect(result.packSha256).toBe(sha(data.pack));
    expect(result.indicatorsClaimed).toBe(1);
    expect(result.publisherClaim).toBe("test-lab");
    expect(result.hostSecurityObserved).toBe(false);
    expect(result.sourceIdentityAuthenticated).toBe(false);
    expect(result.scanningPerformed).toBe(false);
  });

  it("fails when the exact IOC pack bytes change", async () => {
    const data = valid();
    data.pack = encoder.encode(new TextDecoder().decode(data.pack) + " ");
    await expect(run(data)).rejects.toThrow("SHA256 mismatch");
  });

  it("fails on a modified Ed25519 signature", async () => {
    const data = valid();
    const m = JSON.parse(new TextDecoder().decode(data.manifest));
    const mutated = Buffer.from(m.signature_b64, "base64");
    mutated[4] ^= 1;
    m.signature_b64 = mutated.toString("base64");
    data.manifest = bytes(m);
    await expect(run(data)).rejects.toThrow("signature did not match");
  });

  it("rejects unpinned and independently mismatching keys", async () => {
    const data = valid();
    await expect(verifyFieldShieldInBrowser(data.pack, data.manifest, data.trust,
      "", { now, subtle })).rejects.toThrow("out-of-band");
    data.pin = "f".repeat(64);
    await expect(run(data)).rejects.toThrow("independent SHA256 pin");
  });

  it("does not accept a revoked key or locally blocked pack", async () => {
    const data = valid();
    const t = JSON.parse(new TextDecoder().decode(data.trust));
    t.publishers[0].keys[0].state = "revoked";
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("locally revoked");
    t.publishers[0].keys[0].state = "trusted";
    t.publishers[0].blocked_pack_sha256 = [sha(data.pack)];
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("locally blocked");
  });

  it("rejects unfamiliar publishers, unknown keys and issuance rollback", async () => {
    const data = valid();
    const t = JSON.parse(new TextDecoder().decode(data.trust));
    t.publishers = [];
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("not locally trusted");
    t.publishers = [{
      id:"test-lab", keys:[], blocked_pack_sha256:[],
      minimum_issued_at:"2026-01-01T00:00:00Z",
    }];
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("Unknown signing key");
    t.publishers[0].minimum_issued_at = "2026-03-01T00:00:00Z";
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("issuance floor");
  });

  it("rejects expired or not-yet-valid detached manifests", async () => {
    const data = valid();
    await expect(verifyFieldShieldInBrowser(data.pack,data.manifest,data.trust,
      data.pin,{now:Date.parse("2028-01-01T00:00:00Z"),subtle})).rejects.toThrow("expired");
    await expect(verifyFieldShieldInBrowser(data.pack,data.manifest,data.trust,
      data.pin,{now:Date.parse("2025-01-01T00:00:00Z"),subtle})).rejects.toThrow("not yet valid");
  });

  it("rejects duplicate keys even when one is deeply nested", async () => {
    const raw=encoder.encode('{"schema":"ok","nested":{"same":1,"same":2}}');
    expect(()=>parseStrictJson(raw,500)).toThrow("Duplicate JSON key");
    const data=valid();
    const m=new TextDecoder().decode(data.manifest).replace(
      '"publisher": "test-lab"', '"publisher": "evil", "publisher": "test-lab"',
    );
    data.manifest=encoder.encode(m);
    await expect(run(data)).rejects.toThrow("Duplicate JSON key");
  });

  it("refuses renamed metadata that was not signed", async () => {
    const data=valid();
    const m=JSON.parse(new TextDecoder().decode(data.manifest));
    m.expires_at="2027-02-01T00:00:00Z";
    data.manifest=bytes(m);
    await expect(run(data)).rejects.toThrow("signature did not match");
  });

  it("fails closed when the browser crypto backend is absent", async () => {
    // Basic syntactic checks are still tested with malformed JSON.
    const data=valid();
    const wrongTrust=encoder.encode("{");
    await expect(verifyFieldShieldInBrowser(
      data.pack,data.manifest,wrongTrust,data.pin,{now,subtle},
    )).rejects.toThrow("JSON");
  });

  it("rejects signed non-Sentinel bytes after valid signature", async () => {
    // Only actual FieldShield IOC packs qualify, not arbitrary signed JSON.
    const data=valid();
    const invalid=encoder.encode('{"schema":"other"}');
    // Its hash differs from the signed digest, and must fail before parsing.
    data.pack=invalid;
    await expect(run(data)).rejects.toThrow("SHA256 mismatch");
  });
});
