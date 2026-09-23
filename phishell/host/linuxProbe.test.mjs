import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { collectLinuxHostObservation } from "./linuxProbe.mjs";

test(
  "Linux probe returns observation-only data with no execution authority",
  { skip: process.platform !== "linux" },
  async () => {
    const snapshot = await collectLinuxHostObservation();

    assert.equal(snapshot.schemaVersion, "phios.host-observation.v1");
    assert.equal(snapshot.source, "linux-readonly-node-probe");
    assert.equal(snapshot.availability, "available");
    assert.equal(snapshot.reason, null);
    assert.equal(snapshot.readOnly, true);
    assert.equal(snapshot.executionAuthority, false);
    assert.equal(snapshot.effectPerformed, false);
    assert.equal(snapshot.host.platform, "linux");
    assert.ok(snapshot.cpu.logicalCores > 0);
    assert.ok(snapshot.memory.totalBytes > 0);
    assert.ok(snapshot.storage.totalBytes > 0);
    assert.equal(snapshot.init.serviceStatusBound, false);

    for (const network of snapshot.network) {
      assert.deepEqual(
        Object.keys(network).sort(),
        ["families", "internal", "name"],
        "network observations must omit address and MAC data",
      );
    }
  },
);

test("Linux probe source contains no process execution surface", async () => {
  const source = await readFile(new URL("./linuxProbe.mjs", import.meta.url), "utf8");
  for (const forbidden of ["node:child_process", "exec(", "execFile(", "spawn(", "sudo "]) {
    assert.equal(source.includes(forbidden), false, `forbidden execution surface: ${forbidden}`);
  }
});


test(
  "Linux probe preserves partial host facts when network enumeration is denied",
  { skip: process.platform !== "linux" },
  async () => {
    const snapshot = await collectLinuxHostObservation({
      networkInterfaces: () => {
        throw new Error("network interfaces denied");
      },
    });

    assert.equal(snapshot.availability, "unavailable");
    assert.equal(snapshot.reason, "network-enumeration-unavailable");
    assert.deepEqual(snapshot.network, []);
    assert.equal(snapshot.host.platform, "linux");
    assert.ok(snapshot.cpu.logicalCores > 0);
    assert.ok(snapshot.memory.totalBytes > 0);
    assert.ok(snapshot.storage.totalBytes > 0);
    assert.equal(snapshot.readOnly, true);
    assert.equal(snapshot.executionAuthority, false);
    assert.equal(snapshot.effectPerformed, false);
  },
);
