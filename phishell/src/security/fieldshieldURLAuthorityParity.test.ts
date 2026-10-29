import { describe, expect, it } from "vitest";
import corpus from "./fixtures/fieldshield-url-authority-parity.v1.json";
import {
  normalizeFieldShield, safeFieldShieldUrlHostname,
  verifyAndMatchSelectedObservations,
} from "./browserObservationMatch";

const enc = new TextEncoder();
const bytes = (v: unknown) => enc.encode(JSON.stringify(v));
const toBuffer = (raw: Uint8Array): ArrayBuffer => {
  const result = new ArrayBuffer(raw.length);
  new Uint8Array(result).set(raw);
  return result;
};
const hex = (raw: Uint8Array) => Array.from(raw, n => n.toString(16).padStart(2, "0")).join("");
const hash = async (raw: Uint8Array) => hex(new Uint8Array(
  await crypto.subtle.digest("SHA-256", toBuffer(raw)),
));
const b64 = (raw: Uint8Array) => btoa(Array.from(raw, x => String.fromCharCode(x)).join(""));

describe("FieldShield/PhiOS cross-runtime safe URL authority profile v1", () => {
  it("uses the same versioned test corpus as Python", () => {
    expect(corpus.schema).toBe("fieldshield.phios.url-authority-parity.v1");
    expect(corpus.accepted).toHaveLength(9);
    expect(corpus.rejected).toHaveLength(18);
  });

  for (const scenario of corpus.accepted) {
    it("accepts the stable host " + scenario.value, () => {
      expect(normalizeFieldShield("url",scenario.value)).toBe(scenario.value);
      expect(safeFieldShieldUrlHostname(scenario.value)).toBe(scenario.hostname);
    });
  }

  for (const scenario of corpus.rejected) {
    it("rejects parser ambiguity: " + scenario.why, () => {
      expect(() => normalizeFieldShield("url", scenario.value)).toThrow();
    });
  }

  it("does not accidentally report normalized hostile URL evidence as a hit", async () => {
    const pair = await crypto.subtle.generateKey(
      {name:"Ed25519"}, true, ["sign","verify"],
    ) as CryptoKeyPair;
    const publicKey = new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey));
    const packRaw = bytes({
      schema:"fieldshield.ioc-pack.v1",
      issued_at:"2026-01-01T00:00:00Z",
      source:"synthetic URL regression only",
      indicators:[{
        id:"valid-host",kind:"domain",value:"example.invalid",
        confidence:"low",reference:"https://www.rfc-editor.org/rfc/rfc2606",
      }],
    });
    const header = {
      schema:"fieldshield.signed-ioc.v1",
      publisher:"parity-url-fixture",key_id:"key-1",
      pack_sha256:await hash(packRaw),
      issued_at:"2026-02-01T00:00:00Z",expires_at:"2027-01-01T00:00:00Z",
    };
    const sorted = JSON.stringify(Object.fromEntries(
      Object.entries(header).sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0),
    ));
    const prefix = enc.encode("FieldShield Sentinel Signed IOC v1\0");
    const text = enc.encode(sorted);
    const payload = new Uint8Array(prefix.length + text.length);
    payload.set(prefix); payload.set(text,prefix.length);
    const signature = new Uint8Array(
      await crypto.subtle.sign({name:"Ed25519"},pair.privateKey,toBuffer(payload)),
    );
    const manifestRaw = bytes({...header,signature_b64:b64(signature)});
    const trustRaw = bytes({
      schema:"fieldshield.trust-store.v1",
      publishers:[{
        id:"parity-url-fixture",
        keys:[{
          id:"key-1",algorithm:"ed25519",state:"trusted",public_key_b64:b64(publicKey),
        }],
        blocked_pack_sha256:[],
        minimum_issued_at:"2026-01-01T00:00:00Z",
      }],
    });
    const observationsRaw = bytes({
      schema:"fieldshield.observations.v1",
      observations:[
        {kind:"url",value:"https://ex%61mple.invalid/private"},
        {kind:"domain",value:"unrelated.example.invalid"},
      ],
    });
    const result = await verifyAndMatchSelectedObservations({
      packRaw,manifestRaw,trustRaw,observationsRaw,
      independentPublicKeySha256:await hash(publicKey),
      now:Date.parse("2026-10-28T20:00:00Z"),
      subtle:crypto.subtle,
    });
    expect(result.inspected).toBe(1);
    expect(result.uninspected).toBe(1);
    expect(result.matches).toBe(0);
    expect(result.decision).toBe("INCOMPLETE");
    expect(JSON.stringify(result)).not.toContain("ex%61mple");
  });
});
