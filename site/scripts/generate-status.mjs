import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repoRoot = fileURLToPath(new URL("../..", import.meta.url));
const siteRoot = fileURLToPath(new URL("..", import.meta.url));

function git(args) {
  return execFileSync("git", args, {
    cwd: repoRoot,
    encoding: "utf8",
  }).trim();
}

function sectionLastVersion(markdown, startHeading, endHeading) {
  const start = markdown.indexOf(startHeading);
  if (start < 0) return "unknown";
  const end = endHeading ? markdown.indexOf(endHeading, start + startHeading.length) : markdown.length;
  const section = markdown.slice(start, end < 0 ? markdown.length : end);
  const versions = [...section.matchAll(/\| v([0-9.]+) \|/g)].map((match) => `v${match[1]}`);
  return versions.at(-1) ?? "unknown";
}

const history = readFileSync(path.join(repoRoot, "docs", "VERSION_HISTORY.md"), "utf8");
const commit = process.env.GITHUB_SHA || git(["rev-parse", "HEAD"]);
const commitDate = git(["show", "-s", "--format=%cI", commit]);
const mergedSubject = git(["log", "--merges", "-n", "1", "--pretty=%s"]);
const mergedMatch = mergedSubject.match(/#(\d+)/);

const status = {
  repository: "MichaelWave369/PhiOS",
  commit,
  commitShort: commit.slice(0, 9),
  commitDate,
  latestMergedPr: mergedMatch ? Number(mergedMatch[1]) : null,
  siteBuild: "verified",
  versionLines: {
    appPlatform: sectionLastVersion(history, "## App Platform", "## Spine"),
    spine: sectionLastVersion(history, "## Spine", "## PhiReflex"),
    phiReflex: sectionLastVersion(history, "## PhiReflex", "## Core reasoning"),
    hardening: sectionLastVersion(history, "## Research-hardening lineage", "## Why the old"),
  },
  source: "generated from the exact repository checkout used for this Pages build",
  authority: "none",
};

writeFileSync(
  path.join(siteRoot, "public", "project-status.json"),
  `${JSON.stringify(status, null, 2)}\n`,
);

console.log(`Wrote project-status.json for ${status.commitShort}`);
