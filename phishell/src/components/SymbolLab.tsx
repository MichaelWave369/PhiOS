import { useEffect, useMemo, useState } from "react";
import {
  claimClassFor,
  createNode,
  createPromotionProposal,
  createReturnPointer,
  normalizeTags,
  relatedSeeds,
  type PromotionProposal,
  type PromotionTarget,
  type SymbolKind,
  type SymbolLabNode,
} from "../curiosity/symbolLab";
import {
  canonicalArtifactToSessionNode,
  curiosityProjectionProvider,
  type CanonicalCuriosityArtifact,
  type CuriosityProjection,
} from "../curiosity/curiosityProjection";
import {
  curiosityPersistenceClient,
  nodeToPersistPayload,
  type CuriosityAuthorityHealth,
  type CuriosityPersistRequest,
} from "../curiosity/curiosityPersistence";

const kinds: Array<{ kind: SymbolKind; label: string; glyph: string }> = [
  { kind: "symbol", label: "Symbol", glyph: "◈" },
  { kind: "metaphor", label: "Metaphor", glyph: "≈" },
  { kind: "question", label: "Question", glyph: "?" },
  { kind: "hypothesis", label: "Hypothesis", glyph: "△" },
  { kind: "association", label: "Association", glyph: "↔" },
  { kind: "pattern", label: "Pattern", glyph: "⌘" },
  { kind: "dream_fragment", label: "Dream", glyph: "☾" },
  { kind: "creative_seed", label: "Seed", glyph: "✦" },
];

const targets: Array<{ target: PromotionTarget; label: string }> = [
  { target: "research", label: "Offer to Research" },
  { target: "build", label: "Offer to Build" },
  { target: "ledger_review", label: "Offer to Ledger Review" },
];

function nowIso() {
  return new Date().toISOString();
}

