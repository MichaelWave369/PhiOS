import { test } from "node:test";
import assert from "node:assert/strict";
import { latestAppTestLine, publicLinuxImageIdentity } from "../../scripts/status-contracts.mjs";

test("App Platform status is derived from checked-in test filenames, not stale history", () => {
  assert.equal(latestAppTestLine([
    "test_app_platform_v025.py",
    "test_app_platform_v059_signed_release_review.py",
    "test_app_platform_v061_living_application.py",
    "test_other_v999.py",
  ]), "v0.61 tests");
  assert.equal(latestAppTestLine(["README.md"]), "unverified");
  assert.throws(() => latestAppTestLine(null), /test inventory/);
});

test("native image metadata includes only documented release-manifest facts", () => {
  assert.deepEqual(publicLinuxImageIdentity({
    os_version: "0.1.0-alpha.1",
    stage: "development-preview",
    architecture: "x86_64",
    secure_boot: false,
    installer_available: true,
  }), {
    version: "0.1.0-alpha.1",
    stage: "development-preview",
    architecture: "x86_64",
    secureBoot: false,
  });
  assert.throws(() => publicLinuxImageIdentity({ stage: "stable" }), /release contract/);
  assert.throws(() => publicLinuxImageIdentity({
    os_version: "1.0",
    stage: "development-preview",
    architecture: "arm64",
    secure_boot: false,
  }), /release contract/);
});
