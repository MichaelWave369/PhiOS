import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, extname, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { collectLinuxHostObservation } from "./linuxProbe.mjs";
import { assertValidHostObservation } from "./observationContract.mjs";
import { collectSystemdServiceObservation } from "./serviceObserver.mjs";
import { assertValidServiceObservation } from "./serviceObservationContract.mjs";
import { collectCurrentUserProcessObservation } from "./processObserver.mjs";
import { assertValidProcessObservation } from "./processObservationContract.mjs";
import { collectPackageObservation } from "./packageObserver.mjs";
import { assertValidPackageObservation } from "./packageObservationContract.mjs";
import { collectDeviceObservation } from "./deviceObserver.mjs";
import { assertValidDeviceObservation } from "./deviceObservationContract.mjs";
import { composeSystemStateReceipt } from "./systemStateComposer.mjs";
import { assertValidSystemStateReceipt } from "./systemStateContract.mjs";
import { fetchPersistentHistoryProjection } from "./persistentHistoryProxy.mjs";

const LOOPBACK_HOST = "127.0.0.1";
const DEFAULT_PORT = 3969;
const MODULE_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_DIST_DIR = resolve(MODULE_DIR, "../dist");

function jsonResponse(response, status, body) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "cross-origin-resource-policy": "same-origin",
    "referrer-policy": "no-referrer",
  });
  response.end(JSON.stringify(body));
}

function contentType(path) {
  switch (extname(path)) {
    case ".html":
      return "text/html; charset=utf-8";
    case ".js":
      return "text/javascript; charset=utf-8";
    case ".css":
      return "text/css; charset=utf-8";
    case ".svg":
      return "image/svg+xml";
    case ".png":
      return "image/png";
    case ".webp":
      return "image/webp";
    case ".ico":
      return "image/x-icon";
    default:
      return "application/octet-stream";
  }
}

function safeStaticPath(distDir, pathname) {
  const decoded = decodeURIComponent(pathname);
  if (decoded === "/" || decoded === "/index.html") {
    return resolve(distDir, "index.html");
  }
  if (!decoded.startsWith("/assets/")) return null;

  const candidate = resolve(distDir, `.${decoded}`);
  const root = resolve(distDir) + sep;
  return candidate.startsWith(root) ? candidate : null;
}

async function serveStatic(response, distDir, pathname) {
  const path = safeStaticPath(distDir, pathname);
  if (!path) return false;

  try {
    const body = await readFile(path);
    response.writeHead(200, {
      "content-type": contentType(path),
      "cache-control": pathname.startsWith("/assets/")
        ? "public, max-age=31536000, immutable"
        : "no-store",
      "x-content-type-options": "nosniff",
      "cross-origin-resource-policy": "same-origin",
      "referrer-policy": "no-referrer",
      "content-security-policy":
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    });
    response.end(body);
    return true;
  } catch {
    return false;
  }
}

