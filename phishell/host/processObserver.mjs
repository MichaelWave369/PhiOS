import os from "node:os";
import { readdir, readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const PROC_ROOT = "/proc";
const MAX_EXPOSED_PROCESSES = 32;
const MAX_COMM_LENGTH = 128;

function boundedText(value, max = MAX_COMM_LENGTH) {
  if (typeof value !== "string") return "";
  const normalized = value.replace(/[\r\n\t]/g, " ").trim();
  return normalized.length <= max ? normalized : normalized.slice(0, max);
}

function parseStatus(text) {
  const fields = new Map();

  for (const line of text.split("\n")) {
    const separator = line.indexOf(":");
    if (separator <= 0) continue;
    fields.set(line.slice(0, separator), line.slice(separator + 1).trim());
  }

  const uidFields = (fields.get("Uid") ?? "").split(/\s+/).filter(Boolean);
  const stateRaw = fields.get("State") ?? "";
  const stateCode = stateRaw.slice(0, 1);
  const ppid = Number(fields.get("PPid"));
  const threads = Number(fields.get("Threads"));
  const rssMatch = /^(\d+)\s+kB$/i.exec(fields.get("VmRSS") ?? "");

  return {
    uid: uidFields.length > 0 ? Number(uidFields[0]) : null,
    state: /^[RSDTtZXIP]$/.test(stateCode) ? stateCode : "?",
    ppid: Number.isInteger(ppid) && ppid >= 0 ? ppid : null,
    threads: Number.isInteger(threads) && threads >= 1 ? threads : null,
    rssBytes: rssMatch ? Number(rssMatch[1]) * 1024 : 0,
  };
}

async function readProcess(pid) {
  try {
    const [statusText, commText] = await Promise.all([
      readFile(`${PROC_ROOT}/${pid}/status`, "utf8"),
      readFile(`${PROC_ROOT}/${pid}/comm`, "utf8"),
    ]);

    const status = parseStatus(statusText);
    if (status.uid === null || status.ppid === null || status.threads === null) {
      return null;
    }

    return {
      pid,
      ppid: status.ppid,
      uid: status.uid,
      comm: boundedText(commText),
      state: status.state,
      rssBytes: status.rssBytes,
      threads: status.threads,
    };
  } catch {
    return null;
  }
}

function stateCounts(processes) {
  const counts = {
    running: 0,
    sleeping: 0,
    diskSleep: 0,
    stopped: 0,
    zombie: 0,
    idle: 0,
    other: 0,
  };

  for (const process of processes) {
    switch (process.state) {
      case "R":
        counts.running += 1;
        break;
      case "S":
        counts.sleeping += 1;
        break;
      case "D":
        counts.diskSleep += 1;
        break;
      case "T":
      case "t":
        counts.stopped += 1;
        break;
      case "Z":
        counts.zombie += 1;
        break;
      case "I":
        counts.idle += 1;
        break;
      default:
        counts.other += 1;
    }
  }

  return counts;
}

export async function collectCurrentUserProcessObservation({
  uid = typeof process.getuid === "function" ? process.getuid() : os.userInfo().uid,
} = {}) {
  const capturedAt = new Date().toISOString();

  if (process.platform !== "linux") {
    return {
      schemaVersion: "phios.process-observation.v1",
      source: "procfs-current-user",
      capturedAt,
      availability: "unavailable",
      reason: "non-linux-host",
      scope: "current-user",
      processLimit: MAX_EXPOSED_PROCESSES,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      currentUid: Number.isInteger(uid) ? uid : null,
      currentUserProcessCount: 0,
      stateCounts: stateCounts([]),
      processes: [],
    };
  }

  if (!Number.isInteger(uid) || uid < 0) {
    return {
      schemaVersion: "phios.process-observation.v1",
      source: "procfs-current-user",
      capturedAt,
      availability: "unavailable",
      reason: "current-uid-unavailable",
      scope: "current-user",
      processLimit: MAX_EXPOSED_PROCESSES,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      currentUid: null,
      currentUserProcessCount: 0,
      stateCounts: stateCounts([]),
      processes: [],
    };
  }

  let entries;
  try {
    entries = await readdir(PROC_ROOT, { withFileTypes: true });
  } catch {
    return {
      schemaVersion: "phios.process-observation.v1",
      source: "procfs-current-user",
      capturedAt,
      availability: "unavailable",
      reason: "procfs-unavailable",
      scope: "current-user",
      processLimit: MAX_EXPOSED_PROCESSES,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      currentUid: uid,
      currentUserProcessCount: 0,
      stateCounts: stateCounts([]),
      processes: [],
    };
  }

  const pids = entries
    .filter((entry) => entry.isDirectory() && /^\d+$/.test(entry.name))
    .map((entry) => Number(entry.name))
    .filter((pid) => Number.isInteger(pid) && pid > 0);

  const observed = (await Promise.all(pids.map((pid) => readProcess(pid))))
    .filter((item) => item !== null && item.uid === uid);

  const sorted = [...observed].sort(
    (a, b) => b.rssBytes - a.rssBytes || a.pid - b.pid,
  );

  return {
    schemaVersion: "phios.process-observation.v1",
    source: "procfs-current-user",
    capturedAt: new Date().toISOString(),
    availability: "available",
    reason: null,
    scope: "current-user",
    processLimit: MAX_EXPOSED_PROCESSES,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    currentUid: uid,
    currentUserProcessCount: observed.length,
    stateCounts: stateCounts(observed),
    processes: sorted.slice(0, MAX_EXPOSED_PROCESSES).map((item) => ({
      pid: item.pid,
      ppid: item.ppid,
      comm: item.comm,
      state: item.state,
      rssBytes: item.rssBytes,
      threads: item.threads,
    })),
  };
}

async function main() {
  const observation = await collectCurrentUserProcessObservation();
  if (process.argv.includes("--require-linux") && observation.availability !== "available") {
    throw new Error(`process observation unavailable: ${observation.reason}`);
  }
  if (process.argv.includes("--check") || process.argv.includes("--require-linux")) {
    return;
  }
  process.stdout.write(
    `${JSON.stringify(observation, null, process.argv.includes("--json") ? 2 : 0)}\n`,
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
