import { test, expect } from "@playwright/test";

const origin = "https://michaelwave369.github.io";
const base = "/PhiOS/";
const expected = process.env.EXPECTED_DEPLOY_SHA;

test.beforeAll(() => {
  if (!/^[a-f0-9]{40}$/.test(expected ?? "")) {
    throw new Error("Exact EXPECTED_DEPLOY_SHA is required for production checks");
  }
});

test("public Pages delivery renders the expected PhiOS site without errors or off-origin requests", async ({ page }) => {
  const errors = [], remoteAttempts = [];
  page.on("pageerror", err => errors.push(err.message));
  await page.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) {
      remoteAttempts.push(url.origin);
      return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  const response = await page.goto(base + "?smoke_sha=" + expected, {
    waitUntil: "networkidle",
  });
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle("φ PhiOS | Capability is not authority");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sovereign. Coherent.");
  await expect(page.getByRole("heading", { name: "Build a system people can leave." })).toBeVisible();
  expect(errors).toEqual([]);
  expect(remoteAttempts).toEqual([]);
});

test("live Pages metadata matches this workflow's exact shipped commit and has no authority", async ({ page, request }) => {
  const resp = await request.get(base + "project-status.json?smoke_sha=" + expected, {
    failOnStatusCode: true,
    headers: { "Cache-Control": "no-cache" },
  });
  expect(resp.headers()["content-type"]).toContain("application/json");
  const metadata = await resp.json();
  expect(metadata.repository).toBe("MichaelWave369/PhiOS");
  expect(metadata.commit).toBe(expected);
  expect(metadata.commitShort).toBe(expected.slice(0, 9));
  expect(metadata.siteBuild).toBe("verified");
  expect(metadata.authority).toBe("none");

  await page.goto(base + "?smoke_sha=" + expected);
  await expect(page.locator("#status .status-card").first()).toContainText(metadata.commitShort);
  await expect(page.locator("#status")).toContainText("NONE");
});

test("public navigation and architecture mode work on actual GitHub Pages", async ({ page }) => {
  await page.goto(base + "?smoke_sha=" + expected);
  const nav = page.getByRole("navigation", { name: "Primary navigation" });
  await nav.getByRole("link", { name: "Architecture" }).click();
  await expect(page).toHaveURL(/\/PhiOS\/\?smoke_sha=[a-f0-9]{40}#architecture$/);
  await expect(page.getByRole("heading", { name: "The graph changes with the question." })).toBeVisible();

  const switcher = page.getByRole("group", { name: "Architecture view" });
  await switcher.getByRole("button", { name: "AUTHORITY" }).click();
  await expect(page.locator(".mode-explainer")).toContainText("AUTHORITY strips away advisory-only paths");

  await nav.getByRole("link", { name: "Sovereignty" }).click();
  await expect(page.getByRole("heading", { name: "Build a system people can leave." })).toBeVisible();

  await nav.getByRole("link", { name: "Live Project" }).click();
  await expect(page.getByRole("heading", { name: "Build facts, not browser secrets." })).toBeVisible();
});

test("public CRT option is responsive without granting any authority", async ({ page }) => {
  await page.goto(base + "?smoke_sha=" + expected);
  const toggle = page.getByRole("button", { name: "CRT MODE" });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(page.getByRole("button", { name: "CRT ON" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".app")).toHaveClass(/\bcrt\b/);
});
