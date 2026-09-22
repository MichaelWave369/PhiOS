import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { composeSystemStateReceipt } from "./systemStateComposer.mjs";
import { assertValidSystemStateReceipt } from "./systemStateContract.mjs";
import { deriveSystemChangeReceipt } from "./systemChangeDeriver.mjs";
import { assertValidSystemChangeReceipt } from "./systemChangeContract.mjs";

test("change receipt reports only descriptive differences", async () => {
  const first = assertValidSystemStateReceipt(await composeSystemStateReceipt());
  const second = structuredClone(first);
  second.composedAt = new Date(Date.parse(first.composedAt) + 1000).toISOString();
  second.summary.currentUserProcessCount += 2;
  second.summary.installedPackageCount += 1;
  second.components[2].digest = "sha256:" + "b".repeat(64);
  second.components[3].digest = "sha256:" + "c".repeat(64);
  second.receiptDigest = "";
  const { recomputeSystemStateReceiptDigest } = await import("./systemStateComposer.mjs");
  second.receiptDigest = recomputeSystemStateReceiptDigest(second);
  assertValidSystemStateReceipt(second);

  const change = assertValidSystemChangeReceipt(deriveSystemChangeReceipt(first, second, {sequence: 7}));

  assert.equal(change.sequence, 7);
  assert.equal(change.persistent, false);
  assert.equal(change.historyScope, "session-memory");
  assert.equal(change.changedSummaryMetricCount, 2);
  assert.deepEqual(change.summaryChanges.map((row)=>row.metric), [
    "currentUserProcessCount",
    "installedPackageCount",
  ]);
  assert.equal(change.causeAssigned, false);
  assert.equal(change.severityAssigned, false);
  assert.equal(change.executionAuthority, false);
  assert.equal(change.effectPerformed, false);
});

test("change deriver source contains no persistence or effect surface", async () => {
  const source = await readFile(new URL("./systemChangeDeriver.mjs", import.meta.url), "utf8");
  for(const forbidden of [
    "writeFile","appendFile","node:child_process","exec(","spawn(","sqlite","duckdb",
    "systemctl","apt ","process.kill","localStorage","indexedDB"
  ]) assert.equal(source.includes(forbidden),false,forbidden);
});

test("two live receipts produce a valid bounded change receipt", {skip:process.platform!=="linux"}, async()=>{
  const first=await composeSystemStateReceipt();
  const second=await composeSystemStateReceipt();
  const change=assertValidSystemChangeReceipt(deriveSystemChangeReceipt(first,second));
  assert.equal(change.componentChanges.length,5);
  assert.ok(change.summaryChanges.length<=13);
  assert.match(change.changeDigest,/^sha256:[0-9a-f]{64}$/);
});
