import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  collectPackageObservation,
  parseDpkgStatus,
  parseOsRelease,
} from "./packageObserver.mjs";

test("dpkg parser keeps installed package identity only", () => {
  const parsed = parseDpkgStatus(`
Package: alpha
Status: install ok installed
Architecture: amd64
Version: 1.2.3
Essential: yes
Description: This must not leave the parser.

Package: beta
Status: deinstall ok config-files
Architecture: all
Version: 9.9.9

Package: gamma
Status: install ok installed
Architecture: all
Version: 4.5.6
Maintainer: Somebody <person@example.invalid>
`);

  assert.deepEqual(parsed, [
    { name: "alpha", version: "1.2.3", architecture: "amd64", essential: true },
    { name: "gamma", version: "4.5.6", architecture: "all", essential: false },
  ]);
});

test("os-release parser recognizes quoted Debian-family metadata", () => {
  const parsed = parseOsRelease('ID=ubuntu\nID_LIKE="debian"\nPRETTY_NAME="Ubuntu Test"\n');
  assert.equal(parsed.ID, "ubuntu");
  assert.equal(parsed.ID_LIKE, "debian");
  assert.equal(parsed.PRETTY_NAME, "Ubuntu Test");
});

test(
  "package observer reads distro metadata and dpkg database without package-manager execution",
  { skip: process.platform !== "linux" },
  async () => {
    const files = new Map([
      ["/etc/os-release", 'ID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu Test"\n'],
      [
        "/var/lib/dpkg/status",
        `Package: zeta
Status: install ok installed
Architecture: amd64
Version: 2.0

Package: base-files
Status: install ok installed
Architecture: amd64
Version: 1.0
Essential: yes
`,
      ],
    ]);

    const observation = await collectPackageObservation({
      readText: async (path) => {
        if (!files.has(path)) throw new Error("unexpected path");
        return files.get(path);
      },
    });

    assert.equal(observation.availability, "available");
    assert.equal(observation.readOnly, true);
    assert.equal(observation.executionAuthority, false);
    assert.equal(observation.effectPerformed, false);
    assert.equal(observation.packageLimit, 64);
    assert.equal(observation.totalInstalledPackageCount, 2);
    assert.equal(observation.packages[0].name, "base-files");
    assert.deepEqual(Object.keys(observation.packages[0]).sort(), [
      "architecture",
      "essential",
      "name",
      "version",
    ]);
  },
);

test("package observer source contains no package-manager execution surface", async () => {
  const source = await readFile(new URL("./packageObserver.mjs", import.meta.url), "utf8");

  for (const forbidden of [
    "node:child_process",
    "exec(",
    "execFile(",
    "spawn(",
    "sudo ",
    "apt ",
    "apt-get",
    "dpkg ",
    "rpm ",
    "pacman ",
    "dnf ",
    "zypper ",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }

  assert.equal(source.includes('"/var/lib/dpkg/status"'), true);
  assert.equal(source.includes('"/etc/os-release"'), true);
});
