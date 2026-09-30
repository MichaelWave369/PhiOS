import { useCallback, useEffect, useState } from "react";
import {
  ghostWalkAuthorizationConsoleClient,
  type GhostWalkAuthorizationConsoleSnapshot,
} from "../ghostwalk/authorizationConsole";

function shortHash(value: string | null) {
  return value ? `${value.slice(0, 10)}…` : "NONE";
}

export function GhostWalkAuthorizationConsoleCard({
  targetSha256,
  refreshToken,
}: {
  targetSha256: string;
  refreshToken: string;
}) {
  const [snapshot, setSnapshot] =
    useState<GhostWalkAuthorizationConsoleSnapshot | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await ghostWalkAuthorizationConsoleClient.read(
      targetSha256,
    );
    if (result.kind === "found") {
      setSnapshot(result.snapshot);
      setMessage(null);
      return;
    }
    setSnapshot(null);
    setMessage(
      "Human authorization console is unavailable or returned invalid evidence.",
    );
  }, [targetSha256, refreshToken]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!snapshot) {
    return (
      <section className="ghostwalk-auth-console unavailable">
        <div className="ghostwalk-auth-console-head">
          <div>
            <small>HUMAN AUTHORIZATION + LEASE</small>
            <b>UNAVAILABLE</b>
          </div>
          <span>EXECUTION 0</span>
        </div>
        {message && (
          <div className="ghostwalk-auth-console-message">{message}</div>
        )}
      </section>
    );
  }

  const auth = snapshot.authorization_readiness;
  const binding = snapshot.binding_readiness;
  const lease = snapshot.lease_readiness;

  return (
    <section className="ghostwalk-auth-console">
      <div className="ghostwalk-auth-console-head">
        <div>
          <small>HUMAN AUTHORIZATION + LEASE</small>
          <b>{snapshot.lease ? "LEASE ISSUED" : auth.reason}</b>
        </div>
        <span>EXECUTION 0</span>
      </div>

      <div className="ghostwalk-auth-stage">
        <div className="ghostwalk-auth-stage-head">
          <b>1 · HUMAN DECISION</b>
          <span>{auth.ready ? "READY" : auth.reason}</span>
        </div>

        {snapshot.authorization_decision && (
          <div className="ghostwalk-auth-current">
            <b>{snapshot.authorization_decision.decision}</b>
            <span>
              decision{" "}
              {shortHash(
                snapshot.authorization_decision
                  .authorization_decision_sha256,
              )}
            </span>
            <small>
              authorization{" "}
              {snapshot.authorization_decision.authorization_granted
                ? "GRANTED"
                : "NOT GRANTED"}
              {" · "}action authority 0
            </small>
          </div>
        )}

        <p>Review and decide in your local operator terminal:</p>
        <code>phi-operator --target {targetSha256} decide APPROVE</code>
        <p>The terminal also supports HOLD and DENY. HTTP cannot record a decision.</p>
      </div>

      <div className="ghostwalk-auth-stage">
        <div className="ghostwalk-auth-stage-head">
          <b>2 · EXECUTABLE BINDING</b>
          <span>
            {!snapshot.binding_available
              ? "TRUST CONFIG REQUIRED"
              : binding?.reason ?? "UNAVAILABLE"}
          </span>
        </div>

        {snapshot.binding && (
          <div className="ghostwalk-auth-current">
            <b>
              {snapshot.binding.capability_id}@
              {snapshot.binding.capability_version}
            </b>
            <span>
              binding{" "}
              {shortHash(snapshot.binding.executable_binding_sha256)}
              {" · "}payload {shortHash(snapshot.binding.payload_sha256)}
            </span>
            <small>
              permissions {snapshot.binding.permissions_required.join(", ")}
              {" · "}effects {snapshot.binding.effects_declared.join(", ")}
            </small>
          </div>
        )}

        <code>phi-operator --target {targetSha256} bind</code>
      </div>

      <div className="ghostwalk-auth-stage lease">
        <div className="ghostwalk-auth-stage-head">
          <b>3 · SINGLE-USE ACTION LEASE</b>
          <span>
            {!snapshot.lease_available
              ? "TRUST CONFIG REQUIRED"
              : lease?.reason ?? "UNAVAILABLE"}
          </span>
        </div>

        {lease && (
          <div className="ghostwalk-auth-trust-grid">
            <span>
              policy <b>{shortHash(lease.policy_sha256)}</b>
            </span>
            <span>
              enforcement{" "}
              <b>{shortHash(lease.enforcement_profile_sha256)}</b>
            </span>
            <span>
              authority epoch{" "}
              <b>{shortHash(lease.authority_epoch_sha256)}</b>
            </span>
            <span>
              missing permissions{" "}
              <b>
                {lease.missing_permissions.length
                  ? lease.missing_permissions.join(", ")
                  : "NONE"}
              </b>
            </span>
          </div>
        )}

        {snapshot.lease && (
          <div className="ghostwalk-auth-lease">
            <b>
              ActionLease {shortHash(snapshot.lease.action_lease_sha256)}
            </b>
            <span>
              {snapshot.lease.capability_id}@
              {snapshot.lease.capability_version}
            </span>
            <small>
              single-use · valid until {snapshot.lease.valid_until}
            </small>
            <code>{snapshot.lease.action_lease_sha256}</code>
          </div>
        )}

        <code>phi-operator --target {targetSha256} lease</code>
      </div>

      {message && (
        <div className="ghostwalk-auth-console-message">{message}</div>
      )}

      <button onClick={() => void load()}>REFRESH OPERATOR STATUS</button>

      <div className="ghostwalk-auth-console-boundary">
        HUMAN DECISION != BINDING · BINDING != LEASE · LEASE != EXECUTION ·
        VESSIE MAY REFERENCE A LEASE, NOT MINT ONE
      </div>
    </section>
  );
}
