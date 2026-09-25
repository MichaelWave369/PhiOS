import assert from "node:assert/strict";
import { createLocalObservationServer } from "./localTransport.mjs";

if (process.platform !== "linux") {
  process.exit(0);
}

const brokerHealth = {
  schemaVersion: "phios.curiosity-authority-broker.v0.5",
  brokerId: "phios.curiosity-authority-broker.local.v0.5",
  localOnly: true,
  principalId: "operator:test",
  capabilityId: "curiosity.persist",
  permission: "curiosity.write",
  approvalMode: "local_cli_hmac_exact_payload",
  browserCanApprove: false,
  browserReceivesLease: false,
  status: "ready",
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
};

const persistRow = {
  schemaVersion: "phios.curiosity-persist-request.v0.5",
  requestId: "curiosity-request-" + "a".repeat(32),
  payload: {
    schema_version: "phios.curiosity_persist_payload.v0.4",
    artifact_kind: "creative_seed",
    title: "Bubble rhythm",
    content: "Explore the metaphor without declaring a law.",
    created_at: "2026-09-25T21:30:00.000Z",
    created_by: "operator:test",
    tags: ["gear", "music"],
    evidence_ref_sha256s: [],
    parent_artifact_sha256s: [],
  },
  payloadSha256: "b".repeat(64),
  requestedAt: "2026-09-25T21:30:01.000Z",
  expiresAt: "2026-09-25T21:40:01.000Z",
  status: "pending",
  reason: "awaiting_operator_approval",
  approvedAt: null,
  artifactSha256: null,
  executionReceipt: null,
  approvalCommand:
    "python -m phios.curiosity_authority_broker approve curiosity-request-" +
    "a".repeat(32),
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
};

const transport = createLocalObservationServer({
  port: 0,
  historyProjectionFetcher: async () => null,
  historyComparisonFetcher: async () => null,
  curiosityProjectionFetcher: async () => null,
  curiosityAuthorityHealthFetcher: async () => brokerHealth,
  curiosityPersistRequestCreator: async () => persistRow,
  curiosityPersistRequestFetcher: async (requestId) =>
    requestId === persistRow.requestId ? persistRow : null,
});
const address = await transport.listen();
const base = `http://127.0.0.1:${address.port}`;

