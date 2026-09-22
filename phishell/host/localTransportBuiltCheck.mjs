import assert from "node:assert/strict";
import { createLocalObservationServer } from "./localTransport.mjs";

if (process.platform !== "linux") {
  process.exit(0);
}

const transport = createLocalObservationServer({ port: 0 });
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
} finally {
  await transport.close();
}
