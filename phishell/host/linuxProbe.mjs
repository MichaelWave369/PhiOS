import os from "node:os";
import { access, readdir, readFile, statfs } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { pathToFileURL } from "node:url";

async function readText(path) {
  try {
    return (await readFile(path, "utf8")).trim();
  } catch {
    return null;
  }
}

async function readNumber(path) {
  const value = await readText(path);
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function percentUsed(total, free) {
  if (!Number.isFinite(total) || total <= 0) return 0;
  return Math.round(((total - free) / total) * 1000) / 10;
}

async function observePowerSupplies() {
  const root = "/sys/class/power_supply";
  try {
    const entries = await readdir(root, { withFileTypes: true });
    return Promise.all(
      entries
        .filter((entry) => entry.isDirectory() || entry.isSymbolicLink())
        .map(async (entry) => ({
          name: entry.name,
          type: await readText(`${root}/${entry.name}/type`),
          status: await readText(`${root}/${entry.name}/status`),
          capacityPercent: await readNumber(`${root}/${entry.name}/capacity`),
        })),
    );
  } catch {
    return [];
  }
}

async function systemdPresent() {
  try {
    await access("/run/systemd/system", fsConstants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function observeNetwork() {
  const interfaces = os.networkInterfaces();
  return Object.entries(interfaces).map(([name, records]) => {
    const values = records ?? [];
    return {
      name,
      families: [...new Set(values.map((record) => record.family))].sort(),
      internal: values.length > 0 && values.every((record) => record.internal),
    };
  });
}

export async function collectLinuxHostObservation() {
  if (process.platform !== "linux") {
    throw new Error("linux-readonly-node-probe requires a Linux host");
  }

  const cpus = os.cpus();
  const memoryTotal = os.totalmem();
  const memoryFree = os.freemem();
  const root = await statfs("/");
  const storageTotal = root.blocks * root.bsize;
  const storageFree = root.bavail * root.bsize;
  const user = os.userInfo();

  return {
    schemaVersion: "phios.host-observation.v1",
    source: "linux-readonly-node-probe",
    capturedAt: new Date().toISOString(),
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    host: {
      hostname: os.hostname(),
      platform: os.platform(),
      release: os.release(),
      arch: os.arch(),
    },
    session: {
      username: user.username,
      uid: typeof user.uid === "number" ? user.uid : null,
      shell: process.env.SHELL ?? user.shell ?? null,
      sessionType: process.env.XDG_SESSION_TYPE ?? null,
    },
    cpu: {
      logicalCores: cpus.length,
      model: cpus[0]?.model ?? "unknown",
      loadAverage: os.loadavg(),
    },
    memory: {
      totalBytes: memoryTotal,
      freeBytes: memoryFree,
      usedPercent: percentUsed(memoryTotal, memoryFree),
    },
    storage: {
      mount: "/",
      totalBytes: storageTotal,
      freeBytes: storageFree,
      usedPercent: percentUsed(storageTotal, storageFree),
    },
    network: observeNetwork(),
    power: await observePowerSupplies(),
    init: {
      systemdPresent: await systemdPresent(),
      serviceStatusBound: false,
      reason:
        "PhiShell v0.4 does not bind service-control or service-status mutation paths to the observation transport.",
    },
  };
}

async function main() {
  const snapshot = await collectLinuxHostObservation();
  if (process.argv.includes("--check")) {
    return;
  }
  process.stdout.write(`${JSON.stringify(snapshot, null, process.argv.includes("--json") ? 2 : 0)}\n`);
}

const invokedDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
