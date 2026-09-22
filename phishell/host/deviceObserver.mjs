import { readdir, readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const LIMITS = Object.freeze({
  block: 16,
  network: 16,
  pci: 16,
  usb: 16,
  drm: 8,
  power: 8,
});

const SYSFS_ROOT = "/sys";

function boundedText(value, max = 160) {
  if (typeof value !== "string") return null;
  const normalized = value.replace(/[\r\n\t]/g, " ").trim();
  if (!normalized) return null;
  return normalized.length <= max ? normalized : normalized.slice(0, max);
}

function boundedName(value, max = 128) {
  const text = boundedText(value, max);
  if (!text || !/^[A-Za-z0-9_.:@+-]+$/.test(text)) return null;
  return text;
}

function normalizedHex(value, digits = 8) {
  const text = boundedText(value, digits + 2);
  if (!text) return null;
  const normalized = text.toLowerCase();
  if (!/^0x[0-9a-f]+$/.test(normalized) && !/^[0-9a-f]+$/.test(normalized)) return null;
  return normalized.startsWith("0x") ? normalized : `0x${normalized}`;
}

function nonNegativeInteger(value) {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

async function defaultList(path) {
  return readdir(path);
}

async function defaultRead(path) {
  return readFile(path, "utf8");
}

async function optionalText(readText, path, max = 160) {
  try {
    return boundedText(await readText(path), max);
  } catch {
    return null;
  }
}

async function optionalName(readText, path, max = 128) {
  try {
    return boundedName(await readText(path), max);
  } catch {
    return null;
  }
}

async function listSafe(listNames, path) {
  try {
    const names = await listNames(path);
    return names
      .map((name) => boundedName(name, 128))
      .filter((name) => name !== null)
      .sort((a, b) => a.localeCompare(b));
  } catch {
    return [];
  }
}

async function collectCpuTopology(listNames, readText) {
  const names = (await listSafe(listNames, `${SYSFS_ROOT}/devices/system/cpu`)).filter((name) =>
    /^cpu\d+$/.test(name),
  );

  const coreKeys = new Set();
  const packageIds = new Set();

  for (const name of names) {
    const base = `${SYSFS_ROOT}/devices/system/cpu/${name}/topology`;
    const packageId = await optionalText(readText, `${base}/physical_package_id`, 32);
    const coreId = await optionalText(readText, `${base}/core_id`, 32);

    if (packageId !== null) packageIds.add(packageId);
    if (packageId !== null && coreId !== null) coreKeys.add(`${packageId}:${coreId}`);
  }

  return {
    logicalCpuCount: names.length,
    physicalPackageCount: packageIds.size,
    physicalCoreCount: coreKeys.size,
  };
}

async function collectBlock(listNames, readText) {
  const names = (await listSafe(listNames, `${SYSFS_ROOT}/class/block`)).slice(0, LIMITS.block * 4);
  const rows = [];

  for (const name of names) {
    if (rows.length >= LIMITS.block) break;

    const base = `${SYSFS_ROOT}/class/block/${name}`;
    const sectorsText = await optionalText(readText, `${base}/size`, 32);
    const sectors = sectorsText === null ? null : nonNegativeInteger(sectorsText);
    const sizeBytes =
      sectors === null || sectors > Math.floor(Number.MAX_SAFE_INTEGER / 512)
        ? null
        : sectors * 512;

    const removable = (await optionalText(readText, `${base}/removable`, 8)) === "1";
    const rotationalText = await optionalText(readText, `${base}/queue/rotational`, 8);
    const rotational =
      rotationalText === null ? null : rotationalText === "1" ? true : rotationalText === "0" ? false : null;

    rows.push({
      name,
      sizeBytes,
      removable,
      rotational,
      vendor: await optionalText(readText, `${base}/device/vendor`, 80),
      model: await optionalText(readText, `${base}/device/model`, 120),
    });
  }

  return rows;
}

async function collectNetwork(listNames, readText) {
  const names = (await listSafe(listNames, `${SYSFS_ROOT}/class/net`)).slice(0, LIMITS.network);
  const rows = [];

  for (const name of names) {
    const base = `${SYSFS_ROOT}/class/net/${name}`;
    const typeText = await optionalText(readText, `${base}/type`, 16);

    rows.push({
      name,
      type: typeText === null ? null : nonNegativeInteger(typeText),
      operState: await optionalText(readText, `${base}/operstate`, 32),
      vendorId: normalizedHex(await optionalText(readText, `${base}/device/vendor`, 16) ?? ""),
      deviceId: normalizedHex(await optionalText(readText, `${base}/device/device`, 16) ?? ""),
    });
  }

  return rows;
}

async function collectPci(listNames, readText) {
  const names = (await listSafe(listNames, `${SYSFS_ROOT}/bus/pci/devices`)).slice(0, LIMITS.pci);
  const rows = [];

  for (const name of names) {
    const base = `${SYSFS_ROOT}/bus/pci/devices/${name}`;
    const vendorId = normalizedHex(await optionalText(readText, `${base}/vendor`, 16) ?? "");
    const deviceId = normalizedHex(await optionalText(readText, `${base}/device`, 16) ?? "");
    const classId = normalizedHex(await optionalText(readText, `${base}/class`, 16) ?? "");
    if (!vendorId || !deviceId || !classId) continue;

    rows.push({ slot: name, vendorId, deviceId, classId });
  }

  return rows;
}

async function collectUsb(listNames, readText) {
  const names = (await listSafe(listNames, `${SYSFS_ROOT}/bus/usb/devices`)).slice(0, LIMITS.usb * 3);
  const rows = [];

  for (const name of names) {
    if (rows.length >= LIMITS.usb) break;

    const base = `${SYSFS_ROOT}/bus/usb/devices/${name}`;
    const vendorRaw = await optionalText(readText, `${base}/idVendor`, 16);
    const productRaw = await optionalText(readText, `${base}/idProduct`, 16);
    if (!vendorRaw || !productRaw) continue;

    const vendorId = normalizedHex(vendorRaw);
    const productId = normalizedHex(productRaw);
    if (!vendorId || !productId) continue;

    rows.push({
      pathId: name,
      vendorId,
      productId,
      deviceClass: normalizedHex(await optionalText(readText, `${base}/bDeviceClass`, 16) ?? ""),
      manufacturer: await optionalText(readText, `${base}/manufacturer`, 120),
      product: await optionalText(readText, `${base}/product`, 120),
    });
  }

  return rows;
}

async function collectDrm(listNames, readText) {
  const names = (await listSafe(listNames, `${SYSFS_ROOT}/class/drm`))
    .filter((name) => /^card\d+$/.test(name))
    .slice(0, LIMITS.drm);
  const rows = [];

  for (const name of names) {
    const base = `${SYSFS_ROOT}/class/drm/${name}/device`;
    rows.push({
      name,
      vendorId: normalizedHex(await optionalText(readText, `${base}/vendor`, 16) ?? ""),
      deviceId: normalizedHex(await optionalText(readText, `${base}/device`, 16) ?? ""),
    });
  }

  return rows;
}

async function collectPower(listNames, readText) {
  const names = (await listSafe(listNames, `${SYSFS_ROOT}/class/power_supply`)).slice(0, LIMITS.power);
  const rows = [];

  for (const name of names) {
    const base = `${SYSFS_ROOT}/class/power_supply/${name}`;
    rows.push({
      name,
      type: await optionalText(readText, `${base}/type`, 64),
      manufacturer: await optionalText(readText, `${base}/manufacturer`, 120),
      model: await optionalText(readText, `${base}/model_name`, 120),
    });
  }

  return rows;
}

export async function collectDeviceObservation({
  listNames = defaultList,
  readText = defaultRead,
} = {}) {
  const capturedAt = new Date().toISOString();

  if (process.platform !== "linux") {
    return {
      schemaVersion: "phios.device-observation.v1",
      source: "linux-sysfs-bounded",
      capturedAt,
      availability: "unavailable",
      reason: "non-linux-host",
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      limits: LIMITS,
      cpuTopology: { logicalCpuCount: 0, physicalPackageCount: 0, physicalCoreCount: 0 },
      block: [],
      network: [],
      pci: [],
      usb: [],
      drm: [],
      power: [],
    };
  }

  let rootNames;
  try {
    rootNames = await listNames(SYSFS_ROOT);
  } catch {
    return {
      schemaVersion: "phios.device-observation.v1",
      source: "linux-sysfs-bounded",
      capturedAt,
      availability: "unavailable",
      reason: "sysfs-unavailable",
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
      limits: LIMITS,
      cpuTopology: { logicalCpuCount: 0, physicalPackageCount: 0, physicalCoreCount: 0 },
      block: [],
      network: [],
      pci: [],
      usb: [],
      drm: [],
      power: [],
    };
  }

  if (!Array.isArray(rootNames)) {
    throw new Error("sysfs root listing must be an array");
  }

  const [cpuTopology, block, network, pci, usb, drm, power] = await Promise.all([
    collectCpuTopology(listNames, readText),
    collectBlock(listNames, readText),
    collectNetwork(listNames, readText),
    collectPci(listNames, readText),
    collectUsb(listNames, readText),
    collectDrm(listNames, readText),
    collectPower(listNames, readText),
  ]);

  return {
    schemaVersion: "phios.device-observation.v1",
    source: "linux-sysfs-bounded",
    capturedAt: new Date().toISOString(),
    availability: "available",
    reason: null,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    limits: LIMITS,
    cpuTopology,
    block,
    network,
    pci,
    usb,
    drm,
    power,
  };
}

async function main() {
  const observation = await collectDeviceObservation();
  if (process.argv.includes("--require-linux") && observation.availability !== "available") {
    throw new Error(`device observation unavailable: ${observation.reason}`);
  }
  if (process.argv.includes("--check") || process.argv.includes("--require-linux")) return;

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
