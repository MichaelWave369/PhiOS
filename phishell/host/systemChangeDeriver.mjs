import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";
import { assertValidSystemStateReceipt } from "./systemStateContract.mjs";
import { composeSystemStateReceipt } from "./systemStateComposer.mjs";

const SUMMARY_METRICS = Object.freeze([
  "cpuLogicalCores",
  "memoryTotalBytes",
  "rootStorageTotalBytes",
  "observedServiceCount",
  "activeServiceCount",
  "currentUserProcessCount",
  "installedPackageCount",
  "blockDeviceCount",
  "networkDeviceCount",
  "pciDeviceCount",
  "usbDeviceCount",
  "drmDeviceCount",
  "powerDeviceCount",
]);

const HISTORY_LIMIT = 16;

function sha256Json(value) {
  return `sha256:${createHash("sha256").update(JSON.stringify(value)).digest("hex")}`;
}

function digestChangeBody(receipt) {
  const { changeDigest: _ignored, ...body } = receipt;
  return sha256Json(body);
}

export function deriveSystemChangeReceipt(previousRaw, currentRaw, { sequence = 1 } = {}) {
  const previous = assertValidSystemStateReceipt(previousRaw);
  const current = assertValidSystemStateReceipt(currentRaw);

  if (!Number.isInteger(sequence) || sequence < 1) {
    throw new Error("change receipt sequence must be a positive integer");
  }

  const componentChanges = previous.components.map((fromComponent, index) => {
    const toComponent = current.components[index];
    if (toComponent.id !== fromComponent.id) {
      throw new Error("system-state component order changed");
    }
    return {
      id: fromComponent.id,
      fromAvailability: fromComponent.availability,
      toAvailability: toComponent.availability,
      availabilityChanged: fromComponent.availability !== toComponent.availability,
      fromDigest: fromComponent.digest,
      toDigest: toComponent.digest,
      digestChanged: fromComponent.digest !== toComponent.digest,
    };
  });

  const summaryChanges = [];
  for (const metric of SUMMARY_METRICS) {
    const from = previous.summary[metric];
    const to = current.summary[metric];
    if (from !== to) {
      summaryChanges.push({
        metric,
        from,
        to,
        delta: to - from,
      });
    }
  }

  const changedComponentCount = componentChanges.filter(
    (change) => change.availabilityChanged || change.digestChanged,
  ).length;

  const elapsedMs = Math.max(
    0,
    Date.parse(current.composedAt) - Date.parse(previous.composedAt),
  );

  const receipt = {
    schemaVersion: "phios.system-change.v1",
    source: "phios-system-change-deriver",
    recordedAt: new Date().toISOString(),
    sequence,
    historyScope: "session-memory",
    persistent: false,
    historyLimit: HISTORY_LIMIT,
    fromReceiptDigest: previous.receiptDigest,
    toReceiptDigest: current.receiptDigest,
    fromComposedAt: previous.composedAt,
    toComposedAt: current.composedAt,
    elapsedMs,
    coherence: {
      from: previous.coherence,
      to: current.coherence,
      changed: previous.coherence !== current.coherence,
    },
    changedComponentCount,
    componentChanges,
    changedSummaryMetricCount: summaryChanges.length,
    summaryChanges,
    causeAssigned: false,
    severityAssigned: false,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    changeDigest: "",
  };

  receipt.changeDigest = digestChangeBody(receipt);
  return receipt;
}

export function recomputeSystemChangeDigest(receipt) {
  return digestChangeBody(receipt);
}

export { HISTORY_LIMIT, SUMMARY_METRICS };

async function main() {
  const first = await composeSystemStateReceipt();
  const second = await composeSystemStateReceipt();
  const change = deriveSystemChangeReceipt(first, second);

  if (process.argv.includes("--check")) return;
  process.stdout.write(
    `${JSON.stringify(change, null, process.argv.includes("--json") ? 2 : 0)}\n`,
  );
}

const invokedDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
