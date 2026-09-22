import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createLocalObservationServer } from "./localTransport.mjs";

test(
  "local transport serves validated live observation on IPv4 loopback only",
  { skip: process.platform !== "linux" },
  async () => {
    const transport = createLocalObservationServer({ port: 0, serveShell: false });
    const address = await transport.listen();

    try {
      assert.equal(address.host, "127.0.0.1");
      assert.ok(address.port > 0);

      const response = await fetch(
        `http://127.0.0.1:${address.port}/api/v1/host-observation`,
      );
      assert.equal(response.status, 200);
      assert.equal(response.headers.get("access-control-allow-origin"), null);

      const envelope = await response.json();
      assert.equal(envelope.transportSchemaVersion, "phios.host-transport.v1");
      assert.equal(envelope.transport, "loopback-http");
      assert.equal(envelope.localOnly, true);
      assert.equal(envelope.readOnly, true);
      assert.equal(envelope.executionAuthority, false);
      assert.equal(envelope.effectPerformed, false);
      assert.equal(envelope.snapshot.source, "linux-readonly-node-probe");
      assert.equal(envelope.snapshot.executionAuthority, false);
      assert.ok(envelope.snapshotAgeMs >= 0);
    } finally {
      await transport.close();
    }
  },
);

test(
  "local transport rejects mutation methods and unknown routes",
  { skip: process.platform !== "linux" },
  async () => {
    const transport = createLocalObservationServer({ port: 0, serveShell: false });
    const address = await transport.listen();

    try {
      const post = await fetch(
        `http://127.0.0.1:${address.port}/api/v1/host-observation`,
        { method: "POST" },
      );
      assert.equal(post.status, 405);
      assert.equal(post.headers.get("allow"), "GET");
      const rejected = await post.json();
      assert.equal(rejected.effectPerformed, false);
      assert.equal(rejected.executionAuthority, false);

      const missing = await fetch(`http://127.0.0.1:${address.port}/api/v1/does-not-exist`);
      assert.equal(missing.status, 404);
    } finally {
      await transport.close();
    }
  },
);

test("transport source contains no generic execution or wildcard-listen surface", async () => {
  const source = await readFile(new URL("./localTransport.mjs", import.meta.url), "utf8");
  for (const forbidden of [
    "node:child_process",
    "exec(",
    "execFile(",
    "spawn(",
    "sudo ",
    "0.0.0.0",
    "::",
    "access-control-allow-origin",
  ]) {
    assert.equal(source.toLowerCase().includes(forbidden), false, forbidden);
  }
  assert.equal(source.includes('const LOOPBACK_HOST = "127.0.0.1"'), true);
});
