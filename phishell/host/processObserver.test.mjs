import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { collectCurrentUserProcessObservation } from "./processObserver.mjs";

test(
  "process observer exposes only bounded current-user process metadata",
  { skip: process.platform !== "linux" },
  async () => {
    const observation = await collectCurrentUserProcessObservation();

    assert.equal(observation.schemaVersion, "phios.process-observation.v1");
    assert.equal(observation.source, "procfs-current-user");
    assert.equal(observation.scope, "current-user");
    assert.equal(observation.readOnly, true);
    assert.equal(observation.executionAuthority, false);
    assert.equal(observation.effectPerformed, false);
    assert.equal(observation.availability, "available");
    assert.ok(observation.currentUid >= 0);
    assert.ok(observation.currentUserProcessCount >= observation.processes.length);
    assert.ok(observation.processes.length <= observation.processLimit);
    assert.equal(observation.processLimit, 32);

    for (const item of observation.processes) {
      assert.deepEqual(
        Object.keys(item).sort(),
        ["comm", "pid", "ppid", "rssBytes", "state", "threads"],
      );
      assert.ok(item.pid > 0);
      assert.ok(item.ppid >= 0);
      assert.ok(item.comm.length <= 128);
      assert.ok(item.rssBytes >= 0);
      assert.ok(item.threads >= 1);
    }
  },
);

test("process observer source omits sensitive and mutating proc surfaces", async () => {
  const source = await readFile(new URL("./processObserver.mjs", import.meta.url), "utf8");
  for (const forbidden of [
    "/cmdline",
    "/environ",
    "/cwd",
    "/exe",
    "node:child_process",
    "process.kill",
    "SIGKILL",
    "SIGTERM",
    "renice",
    "ptrace",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});

test(
  "process observer does not expose processes belonging to another uid",
  { skip: process.platform !== "linux" },
  async () => {
    const impossibleUid = 2_147_483_646;
    const observation = await collectCurrentUserProcessObservation({ uid: impossibleUid });

    assert.equal(observation.currentUid, impossibleUid);
    assert.equal(observation.currentUserProcessCount, 0);
    assert.deepEqual(observation.processes, []);
  },
);
