import { useCallback, useEffect, useState } from "react";
import { GhostWalkAcceptedIntentEditor } from "./GhostWalkAcceptedIntentEditor";
import {
  ghostWalkOperatorLogClient,
  type GhostWalkOperatorNote,
  type GhostWalkOperatorNoteStatus,
} from "../ghostwalk/operatorLog";

function shortHash(value: string) {
  return `${value.slice(0, 10)}…`;
}

export function GhostWalkOperatorEditor({
  targetSha256,
  onClose,
  onSaved,
}: {
  targetSha256: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [note, setNote] = useState<GhostWalkOperatorNote | null>(null);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const current = await ghostWalkOperatorLogClient.read(targetSha256);
      setNote(current);
      if (current) {
        setBody(current.body);
        setMessage(null);
      } else {
        setMessage("Current OperatorLog revision is unavailable or failed validation.");
      }
    } finally {
      setLoading(false);
    }
  }, [targetSha256]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = useCallback(
    async (status: GhostWalkOperatorNoteStatus) => {
      if (!note || !body.trim()) return;
      setBusy(true);
      setMessage(null);
      try {
        const result = await ghostWalkOperatorLogClient.edit({
          targetSha256,
          expectedRevisionSha256: note.revision_sha256,
          body: body.trim(),
          status,
        });
        if (result.kind === "conflict") {
          setMessage(
            "Revision conflict: this interpretation changed after you loaded it. Your draft is preserved; reload the current revision before saving.",
          );
          return;
        }
        if (result.kind === "unavailable") {
          setMessage("The governed OperatorLog editor rejected or could not validate the edit.");
          return;
        }
        const next = result.envelope.outcome.note;
        setNote(next);
        setBody(next.body);
        setMessage(
          `Saved revision ${next.revision} as ${next.status}. Original inference evidence was not modified.`,
        );
        onSaved();
      } finally {
        setBusy(false);
      }
    },
    [body, note, onSaved, targetSha256],
  );

  return (
    <div className="ghostwalk-editor">
      <div className="ghostwalk-editor-head">
        <div>
          <small>OPERATOR INTERPRETATION</small>
          <b>{shortHash(targetSha256)}</b>
        </div>
        <button onClick={onClose}>CLOSE</button>
      </div>

      {loading ? (
        <div className="ghostwalk-empty">Loading current append-only revision…</div>
      ) : note ? (
        <>
          <div className="ghostwalk-editor-meta">
            <span>revision {note.revision}</span>
            <span>{note.status}</span>
            <span>{note.author_id}</span>
            <span>{shortHash(note.revision_sha256)}</span>
          </div>

          <textarea
            value={body}
            maxLength={16384}
            onChange={(event) => setBody(event.currentTarget.value)}
            aria-label="Operator interpretation"
          />

          <div className="ghostwalk-editor-actions">
            <button
              disabled={busy || body.trim().length === 0}
              onClick={() => void save("ACTIVE")}
            >
              SAVE NEW REVISION
            </button>
            <button
              className="retract"
              disabled={busy || body.trim().length === 0}
              onClick={() => void save("RETRACTED")}
            >
              APPEND RETRACTION
            </button>
            <button disabled={busy} onClick={() => void load()}>
              RELOAD CURRENT
            </button>
          </div>

          {message && <div className="ghostwalk-editor-message">{message}</div>}

          <div className="ghostwalk-editor-boundary">
            HUMAN INTERPRETATION != MACHINE INFERENCE · SAVE APPENDS · SOURCE RECEIPT IMMUTABLE · EXECUTION AUTHORITY FALSE
          </div>

          <GhostWalkAcceptedIntentEditor
            targetSha256={targetSha256}
            sourceOperatorNoteRevisionSha256={note.revision_sha256}
            operatorNoteActive={note.status === "ACTIVE"}
          />
        </>
      ) : (
        <>
          {message && <div className="ghostwalk-editor-message">{message}</div>}
          <button className="ghostwalk-editor-reload" onClick={() => void load()}>
            RETRY
          </button>
        </>
      )}
    </div>
  );
}
