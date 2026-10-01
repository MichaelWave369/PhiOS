import { createHash } from "node:crypto";
import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");

// Record actual Rollup chunk participants before npm pruning removes build
// inputs. Virtual Vite runtime helpers retain their actual supplier identity.
export function bundledInventory() {
  return {
    name: "phios-bundled-inventory",
    enforce: "post",
    writeBundle(options, bundle) {
      const root = realpathSync(join(process.cwd(), "node_modules"));
      const output = resolve(options.dir ?? "dist");
      const packages = new Map();
      const chunks = [];
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== "chunk") continue;
        if (isAbsolute(chunk.fileName) || chunk.fileName.split("/").includes("..")) throw new Error("Unsafe chunk path");
        const bytes = readFileSync(join(output, chunk.fileName));
        chunks.push({ filename: chunk.fileName, sha256: sha(bytes), size: bytes.length });
        for (const id of Object.keys(chunk.modules)) {
          const virtual = id.startsWith("\0vite/");
          const clean = id.replace(/^\0/, "").split("?", 1)[0];
          let path;
          let actual;
          if (virtual) path = join(root, "vite");
          else {
            if (!isAbsolute(clean) || !existsSync(clean)) continue;
            actual = realpathSync(clean);
            if (!actual.startsWith(root + sep)) continue;
            path = dirname(actual);
          }
          while (path.startsWith(root + sep) && !existsSync(join(path, "package.json"))) path = dirname(path);
          if (!path.startsWith(root + sep)) throw new Error("Bundled supplier identity missing");
          const metadata = readFileSync(join(path, "package.json"));
          const info = JSON.parse(metadata);
          if (typeof info.name !== "string" || typeof info.version !== "string") throw new Error("Bundled package identity missing");
          const origin = relative(root, path).split(sep).join("/");
          if (!packages.has(origin)) packages.set(origin, { name: info.name, version: info.version,
            license: typeof info.license === "string" ? info.license : null,
            package_json_sha256: sha(metadata), package_path: "node_modules/" + origin,
            modules: [], notices: [], _path: path });
          packages.get(origin).modules.push({ id: virtual ? clean : relative(path, actual).split(sep).join("/"),
            chunk: chunk.fileName, role: virtual ? "injected-runtime-helper" : "chunk-module" });
        }
      }
      if (packages.size === 0 || packages.size > 2000) throw new Error("Bounded nonempty bundled inventory required");
      mkdirSync(join(output, "bundled-notices"), { recursive: true });
      const rows = [...packages.values()].sort((a, b) => a.package_path.localeCompare(b.package_path));
      for (const row of rows) {
        for (const name of readdirSync(row._path).sort()) {
          if (!/license|copying|notice|copyright/i.test(name)) continue;
          const target = realpathSync(join(row._path, name));
          if (!target.startsWith(root + sep)) throw new Error("Notice escaped dependency root");
          const info = lstatSync(target);
          if (!info.isFile()) continue;
          if (info.size > 1024 * 1024) throw new Error("Bundled notice exceeds its bound");
          const bytes = readFileSync(target);
          const digest = sha(bytes);
          const filename = "bundled-notices/" + digest + ".txt";
          writeFileSync(join(output, filename), bytes);
          row.notices.push({ filename, original_name: name, sha256: digest, size: bytes.length });
        }
        row.modules.sort((a, b) => a.chunk.localeCompare(b.chunk) || a.id.localeCompare(b.id));
        delete row._path;
      }
      writeFileSync(join(output, "bundled-js-inventory.json"), JSON.stringify({
        schema_version: "phios.phishell-bundle.v1", packages: rows,
        chunks: chunks.sort((a, b) => a.filename.localeCompare(b.filename)),
        license_compliance_reviewed: false }, null, 2) + "\n");
    },
  };
}
