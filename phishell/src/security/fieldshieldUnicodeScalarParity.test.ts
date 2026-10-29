import { describe, expect, it } from "vitest";
import fixtures from "./fixtures/fieldshield-unicode-scalar-parity.v1.json";
import { parseStrictJson } from "./browserPackVerification";
import { verifyAndMatchSelectedObservations } from "./browserObservationMatch";

const enc = new TextEncoder();
const bytes = (input: string): Uint8Array => enc.encode(input);
const owned = (input: Uint8Array): ArrayBuffer => {
  const buffer = new ArrayBuffer(input.byteLength);
  new Uint8Array(buffer).set(input);
  return buffer;
};
const hex = (raw: Uint8Array) =>
  Array.from(raw, value => value.toString(16).padStart(2, "0")).join("");
const digest = async (input: Uint8Array) =>
  hex(new Uint8Array(await crypto.subtle.digest("SHA-256", owned(input))));
const base64 = (input: Uint8Array) =>
  btoa(Array.from(input, value => String.fromCharCode(value)).join(""));

describe("FieldShield/PhiOS Unicode scalar JSON parity contract", () => {
  it("locks the same vector inventory as the Python engine", () => {
    expect(fixtures.schema).toBe("fieldshield.phios.unicode-scalar-parity.v1");
    expect(fixtures.accepted).toHaveLength(7);
    expect(fixtures.rejected).toHaveLength(12);
  });

  for (const sample of fixtures.accepted) {
    it("accepts valid Unicode: " + sample.id, () => {
      expect(parseStrictJson(bytes(sample.raw), 4096)).toBeTypeOf("object");
    });
  }

  for (const sample of fixtures.rejected) {
    it("rejects malformed Unicode: " + sample.id, () => {
      expect(() => parseStrictJson(bytes(sample.raw), 4096))
        .toThrow("Unpaired Unicode surrogate");
    });
  }

  it("refuses malformed Unicode in selected observations after pack verification", async () => {
    const keys = await crypto.subtle.generateKey(
      { name: "Ed25519" }, true, ["sign", "verify"],
    ) as CryptoKeyPair;
    const publicBytes = new Uint8Array(
      await crypto.subtle.exportKey("raw", keys.publicKey),
    );
    const packRaw = bytes(JSON.stringify({
      schema: "fieldshield.ioc-pack.v1",
      source: "SYNTHETIC Unicode acceptance test",
      issued_at: "2026-01-01T00:00:00Z",
      indicators: [{
        id: "demo", kind: "domain", value: "demo.example.invalid",
        confidence: "low", reference: "https://www.rfc-editor.org/rfc/rfc2606",
      }],
    }));
    const header = {
      schema: "fieldshield.signed-ioc.v1",
      publisher: "synthetic-unicode-parity",
      key_id: "ephemeral-key",
      pack_sha256: await digest(packRaw),
      issued_at: "2026-02-01T00:00:00Z",
      expires_at: "2027-01-01T00:00:00Z",
    };
    const serialized = JSON.stringify(Object.fromEntries(
      Object.entries(header).sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0),
    ));
    const domain = bytes("FieldShield Sentinel Signed IOC v1\0");
    const canonical = bytes(serialized);
    const signedBytes = new Uint8Array(domain.length + canonical.length);
    signedBytes.set(domain);
    signedBytes.set(canonical, domain.length);
    const signature = new Uint8Array(await crypto.subtle.sign(
      { name: "Ed25519" }, keys.privateKey, owned(signedBytes),
    ));
    const manifestRaw = bytes(JSON.stringify({
      ...header, signature_b64: base64(signature),
    }));
    const trustRaw = bytes(JSON.stringify({
      schema: "fieldshield.trust-store.v1",
      publishers: [{
        id: "synthetic-unicode-parity",
        minimum_issued_at: "2026-01-01T00:00:00Z",
        blocked_pack_sha256: [],
        keys: [{
          id: "ephemeral-key", algorithm: "ed25519", state: "trusted",
          public_key_b64: base64(publicBytes),
        }],
      }],
    }));
    const observationsRaw = bytes(
      '{"schema":"fieldshield.observations.v1","observations":[' +
      '{"kind":"process","value":"\\ud800"}]}',
    );
    await expect(verifyAndMatchSelectedObservations({
      packRaw, manifestRaw, trustRaw, observationsRaw,
      independentPublicKeySha256: await digest(publicBytes),
      subtle: crypto.subtle,
      now: Date.parse("2026-10-28T20:00:00Z"),
    })).rejects.toThrow("Unpaired Unicode surrogate");
  });
});
