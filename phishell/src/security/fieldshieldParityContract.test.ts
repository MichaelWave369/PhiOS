import { beforeAll, describe, expect, it } from "vitest";
import fixture from "./fixtures/fieldshield-observation-parity.v1.json";
import { verifyAndMatchSelectedObservations } from "./browserObservationMatch";

const encoder = new TextEncoder();
const bytes = (data: unknown): Uint8Array =>
  encoder.encode(JSON.stringify(data));
const owned = (input: Uint8Array): ArrayBuffer => {
  const output = new ArrayBuffer(input.byteLength);
  new Uint8Array(output).set(input);
  return output;
};
const hex = (input: Uint8Array) =>
  Array.from(input, b => b.toString(16).padStart(2, "0")).join("");
const digest = async (input: Uint8Array) =>
  hex(new Uint8Array(await crypto.subtle.digest("SHA-256", owned(input))));
const base64 = (input: Uint8Array) =>
  btoa(Array.from(input, b => String.fromCharCode(b)).join(""));
const NOW = Date.parse("2026-10-28T20:00:00Z");

async function signedContract() {
  const key = await crypto.subtle.generateKey(
    {name:"Ed25519"}, true, ["sign","verify"],
  ) as CryptoKeyPair;
  const publicBytes = new Uint8Array(
    await crypto.subtle.exportKey("raw", key.publicKey),
  );
  const packRaw = bytes(fixture.pack);
  const header = {
    schema:"fieldshield.signed-ioc.v1",
    publisher:"synthetic-parity-lab",
    key_id:"ephemeral-parity-test",
    pack_sha256:await digest(packRaw),
    issued_at:"2026-02-01T00:00:00Z",
    expires_at:"2027-01-01T00:00:00Z",
  };
  const sorted = Object.fromEntries(
    Object.entries(header).sort(([a],[b])=>a<b?-1:a>b?1:0),
  );
  const prefix = encoder.encode("FieldShield Sentinel Signed IOC v1\0");
  const content = encoder.encode(JSON.stringify(sorted));
  const signedMessage = new Uint8Array(prefix.length + content.length);
  signedMessage.set(prefix);
  signedMessage.set(content, prefix.length);
  const signature = new Uint8Array(await crypto.subtle.sign(
    {name:"Ed25519"}, key.privateKey, owned(signedMessage),
  ));
  const manifestRaw = bytes({...header,signature_b64:base64(signature)});
  const trustRaw = bytes({
    schema:"fieldshield.trust-store.v1",
    publishers:[{
      id:"synthetic-parity-lab",
      keys:[{
        id:"ephemeral-parity-test",
        algorithm:"ed25519",
        state:"trusted",
        public_key_b64:base64(publicBytes),
      }],
      blocked_pack_sha256:[],
      minimum_issued_at:"2026-01-01T00:00:00Z",
    }],
  });
  return {
    packRaw, manifestRaw, trustRaw,
    independentPublicKeySha256:await digest(publicBytes),
    now:NOW, subtle:crypto.subtle,
  };
}
type SignedContract = Awaited<ReturnType<typeof signedContract>>;

describe("FieldShield ↔ PhiOS shared observation parity contract v1", () => {
  let signed: SignedContract;
  beforeAll(async () => {signed=await signedContract();});

  it("checks the locked golden vector schema and case set", () => {
    expect(fixture.schema).toBe("fieldshield.phios.observations-parity.v1");
    expect(fixture.cases).toHaveLength(7);
    expect(fixture.pack.indicators).toHaveLength(7);
  });

  for (const scenario of fixture.cases) {
    it("matches Python Sentinel golden vector: " + scenario.id, async () => {
      const observedRaw = bytes({
        schema:"fieldshield.observations.v1",
        observations:scenario.observations,
      });
      const actual = await verifyAndMatchSelectedObservations({
        ...signed, observationsRaw:observedRaw,
      });
      const expected = scenario.expected;
      expect({
        decision:actual.decision,
        inspected:actual.inspected,
        uninspected:actual.uninspected,
        findings:actual.findingIds.map(item => ({
          indicatorId:item.indicatorId,
          kind:item.kind,
          observationIndex:item.observationIndex,
        })),
      }).toEqual(expected);
      expect(actual.observationsSupplied).toBe(scenario.observations.length);
      expect(actual.matches).toBe(expected.findings.length);
      expect(actual.verifiedPackSha256).toBe(await digest(signed.packRaw));
      expect(actual.observationFileSha256).toBe(await digest(observedRaw));
      expect(actual.hostSecurityObserved).toBe(false);
      expect(actual.hostScanPerformed).toBe(false);
      expect(actual.networkUsed).toBe(false);
      expect(actual.evidenceValuesIncluded).toBe(false);
      expect(actual.scope).toBe("USER_SELECTED_JSON_ONLY");
    });
  }

  it("never copies a private URL query value into the report", async () => {
    const scenario = fixture.cases.find(
      c=>c.id==="url-hostname-exact-fallback-without-raw-value",
    );
    if (!scenario) throw new Error("Required privacy vector absent");
    const report = await verifyAndMatchSelectedObservations({
      ...signed,
      observationsRaw:bytes({
        schema:"fieldshield.observations.v1",observations:scenario.observations,
      }),
    });
    expect(JSON.stringify(report)).not.toContain("only-in-evidence");
    expect(report.findingIds[0].indicatorId).toBe("synthetic-extra-domain");
  });
});
