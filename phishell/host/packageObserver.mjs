import { readFile, readdir, open } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const DPKG_STATUS_PATH = "/var/lib/dpkg/status";
const OS_RELEASE_PATH = "/etc/os-release";
const PACKAGE_LIMIT = 64;
const MAX_NAME = 128;
const MAX_VERSION = 256;
const MAX_ARCH = 64;
const MAX_DESC_BYTES = 64 * 1024;

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

const PACMAN_LOCAL_PATH = "/var/lib/pacman/local";
const DATABASE_ENTRY_LIMIT = 20000;

export function parsePacmanDescription(text) {
  if (typeof text !== "string" || Buffer.byteLength(text) > MAX_DESC_BYTES) return null;
  const fields = new Map();
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (!["%NAME%", "%VERSION%", "%ARCH%"].includes(lines[i])) continue;
    if (fields.has(lines[i])) return null;
    fields.set(lines[i], lines[i + 1] ?? "");
  }
  const name = fields.get("%NAME%");
  const version = fields.get("%VERSION%");
  const architecture = fields.get("%ARCH%");
  if (!name || !/^[a-z0-9@+_.-]+$/.test(name) || name.length > MAX_NAME ||
      !version || version.length > MAX_VERSION || /[\x00-\x1f\x7f]/.test(version) ||
      !architecture || architecture.length > MAX_ARCH || !/^[a-z0-9_]+$/.test(architecture)) return null;
  // Pacman has no Debian Essential flag. Never infer importance from a name.
  return { name, version, architecture, essential: false };
}

async function readBoundedDescription(path) {
  const file = await open(path, "r");
  try {
    const buffer = Buffer.alloc(MAX_DESC_BYTES + 1);
    const { bytesRead } = await file.read(buffer, 0, buffer.length, 0);
    if (bytesRead > MAX_DESC_BYTES) throw new Error("package description too large");
    return buffer.subarray(0, bytesRead).toString("utf8");
  } finally { await file.close(); }
}

export async function collectPackageObservation({
  readText = async (path) => readFile(path, "utf8"),
  listPacmanEntries = async () => (await readdir(PACMAN_LOCAL_PATH, { withFileTypes: true }))
    .filter(entry => entry.isDirectory()).map(entry => entry.name),
  readPacmanText = readBoundedDescription,
} = {}) {
  const observation = {
    schemaVersion: "phios.package-observation.v1",
    source: "dpkg-status-file", capturedAt: new Date().toISOString(),
    availability: "unavailable", reason: "non-linux-host", adapter: "debian-dpkg-status",
    packageLimit: PACKAGE_LIMIT, readOnly: true, executionAuthority: false,
    effectPerformed: false, distro: null, totalInstalledPackageCount: 0, packages: [],
  };
  if (process.platform !== "linux") return observation;
  let osRelease;
  try { osRelease = parseOsRelease(await readText(OS_RELEASE_PATH)); }
  catch { return { ...observation, reason: "os-release-unavailable" }; }
  observation.distro = {
    id: boundedText(String(osRelease.ID ?? "unknown"), 64) || "unknown",
    name: boundedText(String(osRelease.PRETTY_NAME ?? osRelease.NAME ?? osRelease.ID ?? "Linux"), 160) || "Linux",
  };
  const family = [osRelease.ID, ...String(osRelease.ID_LIKE ?? "").split(/\s+/)];
  const usePacman = family.includes("arch");
  if (!usePacman && !distroSupportsDpkg(osRelease)) {
    return { ...observation, reason: "unsupported-package-database" };
  }
  if (usePacman) {
    observation.source = "pacman-local-desc";
    observation.adapter = "arch-pacman-local";
  }
  let installed;
  try {
    if (usePacman) {
      const entries = await listPacmanEntries();
      if (!Array.isArray(entries) || entries.length > DATABASE_ENTRY_LIMIT) throw new Error("database entry limit exceeded");
      installed = [];
      for (const entry of entries.sort()) {
        if (typeof entry !== "string" || !/^[a-zA-Z0-9@+_.:~-]{1,512}$/.test(entry) || [".", ".."].includes(entry)) {
          throw new Error("invalid database entry");
        }
        const pkg = parsePacmanDescription(await readPacmanText(`${PACMAN_LOCAL_PATH}/${entry}/desc`));
        if (!pkg) throw new Error("invalid package description");
        installed.push(pkg);
      }
    } else {
      installed = parseDpkgStatus(await readText(DPKG_STATUS_PATH));
    }
  } catch { return { ...observation, reason: "package-database-unavailable" }; }
  installed.sort((a, b) => Number(b.essential) - Number(a.essential) ||
    a.name.localeCompare(b.name) || a.architecture.localeCompare(b.architecture));
  return { ...observation, availability: "available", reason: null,
    capturedAt: new Date().toISOString(), totalInstalledPackageCount: installed.length,
    packages: installed.slice(0, PACKAGE_LIMIT) };
}

async function main() {
  const observation = await collectPackageObservation();

  if ((process.argv.includes("--require-debian") || process.argv.includes("--require-native")) && observation.availability !== "available") {
    throw new Error(`package observation unavailable: ${observation.reason}`);
  }
  if (process.argv.includes("--check") || process.argv.includes("--require-debian") || process.argv.includes("--require-native")) {
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