try {
  const shell = await fetch(`${base}/`);
  assert.equal(shell.status, 200);
  assert.match(shell.headers.get("content-type") ?? "", /text\/html/);
  const html = await shell.text();
  assert.match(html, /<div id="root"><\/div>/);

  const observation = await fetch(`${base}/api/v1/host-observation`);
  assert.equal(observation.status, 200);
  assert.equal(observation.headers.get("access-control-allow-origin"), null);

  const envelope = await observation.json();
  assert.equal(envelope.transportSchemaVersion, "phios.host-transport.v1");
  assert.equal(envelope.transportIdentity, "phishell-local-observer");
  assert.equal(envelope.localOnly, true);
  assert.equal(envelope.readOnly, true);
  assert.equal(envelope.executionAuthority, false);
  assert.equal(envelope.effectPerformed, false);
  assert.equal(envelope.snapshot.source, "linux-readonly-node-probe");

  const serviceObservation = await fetch(`${base}/api/v1/service-observation`);
  assert.equal(serviceObservation.status, 200);
  assert.equal(serviceObservation.headers.get("access-control-allow-origin"), null);

  const serviceEnvelope = await serviceObservation.json();
  assert.equal(serviceEnvelope.transportSchemaVersion, "phios.service-transport.v1");
  assert.equal(serviceEnvelope.transportIdentity, "phishell-local-observer");
  assert.equal(serviceEnvelope.localOnly, true);
  assert.equal(serviceEnvelope.readOnly, true);
  assert.equal(serviceEnvelope.executionAuthority, false);
  assert.equal(serviceEnvelope.effectPerformed, false);
  assert.equal(serviceEnvelope.observation.source, "systemd-dbus-list-units");
  assert.equal(serviceEnvelope.observation.allowlistOnly, true);

  const processObservation = await fetch(`${base}/api/v1/process-observation`);
  assert.equal(processObservation.status, 200);
  assert.equal(processObservation.headers.get("access-control-allow-origin"), null);

  const processEnvelope = await processObservation.json();
  assert.equal(processEnvelope.transportSchemaVersion, "phios.process-transport.v1");
  assert.equal(processEnvelope.transportIdentity, "phishell-local-observer");
  assert.equal(processEnvelope.localOnly, true);
  assert.equal(processEnvelope.readOnly, true);
  assert.equal(processEnvelope.executionAuthority, false);
  assert.equal(processEnvelope.effectPerformed, false);
  assert.equal(processEnvelope.observation.source, "procfs-current-user");
  assert.equal(processEnvelope.observation.scope, "current-user");
  assert.ok(processEnvelope.observation.processes.length <= 32);

  const packageObservation = await fetch(`${base}/api/v1/package-observation`);
  assert.equal(packageObservation.status, 200);
  assert.equal(packageObservation.headers.get("access-control-allow-origin"), null);

  const packageEnvelope = await packageObservation.json();
  assert.equal(packageEnvelope.transportSchemaVersion, "phios.package-transport.v1");
  assert.equal(packageEnvelope.transportIdentity, "phishell-local-observer");
  assert.equal(packageEnvelope.localOnly, true);
  assert.equal(packageEnvelope.readOnly, true);
  assert.equal(packageEnvelope.executionAuthority, false);
  assert.equal(packageEnvelope.effectPerformed, false);
  assert.equal(packageEnvelope.observation.source, "dpkg-status-file");
  assert.equal(packageEnvelope.observation.adapter, "debian-dpkg-status");
  assert.ok(packageEnvelope.observation.packages.length <= 64);

  const deviceObservation = await fetch(`${base}/api/v1/device-observation`);
  assert.equal(deviceObservation.status, 200);
  assert.equal(deviceObservation.headers.get("access-control-allow-origin"), null);

  const deviceEnvelope = await deviceObservation.json();
  assert.equal(deviceEnvelope.transportSchemaVersion, "phios.device-transport.v1");
  assert.equal(deviceEnvelope.transportIdentity, "phishell-local-observer");
  assert.equal(deviceEnvelope.localOnly, true);
  assert.equal(deviceEnvelope.readOnly, true);
  assert.equal(deviceEnvelope.executionAuthority, false);
  assert.equal(deviceEnvelope.effectPerformed, false);
  assert.equal(deviceEnvelope.observation.source, "linux-sysfs-bounded");
  assert.ok(deviceEnvelope.observation.block.length <= 16);
  assert.ok(deviceEnvelope.observation.network.length <= 16);
  assert.ok(deviceEnvelope.observation.pci.length <= 16);
  assert.ok(deviceEnvelope.observation.usb.length <= 16);

  const systemState = await fetch(`${base}/api/v1/system-state`);
  assert.equal(systemState.status, 200);
  assert.equal(systemState.headers.get("access-control-allow-origin"), null);

  const systemEnvelope = await systemState.json();
  assert.equal(systemEnvelope.transportSchemaVersion, "phios.system-state-transport.v1");
  assert.equal(systemEnvelope.transportIdentity, "phishell-local-observer");
  assert.equal(systemEnvelope.localOnly, true);
  assert.equal(systemEnvelope.readOnly, true);
  assert.equal(systemEnvelope.executionAuthority, false);
  assert.equal(systemEnvelope.effectPerformed, false);
  assert.equal(systemEnvelope.receipt.schemaVersion, "phios.system-state.v1");
  assert.equal(systemEnvelope.receipt.componentCount, 5);
  assert.equal(systemEnvelope.receipt.executionAuthority, false);
  assert.equal(systemEnvelope.receipt.effectPerformed, false);
  assert.match(systemEnvelope.receipt.receiptDigest, /^sha256:[0-9a-f]{64}$/);

  const persistentHistory = await fetch(`${base}/api/v1/persistent-history`);
  assert.equal(persistentHistory.status, 503);
  assert.equal(persistentHistory.headers.get("access-control-allow-origin"), null);
  const persistentHistoryUnavailable = await persistentHistory.json();
  assert.equal(persistentHistoryUnavailable.error, "persistent_history_unavailable");
  assert.equal(persistentHistoryUnavailable.readOnly, true);
  assert.equal(persistentHistoryUnavailable.executionAuthority, false);
  assert.equal(persistentHistoryUnavailable.effectPerformed, false);

  const comparisonFrom = "phishell.system-state." + "a".repeat(64);
  const comparisonTo = "phishell.system-state." + "b".repeat(64);
  const persistentComparison = await fetch(
    `${base}/api/v1/persistent-history-compare?from=${comparisonFrom}&to=${comparisonTo}`,
  );
  assert.equal(persistentComparison.status, 503);
  assert.equal(persistentComparison.headers.get("access-control-allow-origin"), null);
  const comparisonUnavailable = await persistentComparison.json();
  assert.equal(
    comparisonUnavailable.error,
    "persistent_history_comparison_unavailable",
  );
  assert.equal(comparisonUnavailable.readOnly, true);
  assert.equal(comparisonUnavailable.executionAuthority, false);
  assert.equal(comparisonUnavailable.effectPerformed, false);

  const invalidComparison = await fetch(
    `${base}/api/v1/persistent-history-compare?from=not-a-state&to=${comparisonTo}`,
  );
  assert.equal(invalidComparison.status, 400);

  const curiosityProjection = await fetch(`${base}/api/v1/curiosity`);
  assert.equal(curiosityProjection.status, 503);
  const curiosityUnavailable = await curiosityProjection.json();
  assert.equal(curiosityUnavailable.error, "curiosity_projection_unavailable");
  assert.equal(curiosityUnavailable.readOnly, true);
  assert.equal(curiosityUnavailable.executionAuthority, false);
  assert.equal(curiosityUnavailable.effectPerformed, false);

  const curiosityAuthority = await fetch(`${base}/api/v1/curiosity-authority`);
  assert.equal(curiosityAuthority.status, 200);
  const authorityEnvelope = await curiosityAuthority.json();
  assert.equal(authorityEnvelope.browserCanApprove, false);
  assert.equal(authorityEnvelope.browserReceivesLease, false);
  assert.equal(authorityEnvelope.actionAuthority, false);
  assert.equal(authorityEnvelope.executionAuthority, false);

  const curiosityRequest = await fetch(
    `${base}/api/v1/curiosity/persist-requests`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        artifact_kind: "creative_seed",
        title: "Bubble rhythm",
        content: "Explore the metaphor without declaring a law.",
        created_at: "2026-09-25T21:30:00.000Z",
        tags: ["gear", "music"],
        evidence_ref_sha256s: [],
        parent_artifact_sha256s: [],
      }),
    },
  );
  assert.equal(curiosityRequest.status, 201);
  const createdCuriosityRequest = await curiosityRequest.json();
  assert.equal(createdCuriosityRequest.status, "pending");
  assert.equal(createdCuriosityRequest.actionAuthority, false);
  assert.equal(createdCuriosityRequest.executionAuthority, false);
  assert.match(
    createdCuriosityRequest.approvalCommand,
    /^python -m phios\.curiosity_authority_broker approve curiosity-request-/,
  );

  const curiosityRequestStatus = await fetch(
    `${base}/api/v1/curiosity/persist-requests/${persistRow.requestId}`,
  );
  assert.equal(curiosityRequestStatus.status, 200);
  const requestStatusEnvelope = await curiosityRequestStatus.json();
  assert.equal(requestStatusEnvelope.requestId, persistRow.requestId);
  assert.equal(requestStatusEnvelope.status, "pending");

  const invalidCuriosityRequest = await fetch(
    `${base}/api/v1/curiosity/persist-requests`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        artifact_kind: "creative_seed",
        title: "Bad request",
        content: "Browser tries to smuggle approval.",
        created_at: "2026-09-25T21:30:00.000Z",
        tags: [],
        evidence_ref_sha256s: [],
        parent_artifact_sha256s: [],
        approved: true,
      }),
    },
  );
  assert.equal(invalidCuriosityRequest.status, 400);

  const legacyCuriosityWrite = await fetch(`${base}/api/v1/curiosity/artifacts`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  assert.equal(legacyCuriosityWrite.status, 410);
  const legacyCuriosityBody = await legacyCuriosityWrite.json();
  assert.equal(legacyCuriosityBody.error, "legacy_curiosity_persist_endpoint_retired");
  assert.equal(legacyCuriosityBody.actionAuthority, false);
  assert.equal(legacyCuriosityBody.executionAuthority, false);

  const browserApprovalAttempt = await fetch(`${base}/api/v1/operator-approval`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  assert.equal(browserApprovalAttempt.status, 405);

  const mutation = await fetch(`${base}/api/v1/host-observation`, { method: "POST" });
  assert.equal(mutation.status, 405);

  const serviceMutation = await fetch(`${base}/api/v1/service-observation`, {
    method: "POST",
  });
  assert.equal(serviceMutation.status, 405);

  const processMutation = await fetch(`${base}/api/v1/process-observation`, {
    method: "POST",
  });
  assert.equal(processMutation.status, 405);

  const packageMutation = await fetch(`${base}/api/v1/package-observation`, {
    method: "POST",
  });
  assert.equal(packageMutation.status, 405);

  const deviceMutation = await fetch(`${base}/api/v1/device-observation`, {
    method: "POST",
  });
  assert.equal(deviceMutation.status, 405);

  const stateMutation = await fetch(`${base}/api/v1/system-state`, {
    method: "POST",
  });
  assert.equal(stateMutation.status, 405);

  const historyMutation = await fetch(`${base}/api/v1/persistent-history`, {
    method: "POST",
  });
  assert.equal(historyMutation.status, 405);

  const comparisonMutation = await fetch(
    `${base}/api/v1/persistent-history-compare?from=${comparisonFrom}&to=${comparisonTo}`,
    { method: "POST" },
  );
  assert.equal(comparisonMutation.status, 405);
} finally {
  await transport.close();
}
