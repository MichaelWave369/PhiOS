import dbus from "@jellybrick/dbus-next";
import { access } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { pathToFileURL } from "node:url";

const SYSTEMD_RUNTIME = "/run/systemd/system";
const SYSTEMD_DESTINATION = "org.freedesktop.systemd1";
const SYSTEMD_PATH = "/org/freedesktop/systemd1";
const SYSTEMD_MANAGER = "org.freedesktop.systemd1.Manager";

export const SERVICE_ALLOWLIST = Object.freeze([
  Object.freeze({ id: "dbus", label: "D-Bus", units: Object.freeze(["dbus.service"]) }),
  Object.freeze({
    id: "journald",
    label: "systemd-journald",
    units: Object.freeze(["systemd-journald.service"]),
  }),
  Object.freeze({
    id: "resolved",
    label: "systemd-resolved",
    units: Object.freeze(["systemd-resolved.service"]),
  }),
  Object.freeze({
    id: "network-manager",
    label: "NetworkManager",
    units: Object.freeze(["NetworkManager.service"]),
  }),
  Object.freeze({
    id: "networkd",
    label: "systemd-networkd",
    units: Object.freeze(["systemd-networkd.service"]),
  }),
  Object.freeze({
    id: "ssh",
    label: "SSH",
    units: Object.freeze(["ssh.service", "sshd.service"]),
  }),
  Object.freeze({ id: "docker", label: "Docker", units: Object.freeze(["docker.service"]) }),
  Object.freeze({ id: "ollama", label: "Ollama", units: Object.freeze(["ollama.service"]) }),
  Object.freeze({
    id: "bluetooth",
    label: "Bluetooth",
    units: Object.freeze(["bluetooth.service"]),
  }),
]);

function boundedText(value, max = 256) {
  if (typeof value !== "string") return "";
  return value.length <= max ? value : value.slice(0, max);
}

async function systemdRuntimePresent() {
  try {
    await access(SYSTEMD_RUNTIME, fsConstants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function normalizeLoadedUnits(rows) {
  const loaded = new Map();

  if (!Array.isArray(rows)) return loaded;

  for (const row of rows) {
    if (!Array.isArray(row) || row.length < 5) continue;

    const [name, description, loadState, activeState, subState] = row;
    if (
      typeof name !== "string" ||
      !name.endsWith(".service") ||
      typeof loadState !== "string" ||
      typeof activeState !== "string" ||
      typeof subState !== "string"
    ) {
      continue;
    }

    loaded.set(name, {
      name,
      description: boundedText(description),
      loadState: boundedText(loadState, 64),
      activeState: boundedText(activeState, 64),
      subState: boundedText(subState, 64),
    });
  }

  return loaded;
}

function projectAllowlist(loaded) {
  return SERVICE_ALLOWLIST.map((definition) => {
    const match = definition.units
      .map((unit) => loaded.get(unit))
      .find((candidate) => candidate !== undefined);

    if (!match) {
      return {
        id: definition.id,
        label: definition.label,
        unit: definition.units[0],
        found: false,
        description: null,
        loadState: null,
        activeState: null,
        subState: null,
      };
    }

    return {
      id: definition.id,
      label: definition.label,
      unit: match.name,
      found: true,
      description: match.description || null,
      loadState: match.loadState,
      activeState: match.activeState,
      subState: match.subState,
    };
  });
}

export async function collectSystemdServiceObservation({
  busFactory = () => dbus.systemBus(),
} = {}) {
  const capturedAt = new Date().toISOString();

  if (process.platform !== "linux") {
    return {
      schemaVersion: "phios.service-observation.v1",
      source: "systemd-dbus-list-units",
      capturedAt,
      availability: "unavailable",
      reason: "non-linux-host",
      allowlistOnly: true,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      services: projectAllowlist(new Map()),
    };
  }

  if (!(await systemdRuntimePresent())) {
    return {
      schemaVersion: "phios.service-observation.v1",
      source: "systemd-dbus-list-units",
      capturedAt,
      availability: "unavailable",
      reason: "systemd-runtime-not-present",
      allowlistOnly: true,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      services: projectAllowlist(new Map()),
    };
  }

  let bus;
  try {
    bus = busFactory();
    const object = await bus.getProxyObject(SYSTEMD_DESTINATION, SYSTEMD_PATH);
    const manager = object.getInterface(SYSTEMD_MANAGER);
    const rows = await manager.ListUnits();
    const loaded = normalizeLoadedUnits(rows);

    return {
      schemaVersion: "phios.service-observation.v1",
      source: "systemd-dbus-list-units",
      capturedAt: new Date().toISOString(),
      availability: "available",
      reason: null,
      allowlistOnly: true,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      services: projectAllowlist(loaded),
    };
  } catch {
    return {
      schemaVersion: "phios.service-observation.v1",
      source: "systemd-dbus-list-units",
      capturedAt: new Date().toISOString(),
      availability: "unavailable",
      reason: "system-bus-unavailable",
      allowlistOnly: true,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      services: projectAllowlist(new Map()),
    };
  } finally {
    if (bus && typeof bus.disconnect === "function") {
      bus.disconnect();
    }
  }
}

async function main() {
  const observation = await collectSystemdServiceObservation();
  if (process.argv.includes("--require-systemd") && observation.availability !== "available") {
    throw new Error(`service observation unavailable: ${observation.reason}`);
  }
  if (process.argv.includes("--check") || process.argv.includes("--require-systemd")) {
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
