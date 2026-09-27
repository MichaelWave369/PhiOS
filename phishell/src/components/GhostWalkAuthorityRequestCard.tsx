import { useCallback, useEffect, useState } from "react";
import {
  ghostWalkAuthorityRequestClient,
  type GhostWalkAuthorityRequest,
  type GhostWalkAuthorityRequestReadiness,
} from "../ghostwalk/authorityRequest";

function shortHash(value: string) {
  return `${value.slice(0, 10)}…`;
}

export function GhostWalkAuthorityRequestCard({
  targetSha256,
  refreshToken,
}: {
  targetSha256: string;
  refreshToken: string;
}) {
  const [readiness, setReadiness] =
    useState<GhostWalkAuthorityRequestReadiness | null>(null);
  const [request, setRequest] =
    useState<GhostWalkAuthorityRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await ghostWalkAuthorityRequestClient.read(targetSha256);
    if (result.kind === "found") {
      setReadiness(result.readiness);
      setRequest(result.request);
      setMessage(null);
      return;
    }
    setReadiness(null);
    setRequest(null);
    setMessage(
      result.kind === "not_ready"
        ? "AuthorityRequest is not ready because accepted-intent or policy evidence is missing."
        : "AuthorityRequest state is unavailable or invalid.",
    );
  }, [targetSha256, refreshToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const createRequest = useCallback(async () => {
    if (!readiness?.ready || !readiness.admission_receipt_sha256) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await ghostWalkAuthorityRequestClient.create({
        targetSha256,
        expectedAdmissionReceiptSha256:
          readiness.admission_receipt_sha256,
      });
      if (result.kind === "conflict") {
        setMessage(
          "AuthorityRequest conflict: admission evidence changed or a request already exists. Reload first.",
        );
        return;
      }
      if (result.kind === "unavailable") {
        setMessage("AuthorityRequest creation was rejected or could not be validated.");
        return;
      }
      setRequest(result.request);
      setMessage(
        `AuthorityRequest ${shortHash(result.request.authority_request_sha256)} created as PENDING_AUTHORIZATION. No authority was granted.`,
      );
      await load();
    } finally {
      setBusy(false);
    }
  }, [load, readiness, targetSha256]);

  return (
    <section className="ghostwalk-authority-request">
      <div className="ghostwalk-authority-request-head">
        <div>
          <small>AUTHORITY REQUEST</small>
          <b>{request?.request_state ?? readiness?.reason ?? "NOT READY"}</b>
        </div>
        <span>ACTION AUTH 0</span>
      </div>

      {readiness && (
        <div className="ghostwalk-authority-request-grid">
          <span>policy <b>{readiness.policy_decision}</b></span>
          <span>ready <b>{readiness.ready ? "YES" : "NO"}</b></span>
          <span>admission <b>{readiness.admission_receipt_sha256 ? shortHash(readiness.admission_receipt_sha256) : "NONE"}</b></span>
          <span>lease <b>NONE</b></span>
        </div>
      )}

      {request && (
        <div className="ghostwalk-authority-request-current">
          <b>{request.requested_scope_value}</b>
          <span>
            {request.requested_authority_kind} · {shortHash(request.authority_request_sha256)}
          </span>
          <small>
            requester {request.requester_id} · authorization NOT GRANTED
          </small>
        </div>
      )}

      {readiness?.ready && !request && (
        <button
          className="ghostwalk-authority-request-create"
          disabled={busy || !readiness.admission_receipt_sha256}
          onClick={() => void createRequest()}
        >
          CREATE AUTHORITY REQUEST
        </button>
      )}

      {message && (
        <div className="ghostwalk-authority-request-message">{message}</div>
      )}

      <div className="ghostwalk-authority-request-boundary">
        REQUEST != AUTHORIZATION · PENDING_AUTHORIZATION != ACTION AUTHORITY · ACTIONLEASE NOT CREATED
      </div>
    </section>
  );
}
