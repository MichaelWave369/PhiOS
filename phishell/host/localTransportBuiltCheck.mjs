import assert from "node:assert/strict";
import { createLocalObservationServer } from "./localTransport.mjs";

if (process.platform !== "linux") {
  process.exit(0);
}

const transport = createLocalObservationServer({
  port: 0,
  historyProjectionFetcher: async () => null,
  historyComparisonFetcher: async () => null,
  curiosityProjectionFetcher: async () => null,
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

  const curiosityWrite = await fetch(`${base}/api/v1/curiosity/artifacts`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  assert.equal(curiosityWrite.status, 428);
  const curiosityHeld = await curiosityWrite.json();
  assert.equal(curiosityHeld.error, "action_lease_required");
  assert.equal(curiosityHeld.writeAvailable, false);
  assert.equal(curiosityHeld.actionAuthority, false);
  assert.equal(curiosityHeld.executionAuthority, false);
  assert.equal(curiosityHeld.effectPerformed, false);

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
