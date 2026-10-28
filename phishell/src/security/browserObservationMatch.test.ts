import { describe, expect, it } from "vitest";
import {
  OBSERVATION_LIMIT, normalizeFieldShield, verifyAndMatchSelectedObservations,
} from "./browserObservationMatch";
import { parseStrictJson } from "./browserPackVerification";

const enc = new TextEncoder();
const bytes = (x: unknown) => enc.encode(JSON.stringify(x));
const buffer = (src: Uint8Array): ArrayBuffer => {
  const result = new ArrayBuffer(src.byteLength);
  new Uint8Array(result).set(src);
  return result;
};
const hex = (src: Uint8Array) =>
  Array.from(src, b => b.toString(16).padStart(2, "0")).join("");
const hash = async (src: Uint8Array) =>
  hex(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer(src))));
const b64 = (src: Uint8Array) =>
  btoa(Array.from(src, c => String.fromCharCode(c)).join(""));
const now = Date.parse("2026-10-28T20:00:00Z");

async function fixture() {
  const subtle = crypto.subtle;
  const pair = await subtle.generateKey(
    {name:"Ed25519"}, true, ["sign","verify"],
  ) as CryptoKeyPair;
  const pub = new Uint8Array(await subtle.exportKey("raw",pair.publicKey));
  const packObj = {
    schema:"fieldshield.ioc-pack.v1",source:"SYNTHETIC ONLY",
    issued_at:"2026-01-01T00:00:00Z",
    indicators:[
      {id:"domain-demo",kind:"domain",value:"demo.example.invalid",confidence:"medium",
        reference:"https://www.rfc-editor.org/rfc/rfc2606"},
      {id:"sha-demo",kind:"sha256",value:"a".repeat(64),confidence:"low",
        reference:"https://www.rfc-editor.org/rfc/rfc6234"},
      {id:"path-demo",kind:"path",value:"foo/bar.txt",confidence:"high",
        reference:"https://www.rfc-editor.org/rfc/rfc2606"},
      {id:"url-demo",kind:"url",value:"https://demo.example.invalid/foo",confidence:"low",
        reference:"https://www.rfc-editor.org/rfc/rfc2606"},
    ],
  };
  const signPack = async (packObjToSign: typeof packObj) => {
    const packRaw = bytes(packObjToSign);
    const header = {
      schema:"fieldshield.signed-ioc.v1",
      publisher:"test-publisher",key_id:"key-1",
      pack_sha256:await hash(packRaw),
      issued_at:"2026-02-01T00:00:00Z",expires_at:"2027-01-01T00:00:00Z",
    };
    const ordered=JSON.stringify(Object.fromEntries(
      Object.entries(header).sort(([a],[b]) => a<b ? -1:a>b ? 1:0),
    ));
    const domain=enc.encode("FieldShield Sentinel Signed IOC v1\0");
    const text=enc.encode(ordered);
    const payload=new Uint8Array(domain.byteLength+text.byteLength);
    payload.set(domain);payload.set(text,domain.length);
    const signature=new Uint8Array(await subtle.sign("Ed25519",pair.privateKey,buffer(payload)));
    return {packRaw,manifestRaw:bytes({...header,signature_b64:b64(signature)})};
  };
  const {packRaw,manifestRaw}=await signPack(packObj);
  const trustRaw=bytes({
    schema:"fieldshield.trust-store.v1",
    publishers:[{
      id:"test-publisher",minimum_issued_at:"2026-01-01T00:00:00Z",
      blocked_pack_sha256:[],
      keys:[{id:"key-1",algorithm:"ed25519",state:"trusted",public_key_b64:b64(pub)}],
    }],
  });
  return {
    packRaw,manifestRaw,trustRaw,
    independentPublicKeySha256:await hash(pub),
    now,subtle,
    packObj,signPack,
  };
}
const observations = (values: unknown[]) => bytes({
  schema:"fieldshield.observations.v1", observations:values,
});
const row = (kind: string, value: string) => ({kind,value});

