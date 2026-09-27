import { useCallback, useEffect, useState } from "react";
import {
  ghostWalkAuthorizationConsoleClient,
  type AuthorizationDecisionKind,
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
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<
    "DECISION" | "BINDING" | "LEASE" | null
  >(null);
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

  const recordDecision = useCallback(
    async (decision: AuthorizationDecisionKind) => {
      if (
        !snapshot?.authorization_readiness.ready ||
        !snapshot.authorization_readiness.authority_request_sha256
      ) {
        return;
      }
      setBusy("DECISION");
      setMessage(null);
      try {
        const result =
          await ghostWalkAuthorizationConsoleClient.recordDecision({
            targetSha256,
            expectedAuthorityRequestSha256:
              snapshot.authorization_readiness.authority_request_sha256,
            expectedPreviousDecisionSha256:
              snapshot.authorization_readiness.latest_decision_sha256,
            decision,
            decisionNote: note.trim() || null,
          });
        if (result.kind === "conflict") {
          setMessage(
            "Authorization conflict: the request or decision history changed. Reload before deciding again.",
          );
          return;
        }
        if (result.kind === "unavailable") {
          setMessage(
            "Authorization decision was rejected or could not be validated.",
          );
          return;
        }
        setSnapshot(result.snapshot);
        setNote("");
        setMessage(
          `${decision} recorded. This decision did not create an ActionLease or execute an effect.`,
        );
      } finally {
        setBusy(null);
      }
    },
    [note, snapshot, targetSha256],
  );

  const createBinding = useCallback(async () => {
    const readiness = snapshot?.binding_readiness;
    if (
      !readiness?.ready ||
      !readiness.authorization_decision_sha256 ||
      !readiness.selected_mapping_sha256
    ) {
      return;
    }
    setBusy("BINDING");
    setMessage(null);
    try {
      const result =
        await ghostWalkAuthorizationConsoleClient.createBinding({
          targetSha256,
          expectedAuthorizationDecisionSha256:
            readiness.authorization_decision_sha256,
          expectedMappingSha256: readiness.selected_mapping_sha256,
          expectedMappingSetSha256: readiness.mapping_set_sha256,
        });
      if (result.kind === "conflict") {
        setMessage(
          "Binding conflict: authorization or trusted mapping state changed. Reload first.",
        );
        return;
      }
      if (result.kind === "unavailable") {
        setMessage(
          "Executable binding is unavailable. Trusted local execution configuration may be absent or invalid.",
        );
        return;
      }
      setSnapshot(result.snapshot);
      setMessage(
        "Exact executable binding created. It still carries zero action and execution authority.",
      );
    } finally {
      setBusy(null);
    }
  }, [snapshot, targetSha256]);

  const issueLease = useCallback(async () => {
    const readiness = snapshot?.lease_readiness;
    if (
      !readiness?.ready ||
      !readiness.executable_binding_sha256 ||
      !readiness.policy_sha256 ||
      !readiness.enforcement_profile_sha256 ||
      !readiness.authority_epoch_sha256
    ) {
      return;
    }
    setBusy("LEASE");
    setMessage(null);
    try {
      const result = await ghostWalkAuthorizationConsoleClient.issueLease({
        targetSha256,
        expectedExecutableBindingSha256:
          readiness.executable_binding_sha256,
        expectedPolicySha256: readiness.policy_sha256,
        expectedPolicySetSha256: readiness.policy_set_sha256,
        expectedEnforcementProfileSha256:
          readiness.enforcement_profile_sha256,
        expectedAuthorityEpochSha256:
          readiness.authority_epoch_sha256,
      });
      if (result.kind === "conflict") {
        setMessage(
          "Lease conflict: binding, policy, enforcement, or authority state changed. Reload first.",
        );
        return;
      }
      if (result.kind === "unavailable") {
        setMessage(
          "ActionLease issuance is unavailable or failed current authority checks.",
        );
        return;
      }
      setSnapshot(result.snapshot);
      setMessage(
        "Single-use ActionLease issued. The lease carries bounded action authority; this console still cannot execute it.",
      );
    } finally {
      setBusy(null);
    }
  }, [snapshot, targetSha256]);

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

        {auth.ready && (
          <>
            <textarea
              value={note}
              maxLength={2048}
              disabled={busy !== null}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Optional human decision note"
            />
            <div className="ghostwalk-auth-actions">
              <button
                disabled={busy !== null}
                onClick={() => void recordDecision("APPROVE")}
              >
                APPROVE
              </button>
              <button
                className="hold"
                disabled={busy !== null}
                onClick={() => void recordDecision("HOLD")}
              >
                HOLD
              </button>
              <button
                className="deny"
                disabled={busy !== null}
                onClick={() => void recordDecision("DENY")}
              >
                DENY
              </button>
            </div>
          </>
        )}
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

        {binding?.ready && !snapshot.binding && (
          <button
            className="ghostwalk-auth-primary"
            disabled={busy !== null}
            onClick={() => void createBinding()}
          >
            CREATE EXACT BINDING
          </button>
        )}
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

        {lease?.ready && !snapshot.lease && (
          <button
            className="ghostwalk-auth-primary lease"
            disabled={busy !== null}
            onClick={() => void issueLease()}
          >
            ISSUE SINGLE-USE ACTION LEASE
          </button>
        )}
      </div>

      {message && (
        <div className="ghostwalk-auth-console-message">{message}</div>
      )}

      <div className="ghostwalk-auth-console-boundary">
        HUMAN DECISION != BINDING · BINDING != LEASE · LEASE != EXECUTION ·
        VESSIE MAY REFERENCE A LEASE, NOT MINT ONE
      </div>
    </section>
  );
}
