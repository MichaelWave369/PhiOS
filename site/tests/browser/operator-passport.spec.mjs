import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

const station = "/PhiOS/operator-passport/";
const origin = "http://127.0.0.1:4173";
const storageKey = "phioperator.passport-import.v1";

const passport = (scores) => JSON.stringify({
  format: "phioperator-passport",
  version: 1,
  results: scores.map((bestScore, index) => ({
    rank: index + 1,
    mode: "standard",
    bestScore,
  })),
});

async function choosePassport(page, content, name = "passport.json") {
  await page.locator("#passport-file").setInputFiles({
    name,
    mimeType: "application/json",
    buffer: Buffer.from(content),
  });
}

test("optional Passport route is navigable and usable without any profile or remote requests", async ({ page }) => {
  const errors = [], foreignRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      foreignRequests.push(route.request().url());
      return route.abort("blockedbyclient");
    }
    await route.continue();
  });

  await page.goto("/PhiOS/");
  await page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "Operator Passport" }).click();

  await expect(page).toHaveURL(new RegExp("/PhiOS/operator-passport/$"));
  await expect(page.getByRole("heading", { name: /YOUR CURIOSITY.*YOUR PASSPORT/ })).toBeVisible();
  await expect(page.locator("#dossier-title")).toHaveText("NO PASSPORT IMPORTED");
  await expect(page.locator("#passport-export")).toBeDisabled();
  await expect(page.locator("#passport-remove")).toBeDisabled();
  await expect(page.locator("body")).not.toHaveClass(/\boperator-grid\b/);
  await expect(page.locator("#benefits")).toContainText("remains available without a Passport");
  expect(errors).toEqual([]);
  expect(foreignRequests).toEqual([]);
});

test("Standard rank 3 imports by consent, persists locally, exports, and is removed", async ({ page }) => {
  await page.goto(station, { waitUntil: "networkidle" });
  const input = passport([9, 8, 7]);
  page.once("dialog", (dialog) => dialog.accept());
  await choosePassport(page, input);

  await expect(page.locator("#dossier-title")).toHaveText("STANDARD RANK 3 / 6");
  await expect(page.locator("body")).toHaveClass(/\boperator-grid\b/);
  await expect(page.locator("#mark")).toHaveText("Φ");
  await expect(page.locator("#benefits")).toContainText("decorative Field Grid");
  await expect(page.locator("#message")).toContainText("Passport imported locally");
  await expect(page.locator("#passport-export")).toBeEnabled();

  const persisted = await page.evaluate((key) => localStorage.getItem(key), storageKey);
  expect(JSON.parse(persisted)).toEqual(JSON.parse(input));

  await page.reload();
  await expect(page.locator("#dossier-title")).toHaveText("STANDARD RANK 3 / 6");
  await expect(page.locator("body")).toHaveClass(/\boperator-grid\b/);

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.locator("#passport-export").click(),
  ]);
  expect(download.suggestedFilename()).toBe("phioperator-passport-v1.json");
  expect(JSON.parse(await readFile(await download.path(), "utf8"))).toEqual(JSON.parse(input));

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#passport-remove").click();
  await expect(page.locator("#dossier-title")).toHaveText("NO PASSPORT IMPORTED");
  await expect(page.locator("body")).not.toHaveClass(/\boperator-grid\b/);
  await expect(page.locator("#passport-export")).toBeDisabled();
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBeNull();
  await page.reload();
  await expect(page.locator("#dossier-title")).toHaveText("NO PASSPORT IMPORTED");
});

test("Rank 6 is cosmetic; malformed, oversized and rejected imports never replace prior progress", async ({ page }) => {
  await page.goto(station);
  const full = passport([9, 9, 9, 9, 9, 9]);

  page.once("dialog", (dialog) => dialog.dismiss());
  await choosePassport(page, full);
  await expect(page.locator("#dossier-title")).toHaveText("NO PASSPORT IMPORTED");
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBeNull();

  page.once("dialog", (dialog) => dialog.accept());
  await choosePassport(page, full);
  await expect(page.locator("#dossier-title")).toHaveText("STANDARD RANK 6 / 6");
  await expect(page.locator("#mark")).toHaveText("Φ369");
  await expect(page.locator("#benefits")).toContainText("cosmetic honor");

  await choosePassport(page, "{invalid");
  await expect(page.locator("#message")).toContainText("Import rejected:");
  await expect(page.locator("#dossier-title")).toHaveText("STANDARD RANK 6 / 6");

  await page.locator("#passport-file").setInputFiles({
    name: "oversized.json",
    mimeType: "application/json",
    buffer: Buffer.alloc(16385, 0x20),
  });
  await expect(page.locator("#message")).toContainText("16 KiB limit");
  await expect(page.locator("#mark")).toHaveText("Φ369");
  expect(JSON.parse(await page.evaluate((key) => localStorage.getItem(key), storageKey)))
    .toEqual(JSON.parse(full));
});
