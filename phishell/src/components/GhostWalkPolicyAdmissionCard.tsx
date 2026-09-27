import { useCallback, useEffect, useState } from "react";
import {
  ghostWalkPolicyAdmissionClient,
  type GhostWalkPolicyProfile,
  type GhostWalkPolicyProjection,
  type GhostWalkPolicyReceipt,
} from "../ghostwalk/policyAdmission";

function shortHash(value: string) {
  return `${value.slice(0, 10)}…`;
}

export function GhostWalkPolicyAdmissionCard({
  targetSha256,
  acceptedIntentRevisionSha256,
  operatorNoteRevisionSha256,
}: {
  targetSha256: string;
  acceptedIntentRevisionSha256: string;
  operatorNoteRevisionSha256: string;
}) {
  const [profile, setProfile] = useState<GhostWalkPolicyProfile | null>(null);
  const [projection, setProjection] = useState<GhostWalkPolicyProjection | null>(null);
  const [receipt, setReceipt] = useState<GhostWalkPolicyReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await ghostWalkPolicyAdmissionClient.read(targetSha256);
    if (result.kind === "found") {
      setProfile(result.profile);
      setProjection(result.projection);
      setMessage(null);
      return;
    }
    setProfile(null);
    setProjection(null);
    setMessage(
      result.kind === "not_ready"
        ? "Policy admission is not ready because no valid accepted intent is available."
        : "Policy admission is unavailable or returned invalid evidence.",
    );
  }, [targetSha256, acceptedIntentRevisionSha256, operatorNoteRevisionSha256]);

  useEffect(() => {
    void load();
  }, [load]);

  const recordAdmission = useCallback(async () => {
    if (!profile || !projection) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await ghostWalkPolicyAdmissionClient.record({
        targetSha256,
        expectedAcceptedIntentRevisionSha256:
          projection.accepted_intent_revision_sha256,
        expectedPolicyProfileSha256: profile.profile_sha256,
      });
      if (result.kind === "conflict") {
        setMessage(
          "Admission conflict: accepted intent or policy changed before the receipt was recorded. Reload first.",
        );
        return;
      }
      if (result.kind === "unavailable") {
        setMessage("Policy admission receipt was rejected or could not be validated.");
        return;
      }
      setReceipt(result.receipt);
      setMessage(
        `Recorded ${result.receipt.decision} admission evidence. No authority request or ActionLease was created.`,
      );
    } finally {
      setBusy(false);
    }
  }, [profile, projection, targetSha256]);

  return (
    <section className="ghostwalk-policy">
      <div className="ghostwalk-policy-head">
        <div>
          <small>POLICY ADMISSION</small>
          <b>{projection?.decision ?? "NOT READY"}</b>
        </div>
        <span>AUTHORITY 0</span>
      </div>

      {projection && profile && (
        <>
          <div className="ghostwalk-policy-grid">
            <span>reason <b>{projection.reason}</b></span>
            <span>eligible <b>{projection.request_authority_eligible ? "YES" : "NO"}</b></span>
            <span>binding <b>{projection.operator_binding_current ? "CURRENT" : "STALE"}</b></span>
            <span>policy <b>{shortHash(profile.profile_sha256)}</b></span>
          </div>

          <div className="ghostwalk-policy-rules">
            <span>allow-request {profile.allow_request_intent_codes.length}</span>
            <span>deny {profile.deny_intent_codes.length}</span>
            <span>default HOLD</span>
          </div>

          <button
            className="ghostwalk-policy-record"
            disabled={busy}
            onClick={() => void recordAdmission()}
          >
            RECORD ADMISSION EVIDENCE
          </button>
        </>
      )}

      {receipt && (
        <div className="ghostwalk-policy-receipt">
          receipt {shortHash(receipt.admission_receipt_sha256)} · {receipt.decision}
        </div>
      )}
      {message && <div className="ghostwalk-policy-message">{message}</div>}

      <div className="ghostwalk-policy-boundary">
        ALLOW_REQUEST != AUTHORITY REQUEST · POLICY ADMISSION != ACTIONLEASE · NO EXECUTION
      </div>
    </section>
  );
}
