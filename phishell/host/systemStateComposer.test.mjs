import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  COMPONENT_IDS,
  MAX_COHERENT_SKEW_MS,
  composeSystemStateReceipt,
  recomputeSystemStateReceiptDigest,
} from "./systemStateComposer.mjs";

test(
  "system state composer produces one bounded read-only receipt over all observation planes",
  { skip: process.platform !== "linux" },
  async () => {
    const receipt = await composeSystemStateReceipt();

    assert.equal(receipt.schemaVersion, "phios.system-state.v1");
    assert.equal(receipt.source, "phios-system-state-composer");
    assert.equal(receipt.componentCount, 5);
    assert.deepEqual(
      receipt.components.map((component) => component.id),
      COMPONENT_IDS,
    );
    assert.equal(receipt.readOnly, true);
    assert.equal(receipt.executionAuthority, false);
    assert.equal(receipt.effectPerformed, false);
    assert.ok(receipt.captureSkewMs >= 0);
    assert.equal(receipt.maxCoherentSkewMs, MAX_COHERENT_SKEW_MS);
    assert.match(receipt.receiptDigest, /^sha256:[0-9a-f]{64}$/);
    assert.equal(receipt.receiptDigest, recomputeSystemStateReceiptDigest(receipt));

    for (const component of receipt.components) {
      assert.equal(component.readOnly, true);
      assert.equal(component.executionAuthority, false);
      assert.equal(component.effectPerformed, false);
      assert.match(component.digest, /^sha256:[0-9a-f]{64}$/);
    }

    assert.ok(receipt.summary.cpuLogicalCores >= 1);
    assert.ok(receipt.summary.memoryTotalBytes > 0);
    assert.ok(receipt.summary.rootStorageTotalBytes > 0);
  },
);

test("system state composer source adds no new Linux effect surface", async () => {
  const source = await readFile(new URL("./systemStateComposer.mjs", import.meta.url), "utf8");

  for (const forbidden of [
    "node:child_process",
    "writeFile",
    "appendFile",
    "exec(",
    "spawn(",
    "sudo ",
    "systemctl",
    "apt ",
    "process.kill",
    "/driver/bind",
    "/driver/unbind",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});

test(
  "receipt degrades instead of inventing availability",
  { skip: process.platform !== "linux" },
  async () => {
    const receipt = await composeSystemStateReceipt({
      collectPackages: async () => ({
        schemaVersion: "phios.package-observation.v1",
        source: "dpkg-status-file",
        capturedAt: new Date().toISOString(),
        availability: "unavailable",
        reason: "unsupported-package-database",
        adapter: "debian-dpkg-status",
        packageLimit: 64,
        readOnly: true,
        executionAuthority: false,
        effectPerformed: false,
        distro: { id: "test", name: "Test Linux" },
        totalInstalledPackageCount: 0,
        packages: [],
      }),
    });

    assert.equal(receipt.coherence, "degraded");
    assert.equal(receipt.availableComponentCount, 4);
    assert.equal(
      receipt.components.find((component) => component.id === "packages")?.availability,
      "unavailable",
    );
  },
);