export function createLocalObservationServer({
  port = DEFAULT_PORT,
  distDir = DEFAULT_DIST_DIR,
  serveShell = true,
  historyProjectionFetcher = fetchPersistentHistoryProjection,
} = {}) {
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    throw new Error("local observation port must be an integer between 0 and 65535");
  }

  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", `http://${LOOPBACK_HOST}`);

      if (request.method !== "GET") {
        response.setHeader("allow", "GET");
        jsonResponse(response, 405, {
          error: "method_not_allowed",
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
        });
        return;
      }

      if (url.pathname === "/api/v1/health") {
        jsonResponse(response, 200, {
          transportSchemaVersion: "phios.host-transport.v1",
          transport: "loopback-http",
          transportIdentity: "phishell-local-observer",
          localOnly: true,
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
          status: "ready",
        });
        return;
      }

      if (url.pathname === "/api/v1/host-observation") {
        const snapshot = assertValidHostObservation(await collectLinuxHostObservation());
        const servedAt = new Date().toISOString();
        const snapshotAgeMs = Math.max(0, Date.parse(servedAt) - Date.parse(snapshot.capturedAt));

        jsonResponse(response, 200, {
          transportSchemaVersion: "phios.host-transport.v1",
          transport: "loopback-http",
          transportIdentity: "phishell-local-observer",
          localOnly: true,
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
          servedAt,
          snapshotAgeMs,
          snapshot,
        });
        return;
      }

      if (url.pathname === "/api/v1/service-observation") {
        const observation = assertValidServiceObservation(
          await collectSystemdServiceObservation(),
        );
        const servedAt = new Date().toISOString();
        const snapshotAgeMs = Math.max(
          0,
          Date.parse(servedAt) - Date.parse(observation.capturedAt),
        );

        jsonResponse(response, 200, {
          transportSchemaVersion: "phios.service-transport.v1",
          transport: "loopback-http",
          transportIdentity: "phishell-local-observer",
          localOnly: true,
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
          servedAt,
          snapshotAgeMs,
          observation,
        });
        return;
      }

      if (url.pathname === "/api/v1/process-observation") {
        const observation = assertValidProcessObservation(
          await collectCurrentUserProcessObservation(),
        );
        const servedAt = new Date().toISOString();
        const snapshotAgeMs = Math.max(
          0,
          Date.parse(servedAt) - Date.parse(observation.capturedAt),
        );

        jsonResponse(response, 200, {
          transportSchemaVersion: "phios.process-transport.v1",
          transport: "loopback-http",
          transportIdentity: "phishell-local-observer",
          localOnly: true,
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
          servedAt,
          snapshotAgeMs,
          observation,
        });
        return;
      }

      if (url.pathname === "/api/v1/package-observation") {
        const observation = assertValidPackageObservation(await collectPackageObservation());
        const servedAt = new Date().toISOString();
        const snapshotAgeMs = Math.max(
          0,
          Date.parse(servedAt) - Date.parse(observation.capturedAt),
        );

        jsonResponse(response, 200, {
          transportSchemaVersion: "phios.package-transport.v1",
          transport: "loopback-http",
          transportIdentity: "phishell-local-observer",
          localOnly: true,
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
          servedAt,
          snapshotAgeMs,
          observation,
        });
        return;
      }

      if (url.pathname === "/api/v1/device-observation") {
        const observation = assertValidDeviceObservation(await collectDeviceObservation());
        const servedAt = new Date().toISOString();
        const snapshotAgeMs = Math.max(
          0,
          Date.parse(servedAt) - Date.parse(observation.capturedAt),
        );

        jsonResponse(response, 200, {
          transportSchemaVersion: "phios.device-transport.v1",
          transport: "loopback-http",
          transportIdentity: "phishell-local-observer",
          localOnly: true,
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
          servedAt,
          snapshotAgeMs,
          observation,
        });
        return;
      }

      if (url.pathname === "/api/v1/system-state") {
        const receipt = assertValidSystemStateReceipt(await composeSystemStateReceipt());
        const servedAt = new Date().toISOString();
        const snapshotAgeMs = Math.max(
          0,
          Date.parse(servedAt) - Date.parse(receipt.composedAt),
        );

        jsonResponse(response, 200, {
          transportSchemaVersion: "phios.system-state-transport.v1",
          transport: "loopback-http",
          transportIdentity: "phishell-local-observer",
          localOnly: true,
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
          servedAt,
          snapshotAgeMs,
          receipt,
        });
        return;
      }

      if (url.pathname === "/api/v1/persistent-history") {
        const historyEnvelope = await historyProjectionFetcher();
        if (!historyEnvelope) {
          jsonResponse(response, 503, {
            error: "persistent_history_unavailable",
            localOnly: true,
            readOnly: true,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, historyEnvelope);
        return;
      }

      if (serveShell && (await serveStatic(response, distDir, url.pathname))) {
        return;
      }

      jsonResponse(response, 404, {
        error: "not_found",
        readOnly: true,
        executionAuthority: false,
        effectPerformed: false,
      });
    } catch (error) {
      jsonResponse(response, 500, {
        error: "observation_failed",
        message: error instanceof Error ? error.message : "unknown observation error",
        readOnly: true,
        executionAuthority: false,
        effectPerformed: false,
      });
    }
  });

  return {
    host: LOOPBACK_HOST,
    port,
    server,
    async listen() {
      await new Promise((resolveListen, rejectListen) => {
        const onError = (error) => rejectListen(error);
        server.once("error", onError);
        server.listen(port, LOOPBACK_HOST, () => {
          server.off("error", onError);
          resolveListen();
        });
      });
      const address = server.address();
      if (!address || typeof address === "string") {
        throw new Error("local observation transport did not expose a TCP address");
      }
      if (address.address !== LOOPBACK_HOST) {
        await this.close();
        throw new Error("local observation transport escaped the IPv4 loopback boundary");
      }
      return { host: address.address, port: address.port };
    },
    async close() {
      if (!server.listening) return;
      await new Promise((resolveClose, rejectClose) => {
        server.close((error) => (error ? rejectClose(error) : resolveClose()));
      });
    },
  };
}

function cliPort() {
  const raw = process.env.PHISHELL_OBSERVATION_PORT;
  if (raw === undefined) return DEFAULT_PORT;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("PHISHELL_OBSERVATION_PORT must be an integer from 1024 to 65535");
  }
  return port;
}

async function main() {
  const transport = createLocalObservationServer({ port: cliPort() });
  const address = await transport.listen();
  process.stdout.write(
    `PhiShell local observation transport: http://${address.host}:${address.port}\n`,
  );

  const shutdown = async () => {
    await transport.close();
    process.exitCode = 0;
  };
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
}

const invokedDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