function newId(prefix: string) {
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2, 8)}`;
}

export function SymbolLab() {
  const [nodes, setNodes] = useState<SymbolLabNode[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [kind, setKind] = useState<SymbolKind>("creative_seed");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [parentId, setParentId] = useState("");
  const [returnPrompt, setReturnPrompt] = useState("");
  const [returnContext, setReturnContext] = useState("");
  const [proposals, setProposals] = useState<PromotionProposal[]>([]);
  const [canonicalProjection, setCanonicalProjection] = useState<CuriosityProjection | null>(null);
  const [canonicalStatus, setCanonicalStatus] = useState<"loading" | "ready" | "unavailable">(
    "loading",
  );
  const [authorityHealth, setAuthorityHealth] = useState<CuriosityAuthorityHealth | null>(null);
  const [authorityStatus, setAuthorityStatus] = useState<"loading" | "ready" | "unavailable">(
    "loading",
  );
  const [persistRequests, setPersistRequests] = useState<Record<string, CuriosityPersistRequest>>({});
  const [persistBusy, setPersistBusy] = useState(false);

  const selected = nodes.find((node) => node.id === selectedId) ?? null;
  const related = useMemo(
    () => (selected ? relatedSeeds(selected, nodes).slice(0, 6) : []),
    [selected, nodes],
  );
  const selectedPersistRequest = selected ? persistRequests[selected.id] ?? null : null;
  const selectedPersistPayload = selected ? nodeToPersistPayload(selected) : null;

  async function refreshCanonical() {
    setCanonicalStatus("loading");
    const projection = await curiosityProjectionProvider.read();
    setCanonicalProjection(projection);
    setCanonicalStatus(projection ? "ready" : "unavailable");
  }

  async function refreshAuthority() {
    setAuthorityStatus("loading");
    const health = await curiosityPersistenceClient.health();
    setAuthorityHealth(health);
    setAuthorityStatus(health ? "ready" : "unavailable");
  }

  useEffect(() => {
    void refreshCanonical();
    void refreshAuthority();
  }, []);

  function openCanonical(artifact: CanonicalCuriosityArtifact) {
    const node = canonicalArtifactToSessionNode(artifact);
    setNodes((current) =>
      current.some((item) => item.id === node.id) ? current : [...current, node],
    );
    setSelectedId(node.id);
  }

  function addNode() {
    if (!title.trim() || !content.trim()) return;
    const node = createNode({
      id: newId("curiosity"),
      kind,
      title,
      content,
      tags: normalizeTags(tags),
      parentIds: parentId ? [parentId] : [],
      createdAt: nowIso(),
    });
    setNodes((current) => [...current, node]);
    setSelectedId(node.id);
    setTitle("");
    setContent("");
    setTags("");
    setParentId("");
  }

  function appendReturnPointer() {
    if (!selected || !returnPrompt.trim()) return;
    const pointer = createReturnPointer({
      id: newId("return"),
      nodeId: selected.id,
      prompt: returnPrompt,
      context: returnContext,
      createdAt: nowIso(),
    });
    setNodes((current) =>
      current.map((node) =>
        node.id === selected.id
          ? { ...node, returnPointers: [...node.returnPointers, pointer] }
          : node,
      ),
    );
    setReturnPrompt("");
    setReturnContext("");
  }

  function offer(target: PromotionTarget) {
    if (!selected) return;
    const proposal = createPromotionProposal({
      id: newId("promotion"),
      nodeId: selected.id,
      target,
      createdAt: nowIso(),
    });
    setProposals((current) => [proposal, ...current]);
  }

  async function requestPersistence() {
    if (!selected || !selectedPersistPayload || authorityStatus !== "ready") return;
    setPersistBusy(true);
    const request = await curiosityPersistenceClient.request(selected);
    if (request) {
      setPersistRequests((current) => ({ ...current, [selected.id]: request }));
    } else {
      setAuthorityStatus("unavailable");
    }
    setPersistBusy(false);
  }

  async function checkPersistence() {
    if (!selected || !selectedPersistRequest) return;
    setPersistBusy(true);
    const updated = await curiosityPersistenceClient.status(selectedPersistRequest.requestId);
    if (updated) {
      setPersistRequests((current) => ({ ...current, [selected.id]: updated }));
      if (updated.status === "succeeded" && updated.artifactSha256) {
        const canonicalParentId = `canonical:${updated.artifactSha256}`;
        setNodes((current) =>
          current.map((node) =>
            node.id === selected.id
              ? node
              : {
                  ...node,
                  parentIds: node.parentIds.map((parentId) =>
                    parentId === selected.id ? canonicalParentId : parentId,
                  ),
                },
          ),
        );
        await refreshCanonical();
      }
    }
    setPersistBusy(false);
  }

  return (
    <section className="symbol-lab">
      <header className="symbol-lab-head">
        <div>
          <div className="eyebrow">ΦDREAM · CURIOSITY LANE</div>
          <h1>Symbol Lab</h1>
          <p>
            Explore before deciding. Symbols may remain symbols; hypotheses may remain open.
          </p>
        </div>
        <div className="symbol-boundary">
          <b>SESSION CREATE · CANONICAL READ</b>
          <span>PERSIST REQUEST · EXTERNAL OPERATOR APPROVAL</span>
        </div>
      </header>

      <div className="symbol-lab-layout">
        <aside className="symbol-capture panel">
          <div className="panel-title">CAPTURE A SEED</div>
          <div className="symbol-kind-grid">
            {kinds.map((item) => (
              <button
                key={item.kind}
                className={kind === item.kind ? "active" : ""}
                onClick={() => setKind(item.kind)}
                title={item.label}
              >
                <b>{item.glyph}</b>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          <label>
            <span>Title</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Name the spark…"
            />
          </label>

          <label>
            <span>Fragment / thought</span>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="What are you noticing, wondering, or imagining?"
            />
          </label>

          <label>
            <span>Tags</span>
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="gear, water, rhythm"
            />
          </label>

          <label>
            <span>Parent thread</span>
            <select value={parentId} onChange={(event) => setParentId(event.target.value)}>
              <option value="">No parent</option>
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.title}
                </option>
              ))}
            </select>
          </label>

          <div className="claim-preview">
            <span>CLAIM CLASS</span>
            <b>{claimClassFor(kind).replaceAll("_", " ")}</b>
          </div>

          <button className="capture-seed" onClick={addNode}>
            Add to Session Field
          </button>
          <small className="symbol-disclaimer">
            This creates an ephemeral Curiosity object in the current PhiShell session. Canonical
            persistence requires an explicit local operator approval outside the browser.
          </small>
        </aside>

        <section className="symbol-field panel">
          <div className="symbol-field-head">
            <div>
              <div className="panel-title">CONSTELLATION</div>
              <small>{nodes.length} SESSION OBJECTS</small>
            </div>
            <span>meaning ≠ verification</span>
          </div>

          {nodes.length === 0 ? (
            <div className="symbol-empty">
              <b>The field is empty.</b>
              <p>
                Add a symbol, strange question, dream fragment, metaphor, hypothesis, or creative
                seed. Nothing here has to earn a verdict yet.
              </p>
            </div>
          ) : (
            <div className="symbol-node-grid">
              {nodes.map((node, index) => (
                <button
                  key={node.id}
                  className={
                    selectedId === node.id
                      ? `symbol-node selected node-${index % 6}`
                      : `symbol-node node-${index % 6}`
                  }
                  onClick={() => setSelectedId(node.id)}
                >
                  <small>{node.kind.replaceAll("_", " ")}</small>
                  <b>{node.title}</b>
                  <span>{node.claimClass.replaceAll("_", " ")}</span>
                  <em>{node.tags.slice(0, 3).join(" · ") || "untagged"}</em>
                  {node.parentIds.length > 0 && <i>↳ child thread</i>}
                  {node.returnPointers.length > 0 && <i>↻ return marked</i>}
                  {node.id.startsWith("canonical:") && <i>◇ canonical source</i>}
                </button>
              ))}
            </div>
          )}
        </section>

        <aside className="symbol-inspector panel">
          <div className="panel-title">THREAD INSPECTOR</div>
          {!selected ? (
            <div className="symbol-empty compact">
              Select a curiosity object to inspect its lineage, neighbors, and return path.
            </div>
          ) : (
            <>
              <div className="symbol-inspector-title">
                <small>{selected.kind.replaceAll("_", " ")}</small>
                <h2>{selected.title}</h2>
                <span>{selected.claimClass.replaceAll("_", " ")}</span>
              </div>
              <p className="symbol-content">{selected.content}</p>

              <div className="symbol-authority-grid">
                <div><span>OPERATIONAL</span><b>FALSE</b></div>
                <div><span>ACTION</span><b>FALSE</b></div>
                <div><span>EXECUTION</span><b>FALSE</b></div>
              </div>

              <section className="symbol-related">
                <h3>RELATED SEEDS</h3>
                {related.length === 0 ? (
                  <small>No transparent relationship found yet.</small>
                ) : (
                  related.map((item) => (
                    <button key={item.node.id} onClick={() => setSelectedId(item.node.id)}>
                      <b>{item.node.title}</b>
                      <span>{item.reasons.join(" · ")}</span>
                    </button>
                  ))
                )}
              </section>

              <section className="symbol-return">
                <h3>RETURN POINTER</h3>
                <input
                  value={returnPrompt}
                  onChange={(event) => setReturnPrompt(event.target.value)}
                  placeholder="Where should we resume?"
                />
                <textarea
                  value={returnContext}
                  onChange={(event) => setReturnContext(event.target.value)}
                  placeholder="Optional context to preserve…"
                />
                <button onClick={appendReturnPointer}>Mark Return</button>
                {selected.returnPointers.length > 0 && (
                  <div className="return-history">
                    {[...selected.returnPointers].reverse().slice(0, 3).map((pointer) => (
                      <article key={pointer.id}>
                        <b>{pointer.prompt}</b>
                        <small>{pointer.context || "No extra context."}</small>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="symbol-persist">
                <h3>CANONICAL PERSISTENCE</h3>
                <div className="persist-health">
                  <span>BROKER</span>
                  <b>{authorityStatus.toUpperCase()}</b>
                  {authorityHealth && <code>{authorityHealth.principalId}</code>}
                </div>

                {selected.id.startsWith("canonical:") ? (
                  <small>This object is already canonical. Read copies cannot be re-persisted.</small>
                ) : selectedPersistPayload === null ? (
                  <small>
                    HELD · persist session-local parent threads first so canonical lineage is not lost.
                  </small>
                ) : selectedPersistRequest ? (
                  <div className="persist-request-card">
                    <div>
                      <span>STATUS</span>
                      <b>{selectedPersistRequest.status.toUpperCase()}</b>
                    </div>
                    <code>{selectedPersistRequest.payloadSha256.slice(0, 20)}…</code>
                    {selectedPersistRequest.status === "pending" && (
                      <>
                        <small>Approve this exact request outside PhiShell:</small>
                        <pre>{selectedPersistRequest.approvalCommand}</pre>
                      </>
                    )}
                    {selectedPersistRequest.artifactSha256 && (
                      <div className="persist-artifact-hash">
                        <span>CANONICAL SHA</span>
                        <code>{selectedPersistRequest.artifactSha256}</code>
                      </div>
                    )}
                    <button onClick={() => void checkPersistence()} disabled={persistBusy}>
                      {persistBusy ? "Checking…" : "Check Status"}
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => void requestPersistence()}
                      disabled={persistBusy || authorityStatus !== "ready"}
                    >
                      {persistBusy ? "Requesting…" : "Request Persistence"}
                    </button>
                    <small>
                      Creates a zero-authority pending request only. Approval, ActionLease issuance,
                      and execution remain outside the browser.
                    </small>
                  </>
                )}

                {authorityStatus === "unavailable" && (
                  <button onClick={() => void refreshAuthority()} disabled={persistBusy}>
                    Retry Broker
                  </button>
                )}
              </section>

              <section className="symbol-promote">
                <h3>EXPLICIT HANDOFF</h3>
                {targets.map((item) => (
                  <button key={item.target} onClick={() => offer(item.target)}>
                    {item.label}
                  </button>
                ))}
                <small>Creates proposal_only state. No destination admits it automatically.</small>
              </section>
            </>
          )}
        </aside>
      </div>

      <section className="canonical-curiosity panel">
        <div className="canonical-curiosity-head">
          <div>
            <div className="panel-title">CANONICAL CURIOSITY STORE</div>
            <small>READ-ONLY PROJECTION · ZERO AUTHORITY</small>
          </div>
          <button onClick={() => void refreshCanonical()} disabled={canonicalStatus === "loading"}>
            {canonicalStatus === "loading" ? "Reading…" : "Refresh"}
          </button>
        </div>
        {canonicalStatus === "unavailable" ? (
          <div className="empty-state">
            Curiosity sidecar unavailable. Start the local projection service to read canonical
            artifacts; the Symbol Lab remains session-local meanwhile.
          </div>
        ) : canonicalProjection?.artifacts.length ? (
          <div className="canonical-curiosity-list">
            {canonicalProjection.artifacts.slice(0, 8).map((artifact) => (
              <article key={artifact.curiosity_artifact_sha256}>
                <div>
                  <small>{artifact.artifact_kind.replaceAll("_", " ")}</small>
                  <b>{artifact.title}</b>
                  <code>{artifact.curiosity_artifact_sha256.slice(0, 16)}…</code>
                </div>
                <span>{artifact.claim_class.replaceAll("_", " ")}</span>
                <button onClick={() => openCanonical(artifact)}>Open Read Copy</button>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            {canonicalStatus === "loading"
              ? "Reading canonical Curiosity Store…"
              : "No canonical Curiosity artifacts are stored yet."}
          </div>
        )}
        <div className="canonical-write-hold">
          <b>WRITE GOVERNED</b>
          <span>
            {authorityStatus === "ready"
              ? "operator_approval_required"
              : "authority_broker_unavailable"}
          </span>
          <small>
            Stored artifacts can be read without authority. New persistence requires an exact
            external operator approval and a single-use ActionLease.
          </small>
        </div>
      </section>

      <section className="symbol-proposals panel">
        <div className="panel-title">PROMOTION PROPOSALS · SESSION ONLY</div>
        {proposals.length === 0 ? (
          <div className="empty-state">Nothing has been offered downstream.</div>
        ) : (
          proposals.slice(0, 6).map((proposal) => {
            const node = nodes.find((item) => item.id === proposal.nodeId);
            return (
              <article key={proposal.id}>
                <b>{node?.title ?? "Unknown node"}</b>
                <span>→ {proposal.target.replaceAll("_", " ")}</span>
                <em>{proposal.status}</em>
                <small>authority: 0</small>
              </article>
            );
          })
        )}
      </section>
    </section>
  );
}
