import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const DPKG_STATUS_PATH = "/var/lib/dpkg/status";
const OS_RELEASE_PATH = "/etc/os-release";
const PACKAGE_LIMIT = 64;
const MAX_NAME = 128;
const MAX_VERSION = 256;
const MAX_ARCH = 64;

function boundedText(value, max) {
  if (typeof value !== "string") return "";
  const normalized = value.replace(/[\r\n\t]/g, " ").trim();
  return normalized.length <= max ? normalized : normalized.slice(0, max);
}

export function parseOsRelease(text) {
  const values = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const separator = trimmed.indexOf("=");
    if (separator <= 0) continue;

    const key = trimmed.slice(0, separator);
    let value = trimmed.slice(separator + 1).trim();
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

function distroSupportsDpkg(osRelease) {
  const id = String(osRelease.ID ?? "").toLowerCase();
  const like = String(osRelease.ID_LIKE ?? "")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  return id === "debian" || id === "ubuntu" || like.includes("debian") || like.includes("ubuntu");
}

export function parseDpkgStatus(text) {
  const packages = [];

  for (const stanza of text.split(/\n\s*\n/g)) {
    if (!stanza.trim()) continue;

    const fields = new Map();
    let currentKey = null;

    for (const line of stanza.split("\n")) {
      if (/^[ \t]/.test(line)) {
        if (currentKey !== null) {
          fields.set(currentKey, `${fields.get(currentKey) ?? ""}\n${line.trim()}`);
        }
        continue;
      }

      const separator = line.indexOf(":");
      if (separator <= 0) continue;
      currentKey = line.slice(0, separator);
      fields.set(currentKey, line.slice(separator + 1).trim());
    }

    const status = fields.get("Status");
    if (status !== "install ok installed") continue;

    const name = boundedText(fields.get("Package"), MAX_NAME);
    const version = boundedText(fields.get("Version"), MAX_VERSION);
    const architecture = boundedText(fields.get("Architecture"), MAX_ARCH);
    if (!name || !version || !architecture) continue;

    packages.push({
      name,
      version,
      architecture,
      essential: String(fields.get("Essential") ?? "").toLowerCase() === "yes",
    });
  }

  return packages;
}

export async function collectPackageObservation({
  readText = async (path) => readFile(path, "utf8"),
} = {}) {
  const capturedAt = new Date().toISOString();

  if (process.platform !== "linux") {
    return {
      schemaVersion: "phios.package-observation.v1",
      source: "dpkg-status-file",
      capturedAt,
      availability: "unavailable",
      reason: "non-linux-host",
      adapter: "debian-dpkg-status",
      packageLimit: PACKAGE_LIMIT,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      distro: null,
      totalInstalledPackageCount: 0,
      packages: [],
    };
  }

  let osReleaseText;
  try {
    osReleaseText = await readText(OS_RELEASE_PATH);
  } catch {
    return {
      schemaVersion: "phios.package-observation.v1",
      source: "dpkg-status-file",
      capturedAt,
      availability: "unavailable",
      reason: "os-release-unavailable",
      adapter: "debian-dpkg-status",
      packageLimit: PACKAGE_LIMIT,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      distro: null,
      totalInstalledPackageCount: 0,
      packages: [],
    };
  }

  const osRelease = parseOsRelease(osReleaseText);
  const distro = {
    id: boundedText(String(osRelease.ID ?? "unknown"), 64) || "unknown",
    name:
      boundedText(String(osRelease.PRETTY_NAME ?? osRelease.NAME ?? osRelease.ID ?? "Linux"), 160) ||
      "Linux",
  };

  if (!distroSupportsDpkg(osRelease)) {
    return {
      schemaVersion: "phios.package-observation.v1",
      source: "dpkg-status-file",
      capturedAt,
      availability: "unavailable",
      reason: "unsupported-package-database",
      adapter: "debian-dpkg-status",
      packageLimit: PACKAGE_LIMIT,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      distro,
      totalInstalledPackageCount: 0,
      packages: [],
    };
  }

  let statusText;
  try {
    statusText = await readText(DPKG_STATUS_PATH);
  } catch {
    return {
      schemaVersion: "phios.package-observation.v1",
      source: "dpkg-status-file",
      capturedAt,
      availability: "unavailable",
      reason: "package-database-unavailable",
      adapter: "debian-dpkg-status",
      packageLimit: PACKAGE_LIMIT,
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      distro,
      totalInstalledPackageCount: 0,
      packages: [],
    };
  }

  const installed = parseDpkgStatus(statusText).sort(
    (a, b) =>
      Number(b.essential) - Number(a.essential) ||
      a.name.localeCompare(b.name) ||
      a.architecture.localeCompare(b.architecture),
  );

  return {
    schemaVersion: "phios.package-observation.v1",
    source: "dpkg-status-file",
    capturedAt: new Date().toISOString(),
    availability: "available",
    reason: null,
    adapter: "debian-dpkg-status",
    packageLimit: PACKAGE_LIMIT,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    distro,
    totalInstalledPackageCount: installed.length,
    packages: installed.slice(0, PACKAGE_LIMIT),
  };
}

async function main() {
  const observation = await collectPackageObservation();

  if (process.argv.includes("--require-debian") && observation.availability !== "available") {
    throw new Error(`package observation unavailable: ${observation.reason}`);
  }
  if (process.argv.includes("--check") || process.argv.includes("--require-debian")) {
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
