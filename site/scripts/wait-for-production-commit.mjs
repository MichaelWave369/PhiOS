// PhiOS Site R0.2: exact-commit GitHub Pages rollout check.
// Read-only, fixed public origin, no GitHub token, no write or authority minting.
import { fileURLToPath } from "node:url";

export const PUBLIC_STATUS_URL =
  "https://michaelwave369.github.io/PhiOS/project-status.json";
const SHA = /^[a-f0-9]{40}$/;

function assertIdentity(value, expectedSha) {
  return value !== null && typeof value === "object" &&
    value.repository === "MichaelWave369/PhiOS" &&
    value.commit === expectedSha &&
    value.commitShort === expectedSha.slice(0, 9) &&
    value.siteBuild === "verified" &&
    value.authority === "none";
}

/**
 * Wait briefly for GitHub Pages/CDN propagation, then require exact deployed
 * commit identity. Only the deployed metadata is checked; this does not prove
 * rendered browser content or offline operation. Browser tests run separately.
 */
export async function waitForPublicPhiOSCommit(
  expectedSha, {
    fetcher = fetch,
    sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
    attempts = 18,
    delayMs = 10_000,
    log = () => {},
  } = {},
) {
  if (!SHA.test(expectedSha)) throw new Error("Expected exact 40-character Git commit SHA");
  if (!Number.isSafeInteger(attempts) || attempts < 1 || attempts > 30 ||
      !Number.isSafeInteger(delayMs) || delayMs < 0 || delayMs > 30_000) {
    throw new Error("Invalid bounded rollout policy");
  }
  let lastReason = "NO_RESPONSE";
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const response = await fetcher(
        PUBLIC_STATUS_URL + "?phios_deploy_sha=" + expectedSha + "&attempt=" + attempt,
        {
          redirect: "error",
          cache: "no-store",
          signal: AbortSignal.timeout(10_000),
          headers: { Accept: "application/json" },
        },
      );
      if (!response?.ok) {
        lastReason = "HTTP_" + String(response?.status ?? "UNKNOWN");
      } else {
        const contentType = response.headers?.get?.("content-type") ?? "";
        if (!contentType.toLowerCase().includes("application/json")) {
          lastReason = "NOT_JSON";
        } else {
          const data = await response.json();
          if (assertIdentity(data, expectedSha)) {
            log("Production metadata matches exact deployed commit " +
              expectedSha.slice(0, 12) + " (attempt " + attempt + ").");
            return {
              status: "PUBLIC_METADATA_EXACT_COMMIT_OBSERVED_ONLY",
              expectedSha, observedSha: data.commit, attemptsUsed: attempt,
              source: PUBLIC_STATUS_URL,
              browserRenderedVerified: false,
              actualWanDisconnectedVerified: false,
              linuxOSBootVerified: false,
            };
          }
          lastReason = data?.repository === "MichaelWave369/PhiOS" &&
            typeof data?.commit === "string" && SHA.test(data.commit) ?
              "STALE_OR_OTHER_COMMIT_" + data.commit.slice(0, 12) :
              "IDENTITY_OR_STATUS_MISMATCH";
        }
      }
    } catch (error) {
      // A temporary Pages connection issue can happen before CDN rollout.
      lastReason = error?.name === "TimeoutError" ? "TIMEOUT" : "NETWORK_OR_JSON_ERROR";
    }
    log("Production rollout check " + attempt + "/" + attempts +
      ": " + lastReason);
    if (attempt < attempts) await sleep(delayMs);
  }
  throw new Error("Production did not expose expected PhiOS commit " +
    expectedSha.slice(0, 12) + " after " + attempts +
    " bounded checks; last observation: " + lastReason);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === fileURLToPath(new URL(
  "file://" + process.argv[1].replace(/\\/g, "/").replace(/^([A-Za-z]):/, "/$1:"),
))) {
  const expected = process.env.GITHUB_SHA ?? process.argv[2];
  waitForPublicPhiOSCommit(expected, { log: s => console.log(s) })
    .then(result => console.log(JSON.stringify(result, null, 2)))
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
