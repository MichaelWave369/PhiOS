import { test, expect } from "@playwright/test";

const site = "/PhiOS/";
const origin = "http://127.0.0.1:4173";

test("built PhiOS landing page renders, with no page exceptions or remote requests", async ({ page }) => {
  const pageErrors = [];
  const remoteAttempts = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) {
      remoteAttempts.push(url.origin);
      await route.abort("blockedbyclient");
    } else {
      await route.continue();
    }
  });

  const response = await page.goto(site, { waitUntil: "networkidle" });
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle("φ PhiOS | Capability is not authority");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sovereign. Coherent.");
  await expect(page.getByRole("heading", { name: "Build a system people can leave." })).toBeVisible();
  await expect(page.getByText("CAPABILITY != AUTHORITY").first()).toBeVisible();

  expect(pageErrors).toEqual([]);
  expect(remoteAttempts).toEqual([]);
});

test("primary navigation routes to content without leaving the built Pages base", async ({ page }) => {
  await page.goto(site);
  const nav = page.getByRole("navigation", { name: "Primary navigation" });
  await expect(nav.getByRole("link", { name: "GitHub" })).toHaveAttribute(
    "href",
    "https://github.com/MichaelWave369/PhiOS",
  );

  await nav.getByRole("link", { name: "Architecture" }).click();
  await expect(page).toHaveURL(/\/PhiOS\/#architecture$/);
  await expect(page.getByRole("heading", { name: "The graph changes with the question." })).toBeVisible();

  await nav.getByRole("link", { name: "Sovereignty" }).click();
  await expect(page).toHaveURL(/\/PhiOS\/#sovereignty$/);
  await expect(page.getByRole("heading", { name: "Build a system people can leave." })).toBeVisible();

  await nav.getByRole("link", { name: "Live Project" }).click();
  await expect(page).toHaveURL(/\/PhiOS\/#status$/);
  await expect(page.getByRole("heading", { name: "Build facts, not browser secrets." })).toBeVisible();
});

test("architecture modes update available nodes and selected detail panel", async ({ page }) => {
  await page.goto(site);
  const mode = page.getByRole("group", { name: "Architecture view" });
  await mode.getByRole("button", { name: "AUTHORITY" }).click();
  await expect(page.locator(".mode-explainer")).toContainText(
    "AUTHORITY strips away advisory-only paths",
  );
  await page.locator(".node-grid button.node").filter({ hasText: "Governed Action" }).click();
  await expect(page.locator(".detail-panel h3")).toHaveText("Governed Action");
  await mode.getByRole("button", { name: "EVIDENCE" }).click();
  await expect(page.locator(".mode-explainer")).toContainText(
    "EVIDENCE follows observation",
  );
  await expect(page.locator(".node-grid button.node").filter({ hasText: "Reality Ledger" })).toHaveCount(1);
});

test("CRT control toggles its pressed state and remains a user choice", async ({ page }) => {
  await page.goto(site);
  const toggle = page.getByRole("button", { name: "CRT MODE" });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(page.getByRole("button", { name: "CRT ON" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".app")).toHaveClass(/\bcrt\b/);
  await page.getByRole("button", { name: "CRT ON" }).click();
  await expect(page.getByRole("button", { name: "CRT MODE" })).toHaveAttribute("aria-pressed", "false");
});

test("built project status JSON loads and remains informational", async ({ page, request }) => {
  const response = await request.get(site + "project-status.json");
  expect(response.ok()).toBeTruthy();
  const metadata = await response.json();
  expect(metadata.repository).toBe("MichaelWave369/PhiOS");
  expect(metadata.authority).toBe("none");
  expect(metadata.siteBuild).toBe("verified");
  expect(metadata.commit).toMatch(/^[0-9a-f]{40}$/);

  await page.goto(site);
  await expect(page.locator("#status .status-card").first()).toContainText(metadata.commitShort);
  await expect(page.locator("#status")).toContainText("AUTHORITY");
  await expect(page.locator("#status")).toContainText("NONE");
});

test("mobile browser viewport still renders a useful PhiOS landing page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(site);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Explore the system" })).toBeVisible();
  await page.getByRole("link", { name: "Explore the system" }).click();
  await expect(page).toHaveURL(/\/PhiOS\/#architecture$/);
  await expect(page.getByRole("heading", { name: "The graph changes with the question." })).toBeVisible();
});
