import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  SERVICE_ALLOWLIST,
  collectSystemdServiceObservation,
} from "./serviceObserver.mjs";

function fakeBus(rows) {
  let disconnected = false;
  return {
    get disconnected() {
      return disconnected;
    },
    async getProxyObject(destination, path) {
      assert.equal(destination, "org.freedesktop.systemd1");
      assert.equal(path, "/org/freedesktop/systemd1");
      return {
        getInterface(name) {
          assert.equal(name, "org.freedesktop.systemd1.Manager");
          return {
            async ListUnits() {
              return rows;
            },
          };
        },
      };
    },
    disconnect() {
      disconnected = true;
    },
  };
}

test(
  "service observer projects only allowlisted service state",
  { skip: process.platform !== "linux" },
  async () => {
    const rows = [
      [
        "dbus.service",
        "D-Bus System Message Bus",
        "loaded",
        "active",
        "running",
        "",
        "/org/freedesktop/systemd1/unit/dbus_2eservice",
        0,
        "",
        "/",
      ],
      [
        "evil-unlisted.service",
        "Should never leave the adapter",
        "loaded",
        "active",
        "running",
        "",
        "/org/freedesktop/systemd1/unit/evil_2eservice",
        0,
        "",
        "/",
      ],
    ];
    const bus = fakeBus(rows);
    const observation = await collectSystemdServiceObservation({
      busFactory: () => bus,
      runtimePresent: async () => true,
    });

    assert.equal(observation.readOnly, true);
    assert.equal(observation.executionAuthority, false);
    assert.equal(observation.effectPerformed, false);
    assert.equal(observation.allowlistOnly, true);
    assert.equal(observation.availability, "available");
    assert.equal(bus.disconnected, true);
    assert.deepEqual(
      observation.services.map((service) => service.id),
      SERVICE_ALLOWLIST.map((service) => service.id),
    );
    assert.equal(
      observation.services.some((service) => service.unit === "evil-unlisted.service"),
      false,
    );

    const dbus = observation.services.find((service) => service.id === "dbus");
    assert.equal(dbus?.found, true);
    assert.equal(dbus?.activeState, "active");
    assert.equal(dbus?.subState, "running");
  },
);

test("service observer source exposes no mutating systemd method names", async () => {
  const source = await readFile(new URL("./serviceObserver.mjs", import.meta.url), "utf8");
  for (const forbidden of [
    "StartUnit",
    "StopUnit",
    "RestartUnit",
    "ReloadUnit",
    "EnableUnitFiles",
    "DisableUnitFiles",
    "MaskUnitFiles",
    "SetUnitProperties",
    "KillUnit",
    "ResetFailed",
    "LoadUnit(",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
  assert.equal(source.includes("ListUnits()"), true);
});

test("service allowlist is finite and contains no wildcard unit names", () => {
  assert.ok(SERVICE_ALLOWLIST.length > 0);
  assert.ok(SERVICE_ALLOWLIST.length <= 16);

  for (const service of SERVICE_ALLOWLIST) {
    assert.match(service.id, /^[a-z0-9-]+$/);
    for (const unit of service.units) {
      assert.match(unit, /^[A-Za-z0-9@_.-]+\.service$/);
      assert.equal(unit.includes("*"), false);
    }
  }
});
