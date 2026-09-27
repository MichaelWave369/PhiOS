import { useCallback, useEffect, useState } from "react";
import { GhostWalkPolicyAdmissionCard } from "./GhostWalkPolicyAdmissionCard";
import {
  GHOSTWALK_INTENT_FAMILIES,
  ghostWalkAcceptedIntentClient,
  type GhostWalkAcceptedIntent,
  type GhostWalkIntentFamily,
} from "../ghostwalk/acceptedIntent";

function shortHash(value: string) {
  return `${value.slice(0, 10)}…`;
}

export function GhostWalkAcceptedIntentEditor({
  targetSha256,
  sourceOperatorNoteRevisionSha256,
  operatorNoteActive,
}: {
  targetSha256: string;
  sourceOperatorNoteRevisionSha256: string;
  operatorNoteActive: boolean;
}) {
  const [current, setCurrent] = useState<GhostWalkAcceptedIntent | null>(null);
  const [family, setFamily] = useState<GhostWalkIntentFamily>("OPEN");
  const [code, setCode] = useState("OPEN_");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await ghostWalkAcceptedIntentClient.read(targetSha256);
      if (result.kind === "found") {
        setCurrent(result.intent);
        setFamily(result.intent.intent_family);
        setCode(result.intent.intent_code);
        setMessage(null);
      } else if (result.kind === "none") {
        setCurrent(null);
        setMessage(null);
      } else {
        setMessage("Accepted-intent registry is unavailable or returned invalid evidence.");
      }
    } finally {
      setLoading(false);
    }
  }, [targetSha256]);

  useEffect(() => {
    void load();
  }, [load]);

  const updateFamily = useCallback((next: GhostWalkIntentFamily) => {
    setFamily(next);
    if (next === "OTHER") {
      setCode("CUSTOM_INTENT");
    } else {
      setCode(`${next}_`);
    }
  }, []);

  const accept = useCallback(async () => {
    if (!operatorNoteActive || !code.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await ghostWalkAcceptedIntentClient.accept({
        targetSha256,
        sourceOperatorNoteRevisionSha256,
        family,
        code: code.trim().toUpperCase(),
        expectedCurrentRevisionSha256: current?.revision_sha256 ?? null,
      });
      if (result.kind === "conflict") {
        setMessage(
          "Intent conflict: the accepted-intent record changed after you loaded it. Reload before saving.",
        );
        return;
      }
      if (result.kind === "unavailable") {
        setMessage(
          "Intent acceptance was rejected or could not be validated. The current OperatorLog revision may have changed.",
        );
        return;
      }
      setCurrent(result.intent);
      setFamily(result.intent.intent_family);
      setCode(result.intent.intent_code);
      setMessage(
        `Accepted intent revision ${result.intent.revision}: ${result.intent.intent_code}. No execution policy was granted.`,
      );
    } finally {
      setBusy(false);
    }
  }, [
    code,
    current,
    family,
    operatorNoteActive,
    sourceOperatorNoteRevisionSha256,
    targetSha256,
  ]);

  const revoke = useCallback(async () => {
    if (!current || current.status !== "ACTIVE") return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await ghostWalkAcceptedIntentClient.revoke({
        targetSha256,
        expectedCurrentRevisionSha256: current.revision_sha256,
      });
      if (result.kind === "conflict") {
        setMessage("Intent conflict: reload the latest accepted-intent revision.");
        return;
      }
      if (result.kind === "unavailable") {
        setMessage("Intent revocation was rejected or could not be validated.");
        return;
      }
      setCurrent(result.intent);
      setMessage(
        `Accepted intent revoked in revision ${result.intent.revision}. Prior history remains intact.`,
      );
    } finally {
      setBusy(false);
    }
  }, [current, targetSha256]);

  return (
    <section className="ghostwalk-intent-editor">
      <div className="ghostwalk-intent-head">
        <div>
          <small>ACCEPTED INTENT</small>
          <b>{current ? `r${current.revision} · ${current.status}` : "UNCLASSIFIED"}</b>
        </div>
        <span>POLICY AUTH 0</span>
      </div>

      {loading ? (
        <div className="ghostwalk-empty">Reading accepted-intent history…</div>
      ) : (
        <>
          {current && (
            <div className="ghostwalk-intent-current">
              <b>{current.intent_code}</b>
              <span>
                {current.intent_family} · {shortHash(current.revision_sha256)}
              </span>
              <small>
                bound to OperatorLog {shortHash(current.source_operator_note_revision_sha256)}
              </small>
            </div>
          )}

          {current &&
            current.source_operator_note_revision_sha256 !==
              sourceOperatorNoteRevisionSha256 && (
              <div className="ghostwalk-intent-warning">
                STALE BINDING: this accepted intent was based on an older OperatorLog revision.
                Append a new accepted-intent revision to bind the current human interpretation.
              </div>
            )}

          <div className="ghostwalk-intent-form">
            <select
              value={family}
              disabled={busy || !operatorNoteActive}
              onChange={(event) => updateFamily(event.currentTarget.value as GhostWalkIntentFamily)}
              aria-label="Accepted intent family"
            >
              {GHOSTWALK_INTENT_FAMILIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <input
              value={code}
              disabled={busy || !operatorNoteActive}
              maxLength={128}
              onChange={(event) =>
                setCode(
                  event.currentTarget.value
                    .toUpperCase()
                    .replace(/[^A-Z0-9_]/g, "_"),
                )
              }
              aria-label="Accepted intent code"
              placeholder="OPEN_NETWORK_ADAPTER_PROPERTIES"
            />
          </div>

          {!operatorNoteActive && (
            <div className="ghostwalk-intent-warning">
              The current OperatorLog revision is retracted. Accepted intent cannot be created from retracted interpretation.
            </div>
          )}

          <div className="ghostwalk-intent-actions">
            <button
              disabled={busy || !operatorNoteActive || code.trim().length < 3}
              onClick={() => void accept()}
            >
              {current ? "APPEND INTENT REVISION" : "ACCEPT TYPED INTENT"}
            </button>
            {current?.status === "ACTIVE" && (
              <button className="revoke" disabled={busy} onClick={() => void revoke()}>
                REVOKE ACCEPTED INTENT
              </button>
            )}
            <button disabled={busy} onClick={() => void load()}>
              RELOAD
            </button>
          </div>

          {message && <div className="ghostwalk-intent-message">{message}</div>}

          <div className="ghostwalk-intent-boundary">
            MACHINE CANDIDATE != HUMAN ANNOTATION != ACCEPTED INTENT != EXECUTION POLICY
          </div>


          {current && (
            <GhostWalkPolicyAdmissionCard
              targetSha256={targetSha256}
              acceptedIntentRevisionSha256={current.revision_sha256}
              operatorNoteRevisionSha256={sourceOperatorNoteRevisionSha256}
            />
          )}
        </>
      )}
    </section>
  );
}
