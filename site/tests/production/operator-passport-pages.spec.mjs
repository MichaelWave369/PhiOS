import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

const origin = "https://michaelwave369.github.io";
const base = "/PhiOS/";
const storageKey = "phioperator.passport-import.v1";
const expected = process.env.EXPECTED_DEPLOY_SHA;

test.beforeAll(() => {
  if (!/^[a-f0-9]{40}$/.test(expected ?? "")) {
    throw new Error("Exact EXPECTED_DEPLOY_SHA is required for Passport production checks");
  }
});

test("deployed PhiOS Passport is reachable, opt-in, cosmetic, and revocable on exact Pages commit", async ({ page, request }) => {
  // This runs ONLY after the existing post-deploy SHA wait. Check the source
  // receipt again so an older cached site cannot make this pass.
  const status = await request.get(base + "project-status.json?smoke_sha=" + expected, {
    failOnStatusCode: true,
    headers: { "Cache-Control": "no-cache" },
  });
  const identity = await status.json();
  expect(identity.repository).toBe("MichaelWave369/PhiOS");
  expect(identity.commit).toBe(expected);
  expect(identity.authority).toBe("none");

  const errors = [];
  const remoteRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) {
      remoteRequests.push(route.request().url());
      return route.abort("blockedbyclient");
    }
    await route.continue();
  });

  const main = await page.goto(base + "?smoke_sha=" + expected, { waitUntil: "networkidle" });
  expect(main?.status()).toBe(200);
  await page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "Operator Passport" }).click();

  await expect(page).toHaveURL(origin + base + "operator-passport/");
  // The link navigation can finish before this page's ESM import graph
  // (station.js -> sdk.js) has completed. Playwright trace from the live
  // Pages run showed setInputFiles firing while sdk.js was still loading,
  // before station.js registered its change listener. Waiting for a
  // quiescent network proves module dependency fetches have settled.
  await page.waitForLoadState("networkidle");
  expect(errors).toEqual([]);
  expect(remoteRequests).toEqual([]);
  await expect(page.locator("#dossier-title")).toHaveText("NO PASSPORT IMPORTED");
  await expect(page.locator("#passport-export")).toBeDisabled();
  await expect(page.locator("#passport-remove")).toBeDisabled();
  await expect(page.locator("#benefits")).toContainText("remains available without a Passport");

  const sample = JSON.stringify({
    format: "phioperator-passport",
    version: 1,
    results: [1, 2, 3].map((rank) => ({
      rank,
      mode: "standard",
      bestScore: 9,
    })),
  });
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#passport-file").setInputFiles({
    name: "synthetic-operator-passport.json",
    mimeType: "application/json",
    buffer: Buffer.from(sample),
  });

  await expect(page.locator("#dossier-title")).toHaveText("STANDARD RANK 3 / 6");
  await expect(page.locator("body")).toHaveClass(/\boperator-grid\b/);
  await expect(page.locator("#mark")).toHaveText("Φ");
  await expect(page.locator("#passport-export")).toBeEnabled();

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("#dossier-title")).toHaveText("STANDARD RANK 3 / 6");
  expect(JSON.parse(await page.evaluate((key) => localStorage.getItem(key), storageKey)))
    .toEqual(JSON.parse(sample));

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.locator("#passport-export").click(),
  ]);
  expect(download.suggestedFilename()).toBe("phioperator-passport-v1.json");
  expect(JSON.parse(await readFile(await download.path(), "utf8"))).toEqual(JSON.parse(sample));

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#passport-remove").click();
  await expect(page.locator("#dossier-title")).toHaveText("NO PASSPORT IMPORTED");
  await expect(page.locator("body")).not.toHaveClass(/\boperator-grid\b/);
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBeNull();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("#dossier-title")).toHaveText("NO PASSPORT IMPORTED");

  // This is a public-site game progress test. Never infer or grant OS authority.
  expect(errors).toEqual([]);
  expect(remoteRequests).toEqual([]);
});
