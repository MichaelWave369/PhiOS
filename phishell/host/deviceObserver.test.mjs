import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { collectDeviceObservation } from "./deviceObserver.mjs";

test(
  "device observer exposes bounded read-only sysfs metadata",
  { skip: process.platform !== "linux" },
  async () => {
    const observation = await collectDeviceObservation();

    assert.equal(observation.schemaVersion, "phios.device-observation.v1");
    assert.equal(observation.source, "linux-sysfs-bounded");
    assert.equal(observation.availability, "available");
    assert.equal(observation.readOnly, true);
    assert.equal(observation.executionAuthority, false);
    assert.equal(observation.effectPerformed, false);
    assert.ok(observation.cpuTopology.logicalCpuCount >= 1);
    assert.ok(observation.block.length <= 16);
    assert.ok(observation.network.length <= 16);
    assert.ok(observation.pci.length <= 16);
    assert.ok(observation.usb.length <= 16);
    assert.ok(observation.drm.length <= 8);
    assert.ok(observation.power.length <= 8);

    for (const row of observation.network) {
      assert.deepEqual(Object.keys(row).sort(), [
        "deviceId",
        "name",
        "operState",
        "type",
        "vendorId",
      ]);
      assert.equal("mac" in row, false);
      assert.equal("address" in row, false);
    }

    for (const row of observation.usb) {
      assert.equal("serial" in row, false);
    }
  },
);

test("device observer source contains no device mutation or sensitive identity reads", async () => {
  const source = await readFile(new URL("./deviceObserver.mjs", import.meta.url), "utf8");

  for (const forbidden of [
    "writeFile",
    "appendFile",
    "chmod",
    "chown",
    "node:child_process",
    "exec(",
    "spawn(",
    "/serial",
    "/address",
    "/driver/unbind",
    "/driver/bind",
    "/remove",
    "/rescan",
    "/power/control",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});

test(
  "device observer can project a synthetic sysfs tree without arbitrary path requests",
  { skip: process.platform !== "linux" },
  async () => {
    const lists = new Map([
      ["/sys", ["class", "bus", "devices"]],
      ["/sys/devices/system/cpu", ["cpu0", "cpu1", "cpufreq"]],
      ["/sys/class/block", ["sda"]],
      ["/sys/class/net", ["eth0"]],
      ["/sys/bus/pci/devices", ["0000:00:01.0"]],
      ["/sys/bus/usb/devices", ["1-1"]],
      ["/sys/class/drm", ["card0", "card0-DP-1"]],
      ["/sys/class/power_supply", ["BAT0"]],
    ]);
    const files = new Map([
      ["/sys/devices/system/cpu/cpu0/topology/physical_package_id", "0\n"],
      ["/sys/devices/system/cpu/cpu0/topology/core_id", "0\n"],
      ["/sys/devices/system/cpu/cpu1/topology/physical_package_id", "0\n"],
      ["/sys/devices/system/cpu/cpu1/topology/core_id", "1\n"],
      ["/sys/class/block/sda/size", "2048\n"],
      ["/sys/class/block/sda/removable", "0\n"],
      ["/sys/class/block/sda/queue/rotational", "1\n"],
      ["/sys/class/block/sda/device/vendor", "TEST\n"],
      ["/sys/class/block/sda/device/model", "Disk\n"],
      ["/sys/class/net/eth0/type", "1\n"],
      ["/sys/class/net/eth0/operstate", "up\n"],
      ["/sys/class/net/eth0/device/vendor", "0x1234\n"],
      ["/sys/class/net/eth0/device/device", "0xabcd\n"],
      ["/sys/bus/pci/devices/0000:00:01.0/vendor", "0x1234\n"],
      ["/sys/bus/pci/devices/0000:00:01.0/device", "0xabcd\n"],
      ["/sys/bus/pci/devices/0000:00:01.0/class", "0x030000\n"],
      ["/sys/bus/usb/devices/1-1/idVendor", "046d\n"],
      ["/sys/bus/usb/devices/1-1/idProduct", "c534\n"],
      ["/sys/bus/usb/devices/1-1/bDeviceClass", "00\n"],
      ["/sys/bus/usb/devices/1-1/manufacturer", "Example\n"],
      ["/sys/bus/usb/devices/1-1/product", "Input Device\n"],
      ["/sys/class/drm/card0/device/vendor", "0x10de\n"],
      ["/sys/class/drm/card0/device/device", "0x1234\n"],
      ["/sys/class/power_supply/BAT0/type", "Battery\n"],
      ["/sys/class/power_supply/BAT0/manufacturer", "Example\n"],
      ["/sys/class/power_supply/BAT0/model_name", "Pack\n"],
    ]);

    const observation = await collectDeviceObservation({
      listNames: async (path) => {
        if (!lists.has(path)) throw new Error("missing list");
        return lists.get(path);
      },
      readText: async (path) => {
        if (!files.has(path)) throw new Error("missing file");
        return files.get(path);
      },
    });

    assert.equal(observation.cpuTopology.logicalCpuCount, 2);
    assert.equal(observation.cpuTopology.physicalCoreCount, 2);
    assert.equal(observation.block[0].sizeBytes, 1_048_576);
    assert.equal(observation.network[0].vendorId, "0x1234");
    assert.equal(observation.pci[0].classId, "0x030000");
    assert.equal(observation.usb[0].manufacturer, "Example");
    assert.equal(observation.drm[0].vendorId, "0x10de");
    assert.equal(observation.power[0].type, "Battery");
  },
);
