import test from "node:test";
import assert from "node:assert/strict";
import {
  PUBLIC_STATUS_URL,
  waitForPublicPhiOSCommit,
} from "../../scripts/wait-for-production-commit.mjs";

const sha = "a".repeat(40);
const meta = (overrides = {}) => ({
  repository: "MichaelWave369/PhiOS", commit: sha,
  commitShort: sha.slice(0, 9),
  siteBuild: "verified", authority: "none", ...overrides,
});
function response(data, status = 200, type = "application/json") {
  return {
    ok: status >= 200 && status < 300, status,
    headers: { get: x => x === "content-type" ? type : null },
    json: async () => data,
  };
}
test("a public exact SHA match produces a narrowly scoped metadata receipt", async () => {
  const calls = [];
  const got = await waitForPublicPhiOSCommit(sha, {
    fetcher: async (url, opts) => {
      calls.push({ url, opts });
      return response(meta());
    },
    attempts: 1, delayMs: 0,
  });
  assert.equal(got.status, "PUBLIC_METADATA_EXACT_COMMIT_OBSERVED_ONLY");
  assert.equal(got.expectedSha, sha);
  assert.equal(got.observedSha, sha);
  assert.equal(got.browserRenderedVerified, false);
  assert.equal(got.actualWanDisconnectedVerified, false);
  assert.equal(got.linuxOSBootVerified, false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].opts.redirect, "error");
  assert.equal(calls[0].opts.cache, "no-store");
  assert.equal(calls[0].url.startsWith(PUBLIC_STATUS_URL), true);
});

test("temporary stale Pages metadata is retried within a strict bound", async () => {
  let count = 0;
  const waits = [];
  const got = await waitForPublicPhiOSCommit(sha, {
    fetcher: async () => response(count++ === 0 ? meta({
      commit: "b".repeat(40), commitShort: "b".repeat(9),
    }) : meta()),
    attempts: 2, delayMs: 1, sleep: ms => { waits.push(ms); },
  });
  assert.equal(got.attemptsUsed, 2);
  assert.deepEqual(waits, [1]);
});

test("HTTP error, forged authority, wrong repo and non-JSON never qualify as correct commit", async () => {
  for (const bad of [
    () => response(meta(), 503),
    () => response(meta({ authority: "operator" })),
    () => response(meta({ repository: "private/something" })),
    () => response(meta(), 200, "text/html"),
    async () => { throw new Error("offline"); },
  ]) {
    await assert.rejects(waitForPublicPhiOSCommit(sha, {
      fetcher: bad, attempts: 1, delayMs: 0,
    }), /Production did not expose expected PhiOS commit/);
  }
});

test("persistent stale commit is a hard failure, never silently accepts older site", async () => {
  const logs = [];
  await assert.rejects(waitForPublicPhiOSCommit(sha, {
    fetcher: async () => response(meta({
      commit: "c".repeat(40), commitShort: "c".repeat(9),
    })),
    attempts: 3, delayMs: 0, sleep: () => {},
    log: v => logs.push(v),
  }), /STALE_OR_OTHER_COMMIT/);
  assert.equal(logs.length, 3);
});

test("invalid SHA, iteration count and retry delay fail before touching the network", async () => {
  const never = () => { throw new Error("should not be invoked"); };
  await assert.rejects(waitForPublicPhiOSCommit("main", { fetcher: never }),
    /Expected exact/);
  await assert.rejects(waitForPublicPhiOSCommit(sha, { fetcher: never, attempts: 999 }),
    /bounded rollout policy/);
  await assert.rejects(waitForPublicPhiOSCommit(sha, { fetcher: never, delayMs: -1 }),
    /bounded rollout policy/);
});
