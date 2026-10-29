import { describe, expect, it } from "vitest";
import corpus from "./fixtures/fieldshield-strict-json-parity.v1.json";
import { parseStrictJson } from "./browserPackVerification";
import { verifyAndMatchSelectedObservations } from "./browserObservationMatch";

const encoder = new TextEncoder();
const raw = (value: string) => encoder.encode(value);
const buffer = (value: Uint8Array): ArrayBuffer => {
  const out = new ArrayBuffer(value.byteLength);
  new Uint8Array(out).set(value);
  return out;
};
const sha = async (data: Uint8Array) =>
  Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer(data))),
    b => b.toString(16).padStart(2, "0")).join("");
const b64 = (value: Uint8Array) =>
  btoa(Array.from(value, b => String.fromCharCode(b)).join(""));

describe("shared FieldShield/PhiOS strict JSON parsing v1", () => {
  it("has the same versioned golden contract as the Python tests", () => {
    expect(corpus.schema).toBe("fieldshield.phios.strict-json-parity.v1");
    expect(corpus.maxNestingDepth).toBe(48);
    expect(corpus.accepted).toHaveLength(6);
    expect(corpus.rejected).toHaveLength(23);
  });

  for (const vector of corpus.accepted) {
    it("accepts precise JSON: " + vector.id, () => {
      expect(parseStrictJson(raw(vector.raw), 4_096)).toBeTypeOf("object");
    });
  }

  for (const vector of corpus.rejected) {
    it("rejects ambiguous JSON: " + vector.id, () => {
      expect(() => parseStrictJson(raw(vector.raw), 4_096)).toThrow();
    });
  }

  it("refuses invalid UTF-8 before JSON interpretation", () => {
    expect(() => parseStrictJson(
      Uint8Array.from([123,34,97,34,58,34,255,34,125]), 100,
    )).toThrow("UTF-8");
  });

  it("does not leak duplicate property names into its error message", () => {
    const text = '{"private-forensic-path":1,"private-forensic-path":2}';
    let message = "";
    try { parseStrictJson(raw(text), 500); }
    catch (error) { message = String(error); }
    expect(message).toContain("Duplicate JSON key");
    expect(message).not.toContain("private-forensic-path");
  });

  it("refuses duplicate evidence properties after a freshly verified pack", async () => {
    const keyPair = await crypto.subtle.generateKey(
      {name:"Ed25519"}, true, ["sign","verify"],
    ) as CryptoKeyPair;
    const publicKey = new Uint8Array(
      await crypto.subtle.exportKey("raw", keyPair.publicKey),
    );
    const packRaw = raw(JSON.stringify({
      schema:"fieldshield.ioc-pack.v1",
      source:"synthetic strict-json test",
      issued_at:"2026-01-01T00:00:00Z",
      indicators:[{
        id:"demo",kind:"domain",value:"demo.example.invalid",
        confidence:"low",reference:"https://www.rfc-editor.org/rfc/rfc2606",
      }],
    }));
    const header = {
      schema:"fieldshield.signed-ioc.v1",publisher:"test-only",
      key_id:"ephemeral-key",pack_sha256:await sha(packRaw),
      issued_at:"2026-02-01T00:00:00Z",expires_at:"2027-01-01T00:00:00Z",
    };
    const sorted = JSON.stringify(Object.fromEntries(
      Object.entries(header).sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0),
    ));
    const domain = raw("FieldShield Sentinel Signed IOC v1\0");
    const canonical = raw(sorted);
    const payload = new Uint8Array(domain.length + canonical.length);
    payload.set(domain); payload.set(canonical, domain.length);
    const signature = new Uint8Array(
      await crypto.subtle.sign({name:"Ed25519"},keyPair.privateKey,buffer(payload)),
    );
    const manifestRaw = raw(JSON.stringify({
      ...header,signature_b64:b64(signature),
    }));
    const trustRaw = raw(JSON.stringify({
      schema:"fieldshield.trust-store.v1",
      publishers:[{
        id:"test-only",keys:[{
          id:"ephemeral-key",algorithm:"ed25519",state:"trusted",
          public_key_b64:b64(publicKey),
        }],
        blocked_pack_sha256:[],
        minimum_issued_at:"2026-01-01T00:00:00Z",
      }],
    }));
    const observationsRaw = raw(
      '{"schema":"fieldshield.observations.v1","observations":['+
      '{"kind":"domain","value":"demo.example.invalid",'+
      '"value":"other.example.invalid"}]}',
    );
    await expect(verifyAndMatchSelectedObservations({
      packRaw,manifestRaw,trustRaw,observationsRaw,
      independentPublicKeySha256:await sha(publicKey),
      now:Date.parse("2026-10-28T20:00:00Z"),
      subtle:crypto.subtle,
    })).rejects.toThrow("Duplicate JSON key");
  });
});
