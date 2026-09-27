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
import { fetchHistoryComparison } from "./historyComparisonProxy.mjs";
import { fetchCuriosityProjection } from "./curiosityProjectionProxy.mjs";
import {
  applyGhostWalkAction,
  fetchGhostWalkStatus,
  validateGhostWalkActionPayload,
} from "./ghostWalkControlProxy.mjs";
import {
  applyGhostWalkOperatorEdit,
  fetchGhostWalkOperatorNote,
  validateGhostWalkOperatorEditPayload,
} from "./ghostWalkOperatorLogProxy.mjs";
import {
  applyGhostWalkAcceptedIntentMutation,
  fetchGhostWalkAcceptedIntent,
  validateGhostWalkAcceptedIntentMutationPayload,
} from "./ghostWalkAcceptedIntentProxy.mjs";
import {
  fetchGhostWalkPolicyAdmission,
  recordGhostWalkPolicyAdmission,
  validateGhostWalkPolicyRecordPayload,
} from "./ghostWalkPolicyAdmissionProxy.mjs";
import {
  createGhostWalkAuthorityRequest,
  fetchGhostWalkAuthorityRequestStatus,
  validateGhostWalkAuthorityRequestCreatePayload,
} from "./ghostWalkAuthorityRequestProxy.mjs";
import {
  createGhostWalkExecutableBinding,
  fetchGhostWalkAuthorizationConsole,
  issueGhostWalkActionLease,
  recordGhostWalkAuthorizationDecision,
  validateAuthorizationDecisionPayload,
  validateBindingCreatePayload,
  validateLeaseIssuePayload,
} from "./ghostWalkAuthorizationConsoleProxy.mjs";
import {
  createPersistRequest,
  fetchBrokerHealth,
  fetchPersistRequest,
} from "./curiosityAuthorityProxy.mjs";
import { readBoundedJsonObject } from "./boundedJsonBody.mjs";
import {
  validateCuriosityPersistRequestId,
  validateCuriosityPersistRequestPayload,
} from "./curiosityDoorbellContract.mjs";

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
  historyComparisonFetcher = fetchHistoryComparison,
  curiosityProjectionFetcher = fetchCuriosityProjection,
  curiosityAuthorityHealthFetcher = fetchBrokerHealth,
  curiosityPersistRequestCreator = createPersistRequest,
  curiosityPersistRequestFetcher = fetchPersistRequest,
  ghostWalkStatusFetcher = fetchGhostWalkStatus,
  ghostWalkActionApplier = applyGhostWalkAction,
  ghostWalkOperatorNoteFetcher = fetchGhostWalkOperatorNote,
  ghostWalkOperatorEditApplier = applyGhostWalkOperatorEdit,
  ghostWalkAcceptedIntentFetcher = fetchGhostWalkAcceptedIntent,
  ghostWalkAcceptedIntentMutator = applyGhostWalkAcceptedIntentMutation,
  ghostWalkPolicyAdmissionFetcher = fetchGhostWalkPolicyAdmission,
  ghostWalkPolicyAdmissionRecorder = recordGhostWalkPolicyAdmission,
  ghostWalkAuthorityRequestFetcher = fetchGhostWalkAuthorityRequestStatus,
  ghostWalkAuthorityRequestCreator = createGhostWalkAuthorityRequest,
  ghostWalkAuthorizationConsoleFetcher =
    fetchGhostWalkAuthorizationConsole,
  ghostWalkAuthorizationDecisionRecorder =
    recordGhostWalkAuthorizationDecision,
  ghostWalkExecutableBindingCreator =
    createGhostWalkExecutableBinding,
  ghostWalkActionLeaseIssuer = issueGhostWalkActionLease,
} = {}) {
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    throw new Error("local observation port must be an integer between 0 and 65535");
  }

  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", `http://${LOOPBACK_HOST}`);

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/ghostwalk/authorization-console/decisions"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 8192 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_authorization_decision_body",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!validateAuthorizationDecisionPayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_authorization_decision_request",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        const result = await ghostWalkAuthorizationDecisionRecorder(payload);
        if (result?.kind === "conflict") {
          jsonResponse(response, 409, {
            error: "ghostwalk_authorization_decision_conflict",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "applied") {
          jsonResponse(response, 503, {
            error: "ghostwalk_authorization_console_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/ghostwalk/authorization-console/bindings"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 8192 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_binding_body",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!validateBindingCreatePayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_binding_request",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        const result = await ghostWalkExecutableBindingCreator(payload);
        if (result?.kind === "conflict") {
          jsonResponse(response, 409, {
            error: "ghostwalk_binding_conflict",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "applied") {
          jsonResponse(response, 503, {
            error: "ghostwalk_authorization_console_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/ghostwalk/authorization-console/leases"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 8192 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_lease_body",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!validateLeaseIssuePayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_lease_request",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        const result = await ghostWalkActionLeaseIssuer(payload);
        if (result?.kind === "conflict") {
          jsonResponse(response, 409, {
            error: "ghostwalk_lease_conflict",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "applied") {
          jsonResponse(response, 503, {
            error: "ghostwalk_authorization_console_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/ghostwalk/authority-request/requests"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 8192 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_authority_request_body",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        if (!validateGhostWalkAuthorityRequestCreatePayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_authority_request_create",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const result = await ghostWalkAuthorityRequestCreator(payload);
        if (result?.kind === "conflict") {
          jsonResponse(response, 409, {
            error: "ghostwalk_authority_request_conflict",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "created") {
          jsonResponse(response, 503, {
            error: "ghostwalk_authority_request_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/ghostwalk/policy-admission/evaluations"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 8192 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_policy_admission_body",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        if (!validateGhostWalkPolicyRecordPayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_policy_admission_request",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const result = await ghostWalkPolicyAdmissionRecorder(payload);
        if (result?.kind === "conflict") {
          jsonResponse(response, 409, {
            error: "ghostwalk_policy_admission_conflict",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "recorded") {
          jsonResponse(response, 503, {
            error: "ghostwalk_policy_admission_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/ghostwalk/accepted-intent/revisions"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 8192 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_accepted_intent_body",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        if (!validateGhostWalkAcceptedIntentMutationPayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_accepted_intent_request",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const result = await ghostWalkAcceptedIntentMutator(payload);
        if (result?.kind === "conflict") {
          jsonResponse(response, 409, {
            error: "ghostwalk_accepted_intent_conflict",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "applied") {
          jsonResponse(response, 503, {
            error: "ghostwalk_accepted_intent_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/ghostwalk/operator-log/revisions"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 32768 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_operator_edit_body",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        if (!validateGhostWalkOperatorEditPayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_operator_edit_request",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const result = await ghostWalkOperatorEditApplier(payload);
        if (result?.kind === "conflict") {
          jsonResponse(response, 409, {
            error: "ghostwalk_operator_edit_conflict",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "applied") {
          jsonResponse(response, 503, {
            error: "ghostwalk_operator_editor_unavailable",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/ghostwalk/actions"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 8192 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_control_body",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        if (!validateGhostWalkActionPayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_control_request",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const outcome = await ghostWalkActionApplier(payload);
        if (!outcome) {
          jsonResponse(response, 503, {
            error: "ghostwalk_control_unavailable",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, outcome);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/curiosity/persist-requests"
      ) {
        let payload;
        try {
          payload = await readBoundedJsonObject(request, { maxBytes: 65536 });
        } catch {
          jsonResponse(response, 400, {
            error: "invalid_curiosity_persist_request_body",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        if (!validateCuriosityPersistRequestPayload(payload)) {
          jsonResponse(response, 400, {
            error: "invalid_curiosity_persist_request",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const created = await curiosityPersistRequestCreator(payload);
        if (!created) {
          jsonResponse(response, 503, {
            error: "curiosity_authority_broker_unavailable",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 201, created);
        return;
      }

      if (
        request.method === "POST" &&
        url.pathname === "/api/v1/curiosity/artifacts"
      ) {
        jsonResponse(response, 410, {
          error: "legacy_curiosity_persist_endpoint_retired",
          reason:
            "Use the governed Curiosity persistence-request handshake.",
          operationalAuthority: false,
          actionAuthority: false,
          executionAuthority: false,
          effectPerformed: false,
        });
        return;
      }

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

      if (
        url.pathname === "/api/v1/ghostwalk/authorization-console"
      ) {
        const keys = [...url.searchParams.keys()];
        const target = url.searchParams.get("target");
        if (
          keys.length !== 1 ||
          keys[0] !== "target" ||
          typeof target !== "string" ||
          !/^[0-9a-f]{64}$/.test(target)
        ) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_authorization_console_request",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        const result = await ghostWalkAuthorizationConsoleFetcher(target);
        if (!result || result.kind !== "found") {
          jsonResponse(response, 503, {
            error: "ghostwalk_authorization_console_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (url.pathname === "/api/v1/ghostwalk/authority-request") {
        const keys = [...url.searchParams.keys()];
        const target = url.searchParams.get("target");
        if (
          keys.length !== 1 ||
          keys[0] !== "target" ||
          typeof target !== "string" ||
          !/^[0-9a-f]{64}$/.test(target)
        ) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_authority_request_status",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const result = await ghostWalkAuthorityRequestFetcher(target);
        if (result?.kind === "not_ready") {
          jsonResponse(response, 404, {
            error: "ghostwalk_authority_request_not_ready",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "found") {
          jsonResponse(response, 503, {
            error: "ghostwalk_authority_request_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (url.pathname === "/api/v1/ghostwalk/policy-admission") {
        const keys = [...url.searchParams.keys()];
        const target = url.searchParams.get("target");
        if (
          keys.length !== 1 ||
          keys[0] !== "target" ||
          typeof target !== "string" ||
          !/^[0-9a-f]{64}$/.test(target)
        ) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_policy_admission_request",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const result = await ghostWalkPolicyAdmissionFetcher(target);
        if (result?.kind === "not_ready") {
          jsonResponse(response, 404, {
            error: "ghostwalk_policy_admission_not_ready",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "found") {
          jsonResponse(response, 503, {
            error: "ghostwalk_policy_admission_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (url.pathname === "/api/v1/ghostwalk/accepted-intent") {
        const keys = [...url.searchParams.keys()];
        const target = url.searchParams.get("target");
        if (
          keys.length !== 1 ||
          keys[0] !== "target" ||
          typeof target !== "string" ||
          !/^[0-9a-f]{64}$/.test(target)
        ) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_accepted_intent_request",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const result = await ghostWalkAcceptedIntentFetcher(target);
        if (result?.kind === "none") {
          jsonResponse(response, 404, {
            error: "ghostwalk_accepted_intent_not_found",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        if (!result || result.kind !== "found") {
          jsonResponse(response, 503, {
            error: "ghostwalk_accepted_intent_unavailable",
            policyAuthority: false,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, result.envelope);
        return;
      }

      if (url.pathname === "/api/v1/ghostwalk/operator-log") {
        const keys = [...url.searchParams.keys()];
        const target = url.searchParams.get("target");
        if (
          keys.length !== 1 ||
          keys[0] !== "target" ||
          typeof target !== "string" ||
          !/^[0-9a-f]{64}$/.test(target)
        ) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_operator_note_request",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const note = await ghostWalkOperatorNoteFetcher(target);
        if (!note) {
          jsonResponse(response, 503, {
            error: "ghostwalk_operator_note_unavailable",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, note);
        return;
      }

      if (url.pathname === "/api/v1/ghostwalk") {
        if ([...url.searchParams.keys()].length !== 0) {
          jsonResponse(response, 400, {
            error: "invalid_ghostwalk_status_request",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const status = await ghostWalkStatusFetcher();
        if (!status) {
          jsonResponse(response, 503, {
            error: "ghostwalk_control_unavailable",
            localOnly: true,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, status);
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

      if (url.pathname === "/api/v1/persistent-history-compare") {
        const keys = [...url.searchParams.keys()];
        const fromRecordId = url.searchParams.get("from");
        const toRecordId = url.searchParams.get("to");
        const stateIdPattern = /^phishell\.system-state\.[0-9a-f]{64}$/;
        if (
          keys.length !== 2 ||
          new Set(keys).size !== 2 ||
          !url.searchParams.has("from") ||
          !url.searchParams.has("to") ||
          !fromRecordId ||
          !toRecordId ||
          !stateIdPattern.test(fromRecordId) ||
          !stateIdPattern.test(toRecordId) ||
          fromRecordId === toRecordId
        ) {
          jsonResponse(response, 400, {
            error: "invalid_persistent_history_comparison_request",
            readOnly: true,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const comparisonEnvelope = await historyComparisonFetcher({
          fromRecordId,
          toRecordId,
        });
        if (!comparisonEnvelope) {
          jsonResponse(response, 503, {
            error: "persistent_history_comparison_unavailable",
            localOnly: true,
            readOnly: true,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, comparisonEnvelope);
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

      if (url.pathname === "/api/v1/curiosity-authority") {
        if ([...url.searchParams.keys()].length !== 0) {
          jsonResponse(response, 400, {
            error: "invalid_curiosity_authority_request",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const health = await curiosityAuthorityHealthFetcher();
        if (!health) {
          jsonResponse(response, 503, {
            error: "curiosity_authority_broker_unavailable",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, health);
        return;
      }

      const persistRequestPrefix = "/api/v1/curiosity/persist-requests/";
      if (url.pathname.startsWith(persistRequestPrefix)) {
        if ([...url.searchParams.keys()].length !== 0) {
          jsonResponse(response, 400, {
            error: "invalid_curiosity_persist_status_request",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const requestId = url.pathname.slice(persistRequestPrefix.length);
        if (!validateCuriosityPersistRequestId(requestId)) {
          jsonResponse(response, 400, {
            error: "invalid_curiosity_persist_request_id",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        const item = await curiosityPersistRequestFetcher(requestId);
        if (!item) {
          jsonResponse(response, 503, {
            error: "curiosity_persist_request_unavailable",
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }

        jsonResponse(response, 200, item);
        return;
      }

      if (url.pathname === "/api/v1/curiosity") {
        if ([...url.searchParams.keys()].length !== 0) {
          jsonResponse(response, 400, {
            error: "invalid_curiosity_projection_request",
            readOnly: true,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        const curiosityEnvelope = await curiosityProjectionFetcher();
        if (!curiosityEnvelope) {
          jsonResponse(response, 503, {
            error: "curiosity_projection_unavailable",
            localOnly: true,
            readOnly: true,
            operationalAuthority: false,
            actionAuthority: false,
            executionAuthority: false,
            effectPerformed: false,
          });
          return;
        }
        jsonResponse(response, 200, curiosityEnvelope);
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