describe("browser-only FieldShield observations matching", () => {
  it("matches exact typed indicators, URL hostname fallback and counts correctly", async () => {
    const args=await fixture();
    const report=await verifyAndMatchSelectedObservations({
      ...args, observationsRaw:observations([
        row("domain","DEMO.Example.INVALID."),
        row("sha256","A".repeat(64)),
        row("path","foo\\bar.txt"),
        row("url","https://demo.example.invalid/foo"),
        row("process","unrelated-process"),
      ]),
    });
    expect(report.schema).toBe("phios.security_center.observations_match.v0.4");
    expect(report.decision).toBe("INDICATORS_FOUND");
    expect(report.inspected).toBe(5);
    expect(report.uninspected).toBe(0);
    expect(report.matches).toBe(5); // domain, sha, path, URL and URL hostname
    expect(report.verifiedPackSha256).toBe(await hash(args.packRaw));
    expect(report.observationFileSha256).toHaveLength(64);
    expect(report.hostSecurityObserved).toBe(false);
    expect(report.hostScanPerformed).toBe(false);
    expect(report.networkUsed).toBe(false);
    expect(report.evidenceValuesIncluded).toBe(false);
    expect(JSON.stringify(report)).not.toContain("foo/bar.txt");
    expect(JSON.stringify(report)).not.toContain("demo.example.invalid");
    expect(report.findingIds.map(x=>x.indicatorId)).toContain("domain-demo");
  });

  it("distinguishes no matches in scope from a clean-device claim", async () => {
    const args=await fixture();
    const report=await verifyAndMatchSelectedObservations({
      ...args,observationsRaw:observations([row("domain","safe.example.invalid")]),
    });
    expect(report.decision).toBe("NO_MATCHES_IN_SCOPE");
    expect(report.matches).toBe(0);
    expect(report.hostSecurityObserved).toBe(false);
    expect(report.scope).toBe("USER_SELECTED_JSON_ONLY");
  });

  it("marks malformed, unsupported and empty evidence as incomplete", async () => {
    const args=await fixture();
    const report=await verifyAndMatchSelectedObservations({
      ...args, observationsRaw:observations([
        row("domain","good.example.invalid"),
        row("url","not a URL"),row("unknown","something"),{},
      ]),
    });
    expect(report.decision).toBe("INCOMPLETE");
    expect(report.inspected).toBe(1);
    expect(report.uninspected).toBe(3);
    expect((await verifyAndMatchSelectedObservations({
      ...args,observationsRaw:observations([]),
    })).decision).toBe("INCOMPLETE");
  });

  it("fails closed on an altered detached pack, bad pin and revoked key", async () => {
    const args=await fixture();
    await expect(verifyAndMatchSelectedObservations({
      ...args,packRaw:bytes({...args.packObj,source:"tampered"}),
      observationsRaw:observations([row("domain","demo.example.invalid")]),
    })).rejects.toThrow("SHA256 mismatch");
    await expect(verifyAndMatchSelectedObservations({
      ...args,independentPublicKeySha256:"f".repeat(64),
      observationsRaw:observations([row("domain","demo.example.invalid")]),
    })).rejects.toThrow("independent SHA256 pin");
    const trust=parseStrictJson(args.trustRaw,131_072);
    const roster=trust.publishers as Array<Record<string,unknown>>;
    const keys=roster[0].keys as Array<Record<string,unknown>>;
    keys[0].state="revoked";
    await expect(verifyAndMatchSelectedObservations({
      ...args,trustRaw:bytes(trust),observationsRaw:observations([]),
    })).rejects.toThrow("revoked");
  });

  it("rejects signed packs with duplicate IDs or malformed indicators", async () => {
    const args=await fixture();
    const duplicate=structuredClone(args.packObj);
    duplicate.indicators[1].id="domain-demo";
    const signed=await args.signPack(duplicate);
    await expect(verifyAndMatchSelectedObservations({
      ...args,...signed,observationsRaw:observations([row("domain","demo.example.invalid")]),
    })).rejects.toThrow("Duplicate or unsafe signed indicator ID");
    const wrong=structuredClone(args.packObj);
    wrong.indicators[0].confidence="unknown";
    const signedWrong=await args.signPack(wrong);
    await expect(verifyAndMatchSelectedObservations({
      ...args,...signedWrong,observationsRaw:observations([row("domain","demo.example.invalid")]),
    })).rejects.toThrow("provenance or confidence");
  });

  it("rejects oversized or invalid observation document schemas", async () => {
    const args=await fixture();
    const tooLarge=new Uint8Array(OBSERVATION_LIMIT+1);
    await expect(verifyAndMatchSelectedObservations({
      ...args,observationsRaw:tooLarge,
    })).rejects.toThrow("exceeds");
    await expect(verifyAndMatchSelectedObservations({
      ...args,observationsRaw:bytes({schema:"something-else",observations:[]}),
    })).rejects.toThrow("observations.v1");
  });

  it("caps findings without claiming all observations are fully resolved", async () => {
    const args=await fixture();
    const evidence=observations(Array.from({length:1002},()=>row("domain","demo.example.invalid")));
    const report=await verifyAndMatchSelectedObservations({...args,observationsRaw:evidence});
    expect(report.matches).toBe(1000);
    expect(report.limitReached).toBe(true);
    expect(report.uninspected).toBe(1);
    expect(report.decision).toBe("INCOMPLETE");
    expect(report.findingIds.length).toBeLessThanOrEqual(24);
  });

  it("normalizes only typed exact values and refuses unsafe paths and URLs",()=>{
    expect(normalizeFieldShield("domain","ExAmPle.invalid.")).toBe("example.invalid");
    expect(normalizeFieldShield("path","foo\\bar")).toBe("foo/bar");
    expect(normalizeFieldShield("process","  SomeProcess  ")).toBe("SomeProcess");
    expect(()=>normalizeFieldShield("path","../../secret")).toThrow("relative");
    expect(()=>normalizeFieldShield("url","ftp://example.invalid")).toThrow("HTTP");
    expect(()=>normalizeFieldShield("domain","-bad.example")).toThrow("labels");
  });
});
